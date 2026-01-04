#!/usr/bin/env python
"""
Пример использования интеграции с Prodamus для тестовых платежей.
Этот скрипт создает тестовую платежную ссылку и выводит ее в консоль.
"""

import os
import logging
import time
from dotenv import load_dotenv
from prodamus_api import get_prodamus_client

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_payment_example():
    """Пример создания разового платежа."""
    # Создаем тестового пользователя
    user_id = 123456789  # ID тестового пользователя Telegram
    amount = 100.0  # Сумма тестового платежа
    description = "Тестовый платеж для проверки интеграции с Prodamus"
    
    try:
        # Получаем API клиент
        prodamus_client = get_prodamus_client()
        
        # Создаем платежную ссылку
        payment_data = prodamus_client.create_payment(
            user_id=user_id,
            amount=amount,
            description=description,
            recurring=False
        )
        
        if "error" in payment_data:
            logger.error(f"Ошибка создания платежа: {payment_data['error']}")
            print(f"Ошибка создания платежа: {payment_data['error']}")
            return
        
        # Выводим информацию о платеже
        print("\n" + "="*50)
        print("ТЕСТОВЫЙ РАЗОВЫЙ ПЛАТЕЖ СОЗДАН")
        print("="*50)
        print(f"ID заказа: {payment_data['order_id']}")
        print(f"Сумма: {payment_data['amount']} руб.")
        print(f"Описание: {payment_data['description']}")
        print(f"Подпись: {payment_data['signature']}")
        print("\nПлатежная ссылка:")
        print(payment_data['payment_url'])
        print("\nОткройте эту ссылку в браузере, чтобы совершить тестовый платеж.")
        print("Платеж будет обработан в тестовом режиме (demo_mode=1).")
        print("На странице оплаты будет доступна кнопка 'Оплатить в тестовом режиме'.")
        print("="*50)
    
    except Exception as e:
        logger.exception(f"Ошибка при тестировании платежа: {e}")
        print(f"Произошла ошибка: {e}")

def create_subscription_example():
    """Пример создания подписки (рекуррентного платежа)."""
    # Создаем тестового пользователя
    user_id = 123456789  # ID тестового пользователя Telegram
    amount = 100.0  # Сумма тестового платежа
    description = "Тестовая подписка для проверки интеграции с Prodamus"
    
    try:
        # Получаем API клиент
        prodamus_client = get_prodamus_client()
        
        # Создаем платежную ссылку для подписки
        payment_data = prodamus_client.create_payment(
            user_id=user_id,
            amount=amount,
            description=description,
            recurring=True
        )
        
        if "error" in payment_data:
            logger.error(f"Ошибка создания подписки: {payment_data['error']}")
            print(f"Ошибка создания подписки: {payment_data['error']}")
            return
        
        # Выводим информацию о подписке
        print("\n" + "="*50)
        print("ТЕСТОВАЯ ПОДПИСКА СОЗДАНА")
        print("="*50)
        print(f"ID заказа: {payment_data['order_id']}")
        print(f"Сумма: {payment_data['amount']} руб./мес.")
        print(f"Описание: {payment_data['description']}")
        print(f"Подпись: {payment_data['signature']}")
        print("\nСсылка для оформления подписки:")
        print(payment_data['payment_url'])
        print("\nОткройте эту ссылку в браузере, чтобы оформить тестовую подписку.")
        print("Платеж будет обработан в тестовом режиме (demo_mode=1).")
        print("На странице оплаты будет доступна кнопка 'Оплатить в тестовом режиме'.")
        print("="*50)
    
    except Exception as e:
        logger.exception(f"Ошибка при тестировании подписки: {e}")
        print(f"Произошла ошибка: {e}")

def create_advanced_payment_example():
    """Пример создания продвинутого платежа с товарами."""
    # Создаем тестового пользователя
    user_id = 123456789  # ID тестового пользователя Telegram
    
    # Создаем список товаров
    products = [
        {
            'name': 'Товар 1',
            'price': '100',
            'quantity': '1',
            'tax': {
                'tax_type': '0',  # Без НДС
            },
            'paymentMethod': '1',  # Полная предоплата
            'paymentObject': '1',  # Товар
        },
        {
            'name': 'Товар 2',
            'price': '50',
            'quantity': '2',
            'tax': {
                'tax_type': '6',  # НДС 20%
            },
            'paymentMethod': '1',  # Полная предоплата
            'paymentObject': '4',  # Услуга
        }
    ]
    
    # Расчет общей суммы заказа
    total_amount = sum(float(item['price']) * float(item['quantity']) for item in products)
    
    try:
        # Получаем API клиент
        prodamus_client = get_prodamus_client()
        
        # Создаем платежную ссылку с товарами
        payment_data = prodamus_client.create_payment(
            user_id=user_id,
            amount=total_amount,
            description="Тестовый заказ с несколькими товарами",
            recurring=False,
            products=products
        )
        
        if "error" in payment_data:
            logger.error(f"Ошибка создания платежа: {payment_data['error']}")
            print(f"Ошибка создания платежа: {payment_data['error']}")
            return
        
        # Выводим информацию о платеже
        print("\n" + "="*50)
        print("ТЕСТОВЫЙ ЗАКАЗ С ТОВАРАМИ СОЗДАН")
        print("="*50)
        print(f"ID заказа: {payment_data['order_id']}")
        print(f"Общая сумма: {total_amount} руб.")
        print(f"Подпись: {payment_data['signature']}")
        print("\nСостав заказа:")
        for i, product in enumerate(products, 1):
            print(f"  {i}. {product['name']} - {product['price']} руб. x {product['quantity']} шт.")
        
        print("\nПлатежная ссылка:")
        print(payment_data['payment_url'])
        print("\nОткройте эту ссылку в браузере, чтобы совершить тестовый платеж.")
        print("Платеж будет обработан в тестовом режиме (demo_mode=1).")
        print("На странице оплаты будет доступна кнопка 'Оплатить в тестовом режиме'.")
        print("="*50)
    
    except Exception as e:
        logger.exception(f"Ошибка при тестировании платежа: {e}")
        print(f"Произошла ошибка: {e}")

def main():
    """Основная функция для тестирования платежной ссылки."""
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Проверяем наличие API ключа
    if not os.getenv("PRODAMUS_API_KEY"):
        logger.error("PRODAMUS_API_KEY не найден в переменных окружения")
        print("Ошибка: PRODAMUS_API_KEY не найден.")
        print("Создайте файл .env и укажите в нем PRODAMUS_API_KEY=ваш_тестовый_ключ")
        return
    
    while True:
        print("\nВыберите тип тестового платежа:")
        print("1. Разовый платеж")
        print("2. Подписка (рекуррентный платеж)")
        print("3. Заказ с несколькими товарами")
        print("0. Выход")
        
        choice = input("Введите номер: ")
        
        if choice == "1":
            create_payment_example()
        elif choice == "2":
            create_subscription_example()
        elif choice == "3":
            create_advanced_payment_example()
        elif choice == "0":
            print("Тестирование завершено.")
            break
        else:
            print("Неверный выбор. Попробуйте снова.")
        
        # Ожидаем некоторое время, чтобы пользователь мог прочитать результат
        input("\nНажмите Enter для продолжения...")

if __name__ == "__main__":
    main() 