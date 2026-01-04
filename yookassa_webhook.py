"""
Webhook-обработчик для уведомлений от YooKassa через Telegram Payments
Перенесен из example/yookassa_webhook_handler.py
"""

import logging
import os
import json
from datetime import datetime
from ipaddress import ip_address, ip_network
from aiohttp import web
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем файловое логирование для webhook
webhook_log_handler = logging.FileHandler('yookassa_webhook.log', encoding='utf-8')
webhook_log_handler.setLevel(logging.INFO)
webhook_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
webhook_log_handler.setFormatter(webhook_formatter)
logger.addHandler(webhook_log_handler)

# Отдельный логгер для событий webhook
webhook_events_handler = logging.FileHandler('yookassa_webhook_events.log', encoding='utf-8')
webhook_events_handler.setLevel(logging.INFO)
webhook_events_handler.setFormatter(webhook_formatter)
webhook_events_logger = logging.getLogger('webhook_events')
webhook_events_logger.addHandler(webhook_events_handler)
webhook_events_logger.setLevel(logging.INFO)

# Импорты для обработки платежей
try:
    from telegram_payments import (
        TelegramPaymentsManager,
        get_telegram_payments_manager,
        get_payment_method_from_yookassa
    )
except ImportError:
    logger.warning("telegram_payments module not found, using fallback")
    TelegramPaymentsManager = None
    get_telegram_payments_manager = None
    get_payment_method_from_yookassa = None

# Список доверенных IP-адресов YooKassa
YOOKASSA_TRUSTED_IPS = {
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.154.224/27",
    "2a02:5180:0:1509::/64",
    "2a02:5180:0:2655::/64",
    "2a02:5180:0:1533::/64",
    "2a02:5180:0:2669::/64",
}


