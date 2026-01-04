"""
Модуль для работы с настоящими подписками YooKassa
Реализует автоплатежи через сохраненные платежные методы
Адаптирован для основного проекта с SQLite базой данных
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from telegram import Bot
from dotenv import load_dotenv
from yookassa import Configuration, Payment
import db

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Настройки YooKassa
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN')
TEST_PROVIDER_TOKEN = os.getenv('TEST_PROVIDER_TOKEN', PROVIDER_TOKEN)
CURRENCY = os.getenv('CURRENCY', 'RUB')

# Конфигурация YooKassa SDK
if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
    logger.info("YooKassa SDK сконфигурирован для подписок.")
else:
    logger.error("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не найдены!")

# Тарифы подписок
SUBSCRIPTION_TARIFFS = {
    'basic': {
        'name': 'Basic Plan',
        'price': 40000,  # in kopecks (400 rubles)
        'description': '8 text generations + 4 images per day',
        'generations': 8,
        'images': 4,
        'billing_period': 'monthly'
    },
    'standard': {
        'name': 'Standard Plan', 
        'price': 55000,  # in kopecks (550 rubles)
        'description': '16 text generations + 8 images per day',
        'generations': 16,
        'images': 8,
        'billing_period': 'monthly'
    },
    'premium': {
        'name': 'Premium Plan',
        'price': 75000,  # in kopecks (750 rubles)
        'description': '25 text generations + 15 images per day',
        'generations': 25,
        'images': 15,
        'billing_period': 'monthly'
    }
}


class YooKassaSubscriptionManager:
    """Менеджер для работы с подписками YooKassa"""

    def __init__(self):
        pass

    async def create_subscription_payment(
        self, 
        user_id: int, 
        tariff: str, 
        bot: Bot,
        chat_id: int,
        save_payment_method: bool = True
    ) -> Dict[str, Any]:
        """
        Создает первый платеж для подписки с сохранением карты
        
        Args:
            user_id: ID пользователя Telegram
            tariff: Тип тарифа (basic, standard, premium)
            bot: Экземпляр Telegram бота
            chat_id: ID чата для отправки инвойса
            save_payment_method: Сохранять ли платежный метод
            
        Returns:
            Dict с результатом операции
        """
        try:
            if tariff not in SUBSCRIPTION_TARIFFS:
                raise ValueError(f"Неизвестный тариф: {tariff}")

            config = SUBSCRIPTION_TARIFFS[tariff]
            
            # Проверяем наличие токена провайдера
            provider_token = TEST_PROVIDER_TOKEN or PROVIDER_TOKEN
            if not provider_token:
                return {
                    'success': False,
                    'error': 'Токен провайдера не настроен'
                }

            # Создаем уникальный payload для отслеживания платежа
            payload = json.dumps({
                'user_id': user_id,
                'tariff': tariff,
                'subscription': True,
                'save_payment_method': save_payment_method,
                'timestamp': datetime.now().isoformat()
            })

            # Отправляем инвойс через Telegram Payments
            from telegram import LabeledPrice
            
            prices = [LabeledPrice(config['name'], config['price'])]
            
            message = await bot.send_invoice(
                chat_id=chat_id,
                title=f"Подписка: {config['name']}",
                description=config['description'],
                payload=payload,
                provider_token=provider_token,
                currency=CURRENCY,
                prices=prices,
                need_name=False,
                need_phone_number=False,
                need_email=False,
                need_shipping_address=False,
                send_phone_number_to_provider=False,
                send_email_to_provider=False,
                is_flexible=False,
                disable_notification=False,
                protect_content=False,
                reply_to_message_id=None,
                allow_sending_without_reply=True
            )

            # Сохраняем данные платежа в БД
            await self._save_subscription_data(
                user_id, tariff, payload, message.message_id, config['price']
            )

            logger.info(f"Создан инвойс для подписки пользователя {user_id}, тариф {tariff}")
            
            return {
                'success': True,
                'message_id': message.message_id,
                'payload': payload,
                'amount': config['price']
            }

        except Exception as e:
            logger.error(f"Ошибка создания платежа подписки для {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def _save_subscription_data(
        self, 
        user_id: int, 
        tariff: str, 
        payload: str, 
        message_id: int, 
        amount: int
    ):
        """Сохраняет данные подписки в БД"""
        try:
            # Получаем или создаем пользователя
            user = await db.get_user(user_id)
            if not user:
                await db.add_or_update_user(user_id, {
                    'subscription_active': False,
                    'subscription_end_date': None,
                    'auto_renewal': False,
                    'left_group': False
                })

            # Сохраняем информацию о платеже
            payment_info = {
                'tariff': tariff,
                'amount': amount,
                'payload': payload,
                'message_id': message_id,
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }

            await db.add_or_update_user(user_id, {
                'pending_payment': json.dumps(payment_info)
            })

            logger.info(f"Сохранены данные подписки для пользователя {user_id}")

        except Exception as e:
            logger.error(f"Ошибка сохранения данных подписки: {e}")

    async def process_successful_subscription_payment(
        self, 
        user_id: int, 
        payment_data: Dict[str, Any],
        bot: Bot
    ) -> Dict[str, Any]:
        """
        Обрабатывает успешный платеж подписки и активирует её
        
        Args:
            user_id: ID пользователя
            payment_data: Данные о платеже
            bot: Экземпляр бота
            
        Returns:
            Dict с результатом обработки
        """
        try:
            # Парсим payload
            payload_str = payment_data.get('invoice_payload', '{}')
            payload = json.loads(payload_str)
            
            tariff = payload.get('tariff')
            if not tariff or tariff not in SUBSCRIPTION_TARIFFS:
                raise ValueError(f"Неверный тариф в payload: {tariff}")

            # Получаем payment_method_id из YooKassa API
            provider_charge_id = payment_data.get('provider_payment_charge_id')
            payment_method_id = None
            
            if provider_charge_id:
                payment_method_id = await self._get_payment_method_from_yookassa(provider_charge_id)

            # Рассчитываем даты
            now = datetime.now()
            expires_at = now + timedelta(days=30)  # Месячная подписка
            next_billing = expires_at

            # Активируем подписку
            await self._activate_subscription(
                user_id, payment_data, payment_method_id, expires_at, next_billing
            )

            # Отправляем уведомление
            await self._send_subscription_activated_notification(
                bot, user_id, payment_data, expires_at, bool(payment_method_id)
            )

            logger.info(f"Подписка активирована для пользователя {user_id}")
            
            return {
                'success': True,
                'expires_at': expires_at,
                'has_auto_renewal': bool(payment_method_id)
            }

        except Exception as e:
            logger.error(f"Ошибка обработки успешного платежа подписки: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def _get_payment_method_from_yookassa(self, provider_charge_id: str) -> Optional[str]:
        """Получает payment_method_id из YooKassa API"""
        try:
            payment = Payment.find_one(provider_charge_id)
            if payment and payment.payment_method:
                return payment.payment_method.id
            return None
        except Exception as e:
            logger.error(f"Ошибка получения payment_method_id: {e}")
            return None

    async def _activate_subscription(
        self, 
        user_id: int, 
        payment_data: Dict[str, Any],
        payment_method_id: Optional[str],
        expires_at: datetime,
        next_billing: datetime
    ):
        """Активирует подписку в БД"""
        try:
            # Парсим payload для получения тарифа
            payload_str = payment_data.get('invoice_payload', '{}')
            payload = json.loads(payload_str)
            tariff = payload.get('tariff', 'basic')

            # Обновляем данные пользователя
            user_data = {
                'subscription_active': True,
                'subscription_end_date': expires_at,
                'auto_renewal': bool(payment_method_id),
                'current_tariff': tariff,
                'payment_method_id': payment_method_id,
                'next_billing_date': next_billing,
                'billing_attempts': 0
            }

            # Добавляем информацию о платеже в историю
            payment_info = {
                'amount': payment_data.get('total_amount', 0),
                'currency': payment_data.get('currency', 'RUB'),
                'provider_payment_charge_id': payment_data.get('provider_payment_charge_id'),
                'telegram_payment_charge_id': payment_data.get('telegram_payment_charge_id'),
                'tariff': tariff,
                'payment_date': datetime.now().isoformat(),
                'status': 'completed'
            }

            await db.update_user_subscription(
                user_id, True, expires_at, bool(payment_method_id), payment_info
            )

            logger.info(f"Подписка активирована в БД для пользователя {user_id}")

        except Exception as e:
            logger.error(f"Ошибка активации подписки в БД: {e}")
            raise

    async def _send_subscription_activated_notification(
        self, 
        bot: Bot, 
        user_id: int, 
        payment_data: Dict[str, Any],
        expires_at: datetime,
        has_auto_renewal: bool
    ):
        """Отправляет уведомление об активации подписки"""
        try:
            # Парсим payload для получения тарифа
            payload_str = payment_data.get('invoice_payload', '{}')
            payload = json.loads(payload_str)
            tariff = payload.get('tariff', 'basic')
            
            config = SUBSCRIPTION_TARIFFS.get(tariff, SUBSCRIPTION_TARIFFS['basic'])
            
            auto_renewal_text = "✅ Auto-renewal enabled" if has_auto_renewal else "❌ Auto-renewal disabled"
            
            message = f"""
