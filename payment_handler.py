import logging
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackContext
from prodamus_api import get_prodamus_client

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# URL для перенаправления после успешной/неуспешной оплаты
SUCCESS_URL = os.getenv('PAYMENT_SUCCESS_URL', 'https://t.me/your_bot_username')
FAIL_URL = os.getenv('PAYMENT_FAIL_URL', 'https://t.me/your_bot_username')

async def start_payment(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /pay - создает платежную ссылку."""
    user = update.effective_user
    
    # Проверяем, указана ли сумма после команды /pay
    if context.args and len(context.args) > 0:
        try:
            # Получаем сумму из аргументов команды
            amount = float(context.args[0])
            
            # Минимальный платеж 1 рубль
            if amount < 1:
                await update.message.reply_text("Минимальная сумма платежа: 1 рубль")
                return
                
            # Описание платежа
            description = f"Пополнение баланса для пользователя {user.username or user.id}"
            
            # Создаем список товаров для Prodamus
            products = [
                {
                    'name': description,
                    'price': str(amount),
                    'quantity': '1',
                    'tax': {
                        'tax_type': '0',  # Без НДС
                    },
                    'paymentMethod': '1',  # Полная предварительная оплата
                    'paymentObject': '4',  # Услуга
                }
            ]
            
            # Получаем клиент API Prodamus
            prodamus_client = get_prodamus_client()
            
            # Создаем платежную ссылку
            payment_result = prodamus_client.create_payment(
                user_id=user.id,
                amount=amount,
                description=description,
                recurring=False,  # Отключаем рекуррентные платежи по умолчанию
                success_url=SUCCESS_URL,
                fail_url=FAIL_URL,
                products=products  # Передаем список товаров
            )
            
            if "error" in payment_result:
                logger.error(f"Payment creation error: {payment_result['error']}")
                await update.message.reply_text(
                    "Не удалось создать платеж. Пожалуйста, попробуйте позже."
                )
                return
            
            # Создаем встроенную клавиатуру с кнопкой оплаты
            keyboard = [
                [InlineKeyboardButton("Оплатить", url=payment_result["payment_url"])]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение пользователю с кнопкой оплаты
            await update.message.reply_text(
                f"Для оплаты {amount} ₽ нажмите на кнопку ниже:",
                reply_markup=reply_markup
            )
            
            # Сохраняем ID заказа в данных пользователя
            if not context.user_data.get("payments"):
                context.user_data["payments"] = []
                
            context.user_data["payments"].append({
                "order_id": payment_result["order_id"],
                "amount": amount,
                "signature": payment_result.get("signature", ""),
                "timestamp": context.bot.get_bot().get_updates()[0].message.date.timestamp(),
                "status": "pending"
            })
            
        except ValueError:
            await update.message.reply_text(
                "Неверный формат суммы. Используйте команду в формате: /pay 100"
            )
        except Exception as e:
            logger.exception(f"Error in payment processing: {e}")
            await update.message.reply_text(
                "Произошла ошибка при создании платежа. Пожалуйста, попробуйте позже."
            )
    else:
        await update.message.reply_text(
            "Пожалуйста, укажите сумму платежа. Например: /pay 100"
        )

async def start_subscription(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /subscribe - создает платежную ссылку для подписки."""
    user = update.effective_user
    
    # Проверяем, указана ли сумма после команды /subscribe
    if context.args and len(context.args) > 0:
        try:
            # Получаем сумму из аргументов команды
            amount = float(context.args[0])
            
            # Минимальный платеж 1 рубль
            if amount < 1:
                await update.message.reply_text("Минимальная сумма подписки: 1 рубль")
                return
                
            # Описание платежа
            description = f"Ежемесячная подписка для пользователя {user.username or user.id}"
            
            # Получаем клиент API Prodamus
            prodamus_client = get_prodamus_client()
            
            # Создаем платежную ссылку с рекуррентными платежами
            payment_result = prodamus_client.create_payment(
                user_id=user.id,
                amount=amount,
                description=description,
                recurring=True,  # Включаем рекуррентные платежи
                success_url=SUCCESS_URL,
                fail_url=FAIL_URL
            )
            
            if "error" in payment_result:
                logger.error(f"Subscription creation error: {payment_result['error']}")
                await update.message.reply_text(
                    "Не удалось создать подписку. Пожалуйста, попробуйте позже."
                )
                return
            
            # Создаем встроенную клавиатуру с кнопкой оплаты
            keyboard = [
                [InlineKeyboardButton("Оформить подписку", url=payment_result["payment_url"])]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение пользователю с кнопкой оплаты
            await update.message.reply_text(
                f"Для оформления ежемесячной подписки на сумму {amount} ₽ нажмите на кнопку ниже.\n"
                f"С вашей карты будет автоматически списываться {amount} ₽ каждый месяц.",
                reply_markup=reply_markup
            )
            
            # Сохраняем ID заказа в данных пользователя
            if not context.user_data.get("subscriptions"):
                context.user_data["subscriptions"] = []
                
            context.user_data["subscriptions"].append({
                "order_id": payment_result["order_id"],
                "amount": amount,
                "signature": payment_result.get("signature", ""),
                "timestamp": context.bot.get_bot().get_updates()[0].message.date.timestamp(),
                "status": "pending"
            })
            
        except ValueError:
            await update.message.reply_text(
                "Неверный формат суммы. Используйте команду в формате: /subscribe 100"
            )
        except Exception as e:
            logger.exception(f"Error in subscription processing: {e}")
            await update.message.reply_text(
                "Произошла ошибка при создании подписки. Пожалуйста, попробуйте позже."
            )
    else:
        await update.message.reply_text(
            "Пожалуйста, укажите сумму ежемесячной подписки. Например: /subscribe 100"
        )

async def payment_history(update: Update, context: CallbackContext) -> None:
    """Показывает историю платежей пользователя."""
    user = update.effective_user
    
    # Получаем историю платежей из user_data
    payments = context.user_data.get("payments", [])
    subscriptions = context.user_data.get("subscriptions", [])
    
    if not payments and not subscriptions:
        await update.message.reply_text("У вас пока нет платежей и подписок.")
        return
    
    # Формируем список платежей
    history_text = "История ваших платежей и подписок:\n\n"
    
    if payments:
        history_text += "📊 Разовые платежи:\n"
        for i, payment in enumerate(reversed(payments), 1):
            status = "✅ Оплачено" if payment.get("status") == "completed" else "⏳ Ожидает оплаты"
            history_text += f"{i}. {payment['amount']} ₽ - {status}\n"
    
    if subscriptions:
        history_text += "\n📆 Подписки:\n"
        for i, subscription in enumerate(reversed(subscriptions), 1):
            status = "✅ Активна" if subscription.get("status") == "completed" else "⏳ Ожидает оплаты"
            history_text += f"{i}. {subscription['amount']} ₽/месяц - {status}\n"
    
    await update.message.reply_text(history_text)

def register_payment_handlers(application):
    """Регистрирует обработчики платежей."""
    application.add_handler(CommandHandler("pay", start_payment))
    application.add_handler(CommandHandler("subscribe", start_subscription))
    application.add_handler(CommandHandler("history", payment_history))
    
    # Логируем успешную регистрацию обработчиков
    logger.info("Payment handlers registered successfully")
    
    return application 