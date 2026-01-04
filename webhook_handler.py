import logging
import json
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import JSONResponse
from prodamus_api import get_prodamus_client

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(title="Telegram Bot Payment Webhook API")

# Конфигурация для обработчика webhook
WEBHOOK_PATH = "/prodamus/webhook"

# Глобальный объект для хранения временных данных о платежах
# В реальном приложении это должно быть заменено на базу данных
payment_statuses = {}

async def process_webhook_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Обрабатывает данные webhook и возвращает результат.
    
    Args:
        data: Данные webhook от Prodamus
        
    Returns:
        Результат обработки webhook
    """
    try:
        # Проверяем, что в данных есть необходимые поля
        if 'order_id' not in data or 'status' not in data:
            logger.warning("Webhook data missing required fields")
            return {"success": False, "error": "Missing required fields"}
            
        order_id = data['order_id']
        status = data['status']
        
        # Если order_id начинается с tg_, извлекаем user_id
        if order_id.startswith('tg_'):
            try:
                # Ожидаемый формат: tg_user_id_amount_timestamp
                parts = order_id.split('_')
                if len(parts) >= 4:
                    user_id = int(parts[1])
                    
                    # Обновляем статус платежа в нашем хранилище
                    payment_status = {
                        'user_id': user_id,
                        'order_id': order_id,
                        'status': 'completed' if status in ('successful', 'success', 'paid', 'completed') else status,
                        'data': data,
                        'is_recurring': 'subscription_id' in data  # Определяем, является ли это подпиской
                    }
                    
                    # Определяем, является ли это рекуррентным платежом
                    is_recurring = 'subscription_id' in data or data.get('is_recurring') == '1'
                    
                    # Сохраняем в хранилище по ключу order_id
                    payment_statuses[order_id] = payment_status
                    
                    logger.info(f"Updated payment status for order {order_id} to {status} (recurring: {is_recurring})")
                    return {"success": True, "user_id": user_id, "is_recurring": is_recurring}
                else:
                    logger.warning(f"Invalid order_id format: {order_id}")
                    return {"success": False, "error": "Invalid order_id format"}
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing order_id {order_id}: {str(e)}")
                return {"success": False, "error": f"Error parsing order_id: {str(e)}"}
        else:
            logger.warning(f"Non-telegram order_id received: {order_id}")
            return {"success": False, "error": "Non-telegram order_id"}
    except Exception as e:
        logger.exception(f"Error processing webhook: {str(e)}")
        return {"success": False, "error": str(e)}

@app.post(WEBHOOK_PATH)
async def prodamus_webhook(request: Request) -> JSONResponse:
    """Обработчик webhook-уведомлений от Prodamus.
    
    Args:
        request: HTTP запрос от Prodamus
        
    Returns:
        JSONResponse с результатом обработки
    """
    try:
        # Получаем тело запроса
        body = await request.body()
        
        # Получаем заголовок с подписью
        signature = request.headers.get('X-Signature', '')
        
        # Получаем API клиент
        prodamus_client = get_prodamus_client()
        
        # Верифицируем подпись webhook с использованием алгоритма _sign
        is_valid = prodamus_client.verify_webhook(body, signature)
        
        if not is_valid:
            logger.warning("Invalid webhook signature")
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid signature"}
            )
        
        # Парсим JSON из тела запроса
        data = json.loads(body)
        logger.info(f"Received webhook: {data}")
        
        # Обрабатываем данные webhook
        result = await process_webhook_data(data)
        
        # Отвечаем успехом
        return JSONResponse(
            status_code=200,
            content={"status": "success", "data": result}
        )
    except json.JSONDecodeError:
        logger.error("Failed to decode webhook JSON")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON"}
        )
    except Exception as e:
        logger.exception(f"Error processing webhook: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

def get_payment_status(order_id: str) -> Optional[Dict[str, Any]]:
    """Получает статус платежа по order_id.
    
    Args:
        order_id: ID заказа
        
    Returns:
        Статус платежа или None, если платеж не найден
    """
    return payment_statuses.get(order_id)

def get_user_payments(user_id: int) -> list:
    """Получает все платежи пользователя.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        Список платежей пользователя
    """
    user_payments = []
    for payment in payment_statuses.values():
        if payment.get('user_id') == user_id:
            user_payments.append(payment)
    return user_payments

def get_user_subscriptions(user_id: int) -> list:
    """Получает все подписки пользователя.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        Список подписок пользователя
    """
    user_subscriptions = []
    for payment in payment_statuses.values():
        if payment.get('user_id') == user_id and payment.get('is_recurring', False):
            user_subscriptions.append(payment)
    return user_subscriptions 