🎉 <b>Subscription successfully activated!</b>

📦 <b>Plan:</b> {config['name']}
💰 <b>Amount:</b> {payment_data.get('total_amount', 0) // 100} {payment_data.get('currency', 'RUB')}
📅 <b>Valid until:</b> {expires_at.strftime('%d.%m.%Y %H:%M')}
🔄 <b>Status:</b> {auto_renewal_text}

Thank you for your payment! You now have access to all bot features.
            """

            await bot.send_message(
                chat_id=user_id,
                text=message.strip(),
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об активации: {e}")

    async def process_subscription_renewal(
        self, 
        user_id: int, 
        bot: Bot
    ) -> Dict[str, Any]:
        """
        Автоматически продлевает подписку пользователя
        
        Args:
            user_id: ID пользователя
            bot: Экземпляр бота
            
        Returns:
            Dict с результатом продления
        """
        try:
            # Получаем данные пользователя
            user = await db.get_user(user_id)
            if not user:
                return {'success': False, 'error': 'Пользователь не найден'}

            # Проверяем наличие сохраненного метода платежа
            user_data = json.loads(user.get('user_data', '{}'))
            payment_method_id = user_data.get('payment_method_id')
            
            if not payment_method_id:
                return {'success': False, 'error': 'Нет сохраненного метода платежа'}

            current_tariff = user_data.get('current_tariff', 'basic')
            config = SUBSCRIPTION_TARIFFS.get(current_tariff, SUBSCRIPTION_TARIFFS['basic'])

            # Создаем рекуррентный платеж
            payment_result = await self._create_recurring_payment(
                user_id, payment_method_id, config['price'], 
                f"Продление подписки: {config['name']}"
            )

            if not payment_result['success']:
                await self._handle_failed_renewal(user_id, bot, payment_result['error'])
                return payment_result

            # Обновляем подписку после успешного продления
            expires_at = datetime.now() + timedelta(days=30)
            next_billing = expires_at

            await self._update_subscription_after_renewal(
                user_id, expires_at, next_billing, payment_result['payment_id']
            )

            # Отправляем уведомление
            await self._send_renewal_success_notification(
                bot, user_id, current_tariff, config['price'], expires_at
            )

            logger.info(f"Подписка успешно продлена для пользователя {user_id}")
            
            return {
                'success': True,
                'expires_at': expires_at,
                'payment_id': payment_result['payment_id']
            }

        except Exception as e:
            logger.error(f"Ошибка продления подписки для {user_id}: {e}")
            await self._handle_failed_renewal(user_id, bot, str(e))
            return {'success': False, 'error': str(e)}

    async def _create_recurring_payment(
        self, 
        user_id: int, 
        payment_method_id: str, 
        amount: int, 
        description: str
    ) -> Dict[str, Any]:
        """Создает рекуррентный платеж через YooKassa API"""
        try:
            payment = Payment.create({
                "amount": {
                    "value": f"{amount / 100:.2f}",
                    "currency": CURRENCY
                },
                "payment_method_id": payment_method_id,
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/your_bot"
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": str(user_id),
                    "type": "subscription_renewal"
                }
            }, uuid.uuid4())

            if payment.status == 'succeeded':
                return {
                    'success': True,
                    'payment_id': payment.id
                }
            else:
                return {
                    'success': False,
                    'error': f"Платеж не прошел: {payment.status}"
                }

        except Exception as e:
            logger.error(f"Ошибка создания рекуррентного платежа: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def _update_billing_attempt(self, user_id: int):
        """Обновляет счетчик попыток списания"""
        try:
            user = await db.get_user(user_id)
            if user:
                user_data = json.loads(user.get('user_data', '{}'))
                billing_attempts = user_data.get('billing_attempts', 0) + 1
                user_data['billing_attempts'] = billing_attempts
                
                await db.add_or_update_user(user_id, {'user_data': json.dumps(user_data)})
                
        except Exception as e:
            logger.error(f"Ошибка обновления счетчика попыток: {e}")

    async def _update_subscription_after_renewal(
        self, 
        user_id: int, 
        expires_at: datetime, 
        next_billing: datetime, 
        payment_id: str
    ):
        """Обновляет данные подписки после успешного продления"""
        try:
            user = await db.get_user(user_id)
            if user:
                user_data = json.loads(user.get('user_data', '{}'))
                user_data.update({
                    'next_billing_date': next_billing.isoformat(),
                    'billing_attempts': 0,
                    'last_payment_id': payment_id
                })
                
                await db.update_user_subscription(
                    user_id, True, expires_at, True, {
                        'payment_id': payment_id,
                        'renewal_date': datetime.now().isoformat(),
                        'status': 'renewed'
                    }
                )
                
                await db.add_or_update_user(user_id, {'user_data': json.dumps(user_data)})

        except Exception as e:
            logger.error(f"Ошибка обновления подписки после продления: {e}")

    async def _send_renewal_success_notification(
        self, 
        bot: Bot, 
        user_id: int, 
        tariff: str, 
        amount: int, 
        expires_at: datetime
    ):
        """Отправляет уведомление об успешном продлении"""
        try:
            config = SUBSCRIPTION_TARIFFS.get(tariff, SUBSCRIPTION_TARIFFS['basic'])
            
            message = f"""
🔄 <b>Subscription successfully renewed!</b>

📦 <b>Plan:</b> {config['name']}
💰 <b>Charged:</b> {amount // 100} {CURRENCY}
📅 <b>Valid until:</b> {expires_at.strftime('%d.%m.%Y %H:%M')}

Auto-renewal is working properly. Thank you for using our service!
            """

            await bot.send_message(
                chat_id=user_id,
                text=message.strip(),
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о продлении: {e}")

    async def _handle_failed_renewal(self, user_id: int, bot: Bot, error: str):
        """Обрабатывает неудачное автопродление"""
        try:
            await self._update_billing_attempt(user_id)
            
            user = await db.get_user(user_id)
            if user:
                user_data = json.loads(user.get('user_data', '{}'))
                billing_attempts = user_data.get('billing_attempts', 0)
                
                if billing_attempts >= 3:
                    # Отключаем автопродление после 3 неудачных попыток
                    user_data['auto_renewal'] = False
                    user_data['payment_method_id'] = None
                    await db.add_or_update_user(user_id, {'user_data': json.dumps(user_data)})
                    
                    message = """
❌ <b>Auto-renewal disabled</b>

Unfortunately, we couldn't charge your card after 3 attempts.
Subscription auto-renewal has been disabled.

To resume your subscription, use the /subscribe command
                    """
                else:
                    message = f"""
⚠️ <b>Auto-renewal error</b>

Failed to renew subscription automatically.
Attempt {billing_attempts} of 3.

Please check your card balance or update payment details.
                    """

                await bot.send_message(
                    chat_id=user_id,
                    text=message.strip(),
                    parse_mode='HTML'
                )

        except Exception as e:
            logger.error(f"Ошибка обработки неудачного продления: {e}")

    async def cancel_subscription(self, user_id: int, reason: str = "Отмена пользователем") -> Dict[str, Any]:
        """
        Отменяет подписку пользователя
        
        Args:
            user_id: ID пользователя
            reason: Причина отмены
            
        Returns:
            Dict с результатом отмены
        """
        try:
            # Деактивируем подписку
            await db.update_user_subscription(
                user_id, False, None, False, {
                    'cancellation_reason': reason,
                    'cancelled_at': datetime.now().isoformat()
                }
            )

            # Очищаем данные автопродления
            user = await db.get_user(user_id)
            if user:
                user_data = json.loads(user.get('user_data', '{}'))
                user_data.update({
                    'payment_method_id': None,
                    'auto_renewal': False,
                    'current_tariff': None
                })
                await db.add_or_update_user(user_id, {'user_data': json.dumps(user_data)})

            logger.info(f"Подписка отменена для пользователя {user_id}: {reason}")
            
            return {
                'success': True,
                'message': 'Подписка успешно отменена'
            }

        except Exception as e:
            logger.error(f"Ошибка отмены подписки: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_users_for_renewal(self) -> List[Dict[str, Any]]:
        """
        Получает список пользователей, которым нужно продлить подписку
        
        Returns:
            List пользователей для автопродления
        """
        try:
            # Получаем пользователей с активными подписками и автопродлением
            users = await db.get_users_for_reminder([0])  # Подписки, истекающие сегодня
            
            renewal_users = []
            for user in users:
                user_data = json.loads(user.get('user_data', '{}'))
                if (user_data.get('auto_renewal') and 
                    user_data.get('payment_method_id') and
                    user_data.get('billing_attempts', 0) < 3):
                    renewal_users.append({
                        'user_id': user['user_id'],
                        'tariff': user_data.get('current_tariff', 'basic'),
                        'payment_method_id': user_data.get('payment_method_id'),
                        'billing_attempts': user_data.get('billing_attempts', 0)
                    })

            return renewal_users

        except Exception as e:
            logger.error(f"Ошибка получения пользователей для продления: {e}")
            return []


def get_subscription_manager():
    """Создает экземпляр менеджера подписок"""
    return YooKassaSubscriptionManager()


async def auto_renew_all_subscriptions(bot: Bot) -> int:
    """
    Запускает автопродление для всех подходящих подписок
    
    Args:
        bot: Экземпляр Telegram бота
        
    Returns:
        int: Количество обработанных попыток продления
    """
    try:
        manager = get_subscription_manager()
        users_for_renewal = await manager.get_users_for_renewal()
        
        processed_count = 0
        for user_data in users_for_renewal:
            try:
                result = await manager.process_subscription_renewal(
                    user_data['user_id'], bot
                )
                processed_count += 1
                
                if result['success']:
                    logger.info(f"Подписка продлена для пользователя {user_data['user_id']}")
                else:
                    logger.warning(f"Не удалось продлить подписку для {user_data['user_id']}: {result.get('error')}")
                    
            except Exception as e:
                logger.error(f"Ошибка продления подписки для {user_data['user_id']}: {e}")
                processed_count += 1

        logger.info(f"Обработано {processed_count} попыток автопродления")
        return processed_count

    except Exception as e:
        logger.error(f"Ошибка массового автопродления: {e}")
        return 0
