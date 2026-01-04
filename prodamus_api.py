import os
import json
import logging
import requests
import hashlib
import hmac
import certifi
from typing import Dict, Any, Optional, Union, List
import urllib.parse
import time
from collections.abc import MutableMapping

class ProdamusAPI:
    """Class for interacting with Prodamus payment system API."""
    
    def __init__(self, api_key: str, project_id: Optional[str] = None, verify_ssl: bool = True):
        """Initialize the Prodamus API client.
        
        Args:
            api_key: Your Prodamus API key (secret key)
            project_id: Optional project ID if you have multiple projects
            verify_ssl: Whether to verify SSL certificates (disable only for testing)
        """
        self.api_key = api_key
        self.project_id = project_id
        # В демо-режиме используем demo.payform.ru, в боевом - payform.ru
        self.demo_mode = True  # По умолчанию используем демо-режим
        self.base_url = "https://demo.payform.ru" if self.demo_mode else "https://payform.ru"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        self.verify_ssl = verify_ssl
    
    def create_payment(self, user_id: int, amount: float, description: str, 
                      recurring: bool = False, success_url: Optional[str] = None, 
                      fail_url: Optional[str] = None, products: Optional[List[Dict]] = None,
                      customer_phone: Optional[str] = None) -> Dict[str, Any]:
        """Create a payment link for a user using official Prodamus method.
        
        Args:
            user_id: Telegram user ID
            amount: Payment amount in rubles
            description: Payment description
            recurring: Whether to enable recurring payments
            success_url: URL to redirect after successful payment
            fail_url: URL to redirect after failed payment
            products: List of products to include in payment
            customer_phone: Customer phone number (optional)
            
        Returns:
            Dictionary with payment information including the payment URL
        """
        # Создаем уникальный ID заказа, включающий ID пользователя и временную метку
        timestamp = int(time.time())
        order_id = f"tg_{user_id}_{int(amount)}_{timestamp}"
        
        try:
            # Создаем данные для запроса согласно официальной документации Prodamus
            data = {
                'order_id': order_id,
                'customer_email': f"{user_id}@telegram.user",
                'do': 'pay',
                'demo_mode': 1  # Включаем тестовый режим, используем числовое значение
            }
            
            # Добавляем телефон, если он предоставлен
            if customer_phone:
                data['customer_phone'] = customer_phone
                
            # Для рекуррентных платежей используем параметр subscription вместо products
            if recurring:
                # Используем subscription_id на основе user_id и временной метки
                subscription_id = int(f"{user_id}{timestamp%10000}")
                data['subscription'] = subscription_id
                
                # Также передаем сумму и описание как отдельные параметры
                data['amount'] = amount  # Используем числовое значение
                data['description'] = description
                
                # Добавляем время начала подписки (текущая дата)
                current_time = time.strftime('%Y-%m-%d %H:%M:%S')
                data['subscription_date_start'] = current_time
            else:
                # Для обычных платежей используем products
                if products:
                    # Если передан готовый список товаров, используем его
                    data['products'] = products
                else:
                    # Иначе создаем товар на основе суммы и описания
                    data['products'] = [{
                        'name': description,
                        'price': amount,  # Используем числовое значение
                        'quantity': 1,    # Используем числовое значение
                        'tax': {
                            'tax_type': 0,  # Без НДС по умолчанию, используем числовое значение
                        },
                        'paymentMethod': 1,  # Полная предоплата по умолчанию, используем числовое значение
                        'paymentObject': 4,  # Услуга по умолчанию, используем числовое значение
                    }]
            
            # Добавляем опциональные параметры
            if success_url:
                data['urlSuccess'] = success_url
                
            if fail_url:
                data['urlReturn'] = fail_url
            
            # Создаем подпись для данных и добавляем в запрос
            data['signature'] = self._sign(data)
            
            # Формируем URL платежной формы ТОЧНО как в примере Prodamus
            # Используем urllib.parse.urlencode с результатом http_build_query
            query_string = urllib.parse.urlencode(self._http_build_query(data))
            full_payment_url = f"{self.base_url}/?{query_string}"
            
            logging.info(f"Created payment form URL: {full_payment_url}")
            
            # Возвращаем информацию о платеже
            return {
                "payment_url": full_payment_url,
                "order_id": order_id,
                "amount": amount,
                "description": description,
                "signature": data['signature'],
                "subscription_id": subscription_id if recurring else None
            }
        
        except Exception as e:
            logging.error(f"Error creating payment URL: {e}")
            return {"error": str(e)}
    
    def _sign(self, data: Dict[str, Any]) -> str:
        """Sign the data with the API key using official Prodamus algorithm.
        
        Args:
            data: Data to sign
            
        Returns:
            Signature string
        """
        # Создаем копию данных для подписи, чтобы не изменять оригинальные данные
        sign_data = data.copy()
        
        # Удаляем поле signature если оно есть
        if 'signature' in sign_data:
            del sign_data['signature']
        
        # Переводим все значения в строки - ТОЧНО как в примере Prodamus
        self._deep_int_to_string(sign_data)
        
        # Преобразуем в JSON с сортировкой ключей - ТОЧНО как в примере Prodamus
        # Важно: используем ensure_ascii=False и экранируем слеши
        data_json = json.dumps(sign_data, sort_keys=True, ensure_ascii=False, 
                              separators=(',', ':')).replace("/", "\\/")
        
        # Создаем HMAC подпись с SHA-256
        return hmac.new(self.api_key.encode('utf8'), 
                       data_json.encode('utf8'), 
                       hashlib.sha256).hexdigest()
    
    def _deep_int_to_string(self, dictionary: Dict) -> None:
        """Convert all values in a dictionary to strings recursively.
        
        Args:
            dictionary: Dictionary to convert
        """
        for key, value in dictionary.items():
            if isinstance(value, MutableMapping):
                self._deep_int_to_string(value)
            elif isinstance(value, list) or isinstance(value, tuple):
                for k, v in enumerate(value):
                    self._deep_int_to_string({str(k): v})
            else: 
                dictionary[key] = str(value)
    
    def _http_build_query(self, dictionary: Dict, parent_key: Union[bool, str] = False) -> Dict:
        """Build a query string from a dictionary, identical to the Prodamus example.
        
        Args:
            dictionary: Dictionary to convert
            parent_key: Parent key for nested dictionaries
            
        Returns:
            Dictionary with flattened keys
        """
        items = []
        for key, value in dictionary.items():
            # ТОЧНО как в примере Prodamus - без str() вокруг key
            new_key = str(parent_key) + '[' + key + ']' if parent_key else key
            
            # ТОЧНО как в примере Prodamus - проверка на MutableMapping
            if isinstance(value, MutableMapping):
                items.extend(self._http_build_query(value, new_key).items())
            elif isinstance(value, list) or isinstance(value, tuple):
                # ТОЧНО как в примере Prodamus - рекурсивный вызов для всех элементов
                for k, v in enumerate(value):
                    items.extend(self._http_build_query({str(k): v}, new_key).items())
            else:
                items.append((new_key, value))
                
        return dict(items)
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Get the status of a payment.
        
        Args:
            payment_id: The ID of the payment to check
            
        Returns:
            Dictionary with payment status information
        """
        # В текущей реализации API мы получаем статусы через webhook
        # Этот метод оставлен как заглушка для совместимости
        logging.warning("Method get_payment_status is not implemented in form-based API mode")
        return {"error": "Not implemented in form-based API mode"}
    
    def cancel_recurring(self, user_id: int) -> Dict[str, Any]:
        """Cancel recurring payments for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with cancellation status
        """
        # В текущей реализации API мы не можем отменять подписки программно
        # Этот метод оставлен как заглушка для совместимости
        logging.warning("Method cancel_recurring is not implemented in form-based API mode")
        return {"error": "Not implemented in form-based API mode"}

    def verify_webhook(self, webhook_body: bytes, webhook_signature: str) -> bool:
        """Verify that a webhook came from Prodamus.

        Args:
            webhook_body: The raw request body (bytes).
            webhook_signature: The signature from the 'X-Signature' header.

        Returns:
            Boolean indicating if the webhook is valid.
        """
        try:
            # Декодируем JSON
            data = json.loads(webhook_body.decode('utf-8'))
            
            # Проверяем наличие необходимых полей
            if 'order_id' not in data or 'status' not in data:
                logging.warning("Webhook missing required fields: order_id or status")
                return False
            
            # Проверяем формат order_id (tg_user_id_amount)
            if not data.get('order_id', '').startswith('tg_'):
                logging.warning(f"Webhook received with invalid order ID format: {data.get('order_id')}")
                return False
            
            # Для дополнительной безопасности можно проверить подпись
            if webhook_signature:
                # Если в заголовке есть подпись, проверяем ее
                calculated_signature = self._sign(data)
                if calculated_signature != webhook_signature:
                    logging.warning(f"Invalid webhook signature. Got {webhook_signature}, expected {calculated_signature}")
                    return False
            
            # Webhook прошел все проверки
            return True
            
        except json.JSONDecodeError:
            logging.error("Failed to decode webhook JSON data")
            return False
        except Exception as e:
            logging.error(f"Error during webhook verification: {e}")
            return False

# Example usage
def get_prodamus_client() -> ProdamusAPI:
    """Get a configured Prodamus API client."""
    api_key = os.getenv('PRODAMUS_API_KEY')
    project_id = os.getenv('PRODAMUS_PROJECT_ID')
    
    # По умолчанию отключаем проверку SSL для тестирования
    # В продакшене этот параметр должен быть True
    verify_ssl = os.getenv('PRODAMUS_VERIFY_SSL', 'False').lower() == 'true'
    
    if not api_key:
        raise ValueError("PRODAMUS_API_KEY environment variable is not set")
    
    client = ProdamusAPI(api_key, project_id, verify_ssl)
    
    # Устанавливаем режим (демо или боевой) из переменной окружения
    # По умолчанию используем демо-режим (True)
    client.demo_mode = os.getenv('PRODAMUS_DEMO_MODE', 'True').lower() == 'true'
    
    # Обновляем URL в зависимости от режима
    client.base_url = "https://demo.payform.ru" if client.demo_mode else "https://payform.ru"
    
    logging.info(f"Prodamus API client initialized: demo_mode={client.demo_mode}, verify_ssl={client.verify_ssl}")
    
    return client