async def handle_yookassa_webhook(request: web.Request):
    """Обрабатывает входящие вебхуки от YooKassa"""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Логируем получение webhook
    logger.info("🎯" + "=" * 60)
    logger.info("🎯 === ПОЛУЧЕН WEBHOOK ОТ YOOKASSA ===")
    logger.info(f"🎯 Timestamp: {timestamp}")
    logger.info(f"🎯 Method: {request.method}")
    logger.info(f"🎯 URL: {request.url}")
    logger.info(f"🎯 Headers: {dict(request.headers)}")
    
    webhook_events_logger.info("=" * 80)
    webhook_events_logger.info(f"WEBHOOK RECEIVED: {timestamp}")
    webhook_events_logger.info(f"Method: {request.method}")
    webhook_events_logger.info(f"URL: {request.url}")
    webhook_events_logger.info(f"Remote IP: {request.remote}")
    webhook_events_logger.info(f"Headers: {json.dumps(dict(request.headers), ensure_ascii=False, indent=2)}")
    
    # Проверка IP-адреса (базовая безопасность)
    remote_ip = request.remote
    logger.info(f"🎯 Remote IP: {remote_ip}")
    
    try:
        remote_ip_obj = ip_address(remote_ip)
        trusted = any(remote_ip_obj in ip_network(trusted_ip) for trusted_ip in YOOKASSA_TRUSTED_IPS)
        
        if not trusted:
            logger.warning(f"Получен запрос с недоверенного IP: {remote_ip}")
            # Для отладки временно разрешаем все IP
            logger.warning("ВНИМАНИЕ: Проверка IP отключена для отладки!")
    except ValueError as e:
        logger.error(f"Ошибка при проверке IP {remote_ip}: {e}")

    try:
        # Получаем raw данные для детального логирования
        raw_body = await request.text()
        webhook_events_logger.info(f"Raw request body: {raw_body}")
        
        # Парсим JSON
        data = json.loads(raw_body)
        
        event_type = data.get('event', 'unknown')
        logger.info(f"🎯 Получен вебхук от YooKassa: {event_type}")
        webhook_events_logger.info(f"Event type: {event_type}")
        webhook_events_logger.info(f"Full webhook data: {json.dumps(data, ensure_ascii=False, indent=2)}")

        # Обрабатываем только успешные платежи
        if event_type != 'payment.succeeded':
            logger.info(f"🎯 Событие {event_type} игнорируется (ожидаем payment.succeeded)")
            webhook_events_logger.info(f"Event ignored: {event_type}")
            return web.Response(status=200, text="OK, event ignored")

        payment_object = data.get('object')
        if not payment_object:
            logger.error("В вебхуке отсутствует объект платежа")
            return web.Response(status=400, text="Bad Request: Missing payment object")

        # Для YooKassa API платежей user_id должен быть в metadata
        metadata = payment_object.get('metadata', {})
        user_id = metadata.get('user_id')
        
        logger.info(f"📋 Metadata из платежа: {json.dumps(metadata, ensure_ascii=False)}")
        webhook_events_logger.info(f"Payment metadata: {json.dumps(metadata, ensure_ascii=False, indent=2)}")
        
        if user_id:
            logger.info(f"✅ user_id найден в metadata: {user_id}")
            webhook_events_logger.info(f"User ID found in metadata: {user_id}")
        else:
            # Fallback: пытаемся найти в description
            description = payment_object.get('description', '')
            logger.warning(f"⚠️ user_id не найден в metadata, пробуем description: {description}")
            
            import re
            user_id_match = re.search(r'user_id[:\s]*(\d+)', description)
            if user_id_match:
                user_id = user_id_match.group(1)
                logger.info(f"✅ user_id найден в description: {user_id}")
            else:
                # Последняя попытка: ищем любые цифры
                all_numbers = re.findall(r'\d+', description)
                if all_numbers:
                    user_id = all_numbers[-1]
                    logger.warning(f"⚠️ Используем последнее число как user_id: {user_id}")
        
        if not user_id:
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: user_id не найден!")
            logger.error(f"Full payment object: {json.dumps(payment_object, indent=2, ensure_ascii=False)}")
            return web.Response(status=400, text="Bad Request: Missing user_id")

        # Извлекаем payment_method_id для рекуррентных платежей
        payment_method = payment_object.get('payment_method', {})
        payment_method_id = payment_method.get('id')
        
        logger.info(f"🔑 Payment method info: {json.dumps(payment_method, ensure_ascii=False)}")
        webhook_events_logger.info(f"Payment method: {json.dumps(payment_method, ensure_ascii=False, indent=2)}")
        
        if payment_method_id:
            logger.info(f"✅ Получен payment_method_id: {payment_method_id}")
            saved = payment_method.get('saved', False)
            logger.info(f"Payment method saved: {saved}")
        else:
            logger.warning("⚠️ Payment method ID отсутствует")

        # Для YooKassa API платежей payload строим из metadata
        tariff = metadata.get('tariff', 'regular')  # по умолчанию regular
        
        if not tariff or tariff == 'regular':
            # Определяем тариф на основе пользователя
            import db
            
            # Создаем временную сессию БД
            if not db.conn:
                await db.init_db_pool()
            
            user = await db.get_user(int(user_id))
            if user and user.get('left_group', False):
                tariff = 'returning'
            else:
                tariff = 'basic'  # Changed from 'regular' to 'basic' to match SUBSCRIPTION_TARIFFS
        
        # Создаем payload в нужном формате
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        invoice_payload = f"subscription_{tariff}_{user_id}_{timestamp_str}"
        logger.info(f"✅ Создан payload: {invoice_payload}")
        
        # Данные для обработки платежа
        payment_data = {
            'invoice_payload': invoice_payload,
            'total_amount': payment_object.get('amount', {}).get('value'),
            'currency': payment_object.get('amount', {}).get('currency'),
            'provider_payment_charge_id': payment_object.get('id'),
            'payment_method_id': payment_method_id
        }

        # Создаем менеджер платежей
        import db
        if not db.conn:
            await db.init_db_pool()  # Инициализируем пул БД
        
        try:
            payments_manager = get_telegram_payments_manager()  # БД сессия создается внутри
            
            logger.info(f"🔄 Начинаем обработку платежа для пользователя {user_id}")
            webhook_events_logger.info(f"Starting payment processing for user {user_id}")
            webhook_events_logger.info(f"Payment data: {json.dumps(payment_data, ensure_ascii=False, indent=2)}")
            
            # Создаем Bot объект для отправки уведомлений
            from telegram import Bot
            bot_token = os.getenv('TELEGRAM_API_TOKEN')
            if bot_token:
                bot = Bot(token=bot_token)
                logger.info("Создан Bot объект для webhook")
            else:
                bot = None
                logger.warning("Bot токен не найден - уведомления не будут отправлены")
            
            # Обрабатываем успешный платеж
            result = await payments_manager.process_successful_payment(
                bot=bot, 
                user_id=int(user_id),
                payment_data=payment_data
            )

            if result.get('success'):
                logger.info(f"✅ Webhook успешно обработан для пользователя {user_id}")
                logger.info(f"✅ Результат: {result}")
                webhook_events_logger.info(f"SUCCESS: Payment processed for user {user_id}")
                webhook_events_logger.info(f"Result: {result}")
            else:
                logger.error(f"❌ Ошибка при обработке webhook для пользователя {user_id}: {result.get('error')}")
                webhook_events_logger.error(f"ERROR: Payment processing failed for user {user_id}: {result.get('error')}")

        except Exception as processing_error:
            logger.error(f"❌ Критическая ошибка при обработке платежа: {processing_error}", exc_info=True)
            webhook_events_logger.error(f"CRITICAL ERROR: Payment processing exception: {processing_error}", exc_info=True)
            raise processing_error

        logger.info(f"🎯 Webhook для пользователя {user_id} завершен успешно")
        webhook_events_logger.info(f"Webhook completed successfully for user {user_id}")
        return web.Response(status=200, text="OK")

    except json.JSONDecodeError as json_error:
        logger.error(f"❌ Ошибка декодирования JSON: {json_error}")
        webhook_events_logger.error(f"JSON decode error: {json_error}")
        return web.Response(status=400, text="Bad Request: Invalid JSON")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при обработке вебхука: {e}", exc_info=True)
        webhook_events_logger.error(f"CRITICAL ERROR in webhook handler: {e}", exc_info=True)
        return web.Response(status=500, text="Internal Server Error")


async def health_check(request: web.Request):
    """Проверка работоспособности сервера вебхуков"""
    return web.Response(text="Webhook server is running")


def create_webhook_app():
    """Создает и возвращает приложение aiohttp для вебхуков"""
    app = web.Application()
    app.router.add_post('/webhook/yookassa', handle_yookassa_webhook)
    app.router.add_get('/health', health_check)
    return app


if __name__ == '__main__':
    # Прямой запуск webhook сервера
    port = int(os.getenv('YOOKASSA_WEBHOOK_PORT', 8080))
    
    app = create_webhook_app()
    
    logger.info(f"Запуск сервера вебхуков YooKassa на порту {port}...")
    web.run_app(app, host='0.0.0.0', port=port)