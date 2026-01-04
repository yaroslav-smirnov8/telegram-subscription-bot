"""
Модуль для интеграции с YooKassa через Telegram Payments
Перенесен из example/telegram_payments.py для основного проекта
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from telegram import Bot, LabeledPrice
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from yookassa import Configuration, Payment
import uuid

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Настройки YooKassa для Telegram Payments
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN')
TEST_PROVIDER_TOKEN = os.getenv('TEST_PROVIDER_TOKEN', PROVIDER_TOKEN)
CURRENCY = os.getenv('CURRENCY', 'RUB')
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')

# Конфигурация YooKassa SDK
if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
    logger.info("YooKassa SDK сконфигурирован.")
else:
    logger.warning("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не найдены.")

# Проверяем наличие токена провайдера
if not PROVIDER_TOKEN or PROVIDER_TOKEN.startswith('ЗАМЕНИТЕ_НА_ВАШ'):
    logger.warning("PROVIDER_TOKEN не настроен! Платежи будут недоступны.")
    PROVIDER_TOKEN = None
    TEST_PROVIDER_TOKEN = None
else:
    logger.info(f"PROVIDER_TOKEN настроен: {PROVIDER_TOKEN[:15]}...")

# Настройки тарифов из price_config.json + дефолтные значения
def get_tariff_configs() -> Dict[str, Dict]:
    """Получить конфигурацию тарифов из price_config.json"""
    try:
        with open('price_config.json', 'r') as f:
            config = json.load(f)
        
        # Конвертируем цены в копейки для Telegram API
        tariff_configs = {}
        regular_price = int(config.get('regular_price', 1800) * 100)  # в копейках
        returning_price = int(config.get('returning_price', 2000) * 100)  # в копейках
        
        tariff_configs['regular'] = {
            'name': 'Регулярная подписка',
            'price': regular_price,
            'description': f'Доступ к группе - {regular_price//100} ₽/месяц',
        }
        
        tariff_configs['returning'] = {
            'name': 'Подписка для вернувшихся',
            'price': returning_price,
            'description': f'Доступ к группе - {returning_price//100} ₽/месяц (возврат)',
        }
        
        return tariff_configs
        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Ошибка чтения price_config.json: {e}. Используем дефолтные цены.")
        return {
            'regular': {
                'name': 'Регулярная подписка',
                'price': 180000,  # 1800 рублей в копейках
                'description': 'Доступ к группе - 1800 ₽/месяц',
            },
            'returning': {
                'name': 'Подписка для вернувших',
                'price': 200000,  # 2000 рублей в копейках
                'description': 'Доступ к группе - 2000 ₽/месяц (возврат)',
            }
        }

# Получаем актуальную конфигурацию тарифов
TARIFF_CONFIGS = get_tariff_configs()


async def create_invoice(
    bot: Bot,
    chat_id: int,
    tariff: str,
    user_id: int,
    test_mode: bool = False,
    is_recurring: bool = True  # По умолчанию включаем рекуррентные платежи
) -> Dict[str, Any]:
    """
    Создает и отправляет инвойс пользователю через Telegram Payments
    
    Args:
        bot: Экземпляр Telegram бота
        chat_id: ID чата для отправки инвойса
        tariff: Тип тарифа (regular, returning)
        user_id: ID пользователя Telegram
        test_mode: Использовать тестовый режим
        is_recurring: Является ли платеж рекуррентным (для сохранения карты)
        
    Returns:
        Dict с результатом создания инвойса
    """
    try:
        if tariff not in TARIFF_CONFIGS:
            # Обновляем конфигурацию тарифов
            global TARIFF_CONFIGS
            TARIFF_CONFIGS = get_tariff_configs()
            
            if tariff not in TARIFF_CONFIGS:
                raise ValueError(f"Неизвестный тариф: {tariff}")

        config = TARIFF_CONFIGS[tariff]

        # Проверяем наличие токена провайдера
        provider_token = TEST_PROVIDER_TOKEN if test_mode else PROVIDER_TOKEN
        if not provider_token:
            raise ValueError("PROVIDER_TOKEN не настроен. Подключите YooKassa в BotFather.")
        
        # Логируем информацию о провайдере
        is_test_token = provider_token and ':TEST:' in provider_token
        logger.info(f"🔑 Используемый провайдер: {'ТЕСТОВЫЙ' if is_test_token else 'БОЕВОЙ'}")
        logger.info(f"🎯 test_mode параметр: {test_mode}")
        logger.info(f"🔄 is_recurring (сохранение карты): {is_recurring}")
        
        # Создаем уникальный payload для отслеживания платежа
        payload = f"subscription_{tariff}_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Создаем массив цен
        prices = [LabeledPrice(label=config['name'], amount=config['price'])]
        
        # Определяем, боевой это режим или тестовый
        is_live_mode = not test_mode and not is_test_token
        
        # Настройка данных для автоплатежей
        if is_recurring:
            if is_live_mode:
                # В БОЕВОМ режиме используем полные чеки 54-ФЗ
                receipt_data = {
                    "customer": {
                        "email": f"user{user_id}@telegram-bot.local"
                    },
                    "items": [
                        {
                            "description": config['description'],
                            "quantity": "1.00",
                            "amount": {
                                "value": f"{config['price'] / 100:.2f}",
                                "currency": CURRENCY
                            },
                            "vat_code": 1,  # НДС 20%
                            "payment_mode": "full_payment",
                            "payment_subject": "service"
                        }
                    ],
                    "tax_system_code": 1  # ОСН
                }
                
                provider_data = json.dumps({
                    'save_card': True,
                    'receipt': receipt_data
                }, ensure_ascii=False)
                
                logger.info(f"💼 БОЕВОЙ режим: чеки 54-ФЗ + автоплатежи")
            else:
                # В ТЕСТОВОМ режиме упрощенная схема
                provider_data = json.dumps({
                    'save_card': True
                })
                logger.info(f"🧪 ТЕСТОВЫЙ режим: упрощенная схема")
        else:
            provider_data = None
        
        # Отправляем инвойс
        invoice_params = {
            'chat_id': chat_id,
            'title': config['name'],
            'description': config['description'],
            'payload': payload,
            'provider_token': provider_token,
            'currency': CURRENCY,
            'prices': prices,
            'start_parameter': f"pay_{tariff}"
        }
        
        if provider_data:
            invoice_params['provider_data'] = provider_data

        # Логируем параметры
        logger.info(f"Создаем инвойс: {config['name']} за {config['price']/100:.2f} ₽")
        logger.info(f"Payload: {payload}")

        message = await bot.send_invoice(**invoice_params)

        logger.info(f"✅ Инвойс отправлен! Message ID: {message.message_id}")
        
        return {
            'success': True,
            'message_id': message.message_id,
            'payload': payload,
            'tariff': tariff,
            'amount': config['price'],
            'currency': CURRENCY
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании инвойса: {e}")
        import traceback
        logger.error(f"Трейсбек: {traceback.format_exc()}")
        return {
            'success': False,
            'error': str(e)
        }


def parse_payload(payload: str) -> Dict[str, Any]:
    """
    Парсит payload из платежа для извлечения информации
    
    Args:
        payload: Строка payload из платежа
        
    Returns:
        Dict с распарсенными данными
    """
    try:
        # Формат: subscription_{tariff}_{user_id}_{timestamp}
        parts = payload.split('_')
        if len(parts) >= 4 and parts[0] == 'subscription':
            return {
                'type': 'subscription',
                'tariff': parts[1],
                'user_id': int(parts[2]),
                'timestamp': parts[3]
            }
    except Exception as e:
        logger.warning(f"Не удалось распарсить payload: {payload}, ошибка: {e}")
    
    return {'type': 'unknown'}


def get_tariff_info(tariff: str) -> Dict[str, Any]:
    """
    Возвращает информацию о тарифе
    
    Args:
        tariff: Тип тарифа
        
    Returns:
        Dict с информацией о тарифе
    """
    # Обновляем конфигурацию перед возвратом
    global TARIFF_CONFIGS
    TARIFF_CONFIGS = get_tariff_configs()
    return TARIFF_CONFIGS.get(tariff, {})


async def get_payment_method_from_yookassa(provider_payment_charge_id: str) -> Optional[str]:
    """
    Получает payment_method_id из YooKassa API по provider_payment_charge_id
    """
    if not all([YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY]):
        logger.warning("YooKassa API credentials не настроены")
        return None
        
    try:
        logger.info(f"Запрашиваем payment_method из YooKassa для: {provider_payment_charge_id}")
        
        # Обертываем синхронный вызов в asyncio.to_thread с timeout
        payment = await asyncio.wait_for(
            asyncio.to_thread(Payment.find_one, provider_payment_charge_id),
            timeout=30.0
        )
        
        logger.info(f"Ответ от YooKassa: статус {payment.status if payment else 'None'}")
        
        if payment and payment.payment_method:
            payment_method_id = payment.payment_method.id
            logger.info(f"✅ Получен payment_method_id: {payment_method_id}")
            
            # Проверяем, что платежный метод сохранен
            saved = getattr(payment.payment_method, 'saved', False)
            logger.info(f"Payment method saved: {saved}")
            
            # В тестовом режиме возвращаем payment_method_id независимо от saved
            is_test_mode = YOOKASSA_SECRET_KEY and YOOKASSA_SECRET_KEY.startswith('test_')
            if is_test_mode:
                logger.info("✅ ТЕСТОВЫЙ РЕЖИМ: возвращаем payment_method_id")
                return payment_method_id
            elif saved:
                logger.info("✅ Платежный метод сохранен для автоплатежей")
                return payment_method_id
            else:
                logger.warning("⚠️ Платежный метод НЕ сохранен для автоплатежей")
                return None
        else:
            logger.warning(f"❌ Payment method не найден для: {provider_payment_charge_id}")
            return None
            
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут при запросе к YooKassa API")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при получении payment_method_id: {e}")
        return None


async def send_payment_notification(
    bot: Bot,
    user_id: int,
    notification_type: str,
    **kwargs
) -> bool:
    """
    Отправляет уведомление пользователю о статусе платежа
    
    Args:
        bot: Экземпляр Telegram бота
        user_id: ID пользователя
        notification_type: Тип уведомления
        **kwargs: Дополнительные параметры
        
    Returns:
        bool: True если уведомление отправлено успешно
    """
    try:
        message_text = ""
        
        if notification_type == "payment_successful":
            tariff = kwargs.get('tariff', 'Неизвестно')
            amount = kwargs.get('amount', 0)
            expires_at = kwargs.get('expires_at')
            is_recurring = kwargs.get('is_recurring', False)

            # Конвертируем amount в рубли
            try:
                amount_value = float(amount) if isinstance(amount, str) else amount
                if amount_value >= 100:  # Если в копейках
                    amount_display = amount_value / 100
                else:  # Если уже в рублях
                    amount_display = amount_value
            except (ValueError, TypeError):
                amount_display = 0
                
            message_text = (
                f"✅ <b>Подписка активирована!</b>\n\n"
                f"🎯 Тариф: {tariff.title()}\n"
                f"💰 Сумма: {amount_display:.2f} ₽\n"
                f"📅 Действует до: {expires_at.strftime('%d.%m.%Y') if expires_at else 'Неизвестно'}\n\n"
                f"Спасибо за покупку! Теперь вы можете пользоваться группой."
            )
            
            if is_recurring:
                message_text += (
                    f"\n\n💳 <b>Карта сохранена для автопродления</b>\n"
                    f"🔄 Подписка будет автоматически продлеваться каждые 30 дней\n"
                    f"🔓 Отменить можно командой /cancel_subscription"
                )

        elif notification_type == "payment_failed":
            message_text = (
                f"❌ <b>Платеж не прошел</b>\n\n"
                f"Попробуйте еще раз или обратитесь в поддержку."
            )
            
        elif notification_type == "subscription_expiring":
            days_left = kwargs.get('days_left', 0)
            tariff = kwargs.get('tariff', 'Неизвестно')
            
            message_text = (
                f"⚠️ <b>Подписка истекает</b>\n\n"
                f"🎯 Тариф: {tariff.title()}\n"
                f"⏰ Осталось дней: {days_left}\n\n"
                f"Продлите подписку, чтобы продолжить пользоваться группой."
            )
            
        elif notification_type == "subscription_expired":
            tariff = kwargs.get('tariff', 'Неизвестно')
            
            message_text = (
                f"⏰ <b>Подписка истекла</b>\n\n"
                f"🎯 Тариф: {tariff.title()}\n\n"
                f"Оформите новую подписку для продолжения использования группы."
            )
        
        if message_text:
            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode='HTML'
            )
            logger.info(f"✅ Уведомление '{notification_type}' отправлено пользователю {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления пользователю {user_id}: {e}")
    
    return False


class TelegramPaymentsManager:
    """Менеджер для работы с подписками через Telegram Payments"""

    def __init__(self, db_session):
        self.db = db_session

    async def process_successful_payment(
        self,
        bot: Bot,
        user_id: int,
        payment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Обрабатывает успешный платеж и активирует подписку
        """
        try:
            payload_info = parse_payload(payment_data.get('invoice_payload', ''))
            if payload_info['type'] != 'subscription':
                logger.error(f"Неизвестный тип payload: {payload_info}")
                return {'success': False, 'error': 'Invalid payload type'}

            tariff = payload_info['tariff']
            
            # payment_method_id получаем из YooKassa
            payment_method_id = await get_payment_method_from_yookassa(
                payment_data.get('provider_payment_charge_id')
            )

            await self._update_user_subscription(
                user_id=user_id,
                tariff=tariff,
                payment_data=payment_data,
                payment_method_id=payment_method_id
            )

            expires_at = datetime.utcnow() + timedelta(days=30)  # 30 дней подписки
            await send_payment_notification(
                bot=bot,
                user_id=user_id,
                notification_type="payment_successful",
                tariff=tariff,
                amount=payment_data.get('total_amount', 0),
                expires_at=expires_at,
                is_recurring=bool(payment_method_id)
            )

            logger.info(f"✅ Успешно обработан платеж для пользователя {user_id}, тариф {tariff}")

            return {
                'success': True,
                'tariff': tariff,
                'expires_at': expires_at
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке успешного платежа: {e}")
            return {'success': False, 'error': str(e)}

    async def _update_user_subscription(
        self,
        user_id: int,
        tariff: str,
        payment_data: Dict[str, Any],
        payment_method_id: Optional[str] = None
    ):
        """Обновляет данные подписки пользователя в БД"""
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            import db
            
            # Получаем пользователя
            user = await db.get_user(user_id)
            if not user:
                # Создаем пользователя если не существует
                await db.add_or_update_user(user_id, {})
                user = await db.get_user(user_id)

            expires_at = datetime.utcnow() + timedelta(days=30)  # 30 дней подписки
            next_billing = datetime.utcnow() + timedelta(days=30)  # Следующее списание

            update_data = {
                'subscription_active': True,
                'subscription_end_date': expires_at,
                'auto_renewal': bool(payment_method_id),
                'left_group': False,
                'payment_history': user.get('payment_history', [])
            }
            
            # Добавляем информацию о платеже в историю
            payment_record = {
                'order_id': f"tg_{user_id}_{int(time.time())}",
                'amount': payment_data.get('total_amount', 0),
                'status': 'completed',
                'created_at': datetime.utcnow().isoformat(),
                'tariff': tariff,
                'payment_method_id': payment_method_id,
                'provider_payment_charge_id': payment_data.get('provider_payment_charge_id')
            }
            
            update_data['payment_history'].append(payment_record)
            
            await db.add_or_update_user(user_id, update_data)
            
            if payment_method_id:
                logger.info(f"✅ Автоплатежи ВКЛЮЧЕНЫ для пользователя {user_id}")
            else:
                logger.warning(f"❌ Автоплатежи НЕ настроены для пользователя {user_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении данных подписки: {e}")


def get_telegram_payments_manager(db_session):
    """Создает экземпляр менеджера Telegram Payments"""
    return TelegramPaymentsManager(db_session)


# Функция для получения цены пользователя (используется в bot.py)
async def get_user_price(user_id: int) -> int:
    """Определяет цену для пользователя на основе его истории платежей"""
    try:
        # Импортируем здесь чтобы избежать циклических импортов
        import db
        
        user = await db.get_user(user_id)
        user_data = user if user else {}
        
        # Обновляем конфигурацию тарифов
        global TARIFF_CONFIGS
        TARIFF_CONFIGS = get_tariff_configs()
        
        if user_data.get('left_group', False):
            # Пользователь возвращается - цена для возвращающихся
            return TARIFF_CONFIGS['returning']['price']
        else:
            # Новый пользователь - обычная цена
            return TARIFF_CONFIGS['regular']['price']
            
    except Exception as e:
        logger.error(f"Ошибка при определении цены для пользователя {user_id}: {e}")
        return TARIFF_CONFIGS['regular']['price']  # дефолтная цена