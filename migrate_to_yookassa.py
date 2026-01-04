"""
Скрипт миграции базы данных для поддержки YooKassa
Добавляет новые поля в таблицу users для интеграции с YooKassa
"""

import sqlite3
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Выполняет миграцию базы данных для поддержки YooKassa"""
    
    db_file = 'bot_database.db'
    
    if not os.path.exists(db_file):
        logger.info(f"База данных {db_file} не существует. Создается новая.")
        return create_new_database()
    
    logger.info(f"Выполняем миграцию существующей базы данных {db_file}")
    
    # Создаем резервную копию
    backup_file = f"bot_database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    import shutil
    shutil.copy2(db_file, backup_file)
    logger.info(f"Создана резервная копия: {backup_file}")
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Получаем текущие колонки таблицы users
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        logger.info(f"Существующие колонки: {existing_columns}")
        
        # Список новых колонок для YooKassa
        new_columns = [
            # YooKassa специфичные поля
            ("yookassa_payment_method_id", "TEXT NULL"),
            ("provider_payment_charge_id", "TEXT NULL"), 
            ("telegram_payment_charge_id", "TEXT NULL"),
            ("invoice_payload", "TEXT NULL"),
            ("invoice_message_id", "INTEGER NULL"),
            
            # Статусы подписки
            ("telegram_payments_status", "TEXT NULL"),  # 'active', 'expired', 'pending'
            ("subscription_type", "TEXT DEFAULT 'free'"),  # 'telegram_payments', 'admin_gift', 'free'
            ("payment_status", "TEXT NULL"),  # 'pending', 'paid', 'failed', 'cancelled'
            
            # Финансовая информация
            ("payment_currency", "TEXT DEFAULT 'RUB'"),
            ("payment_amount", "INTEGER NULL"),  # в копейках
            ("subscription_amount", "REAL NULL"),  # в рублях
            ("subscription_discount", "REAL DEFAULT 0.0"),
            
            # Даты и временные метки
            ("last_payment_date", "DATETIME NULL"),
            ("next_billing_date", "DATETIME NULL"),
            ("subscription_created_at", "DATETIME NULL"),
            ("subscription_cancelled_at", "DATETIME NULL"),
            ("subscription_cancelled_reason", "TEXT NULL"),
            
            # Напоминания и уведомления
            ("last_expiry_notification", "DATETIME NULL"),
            ("last_reminder_sent", "DATETIME NULL"),
            ("reminder_count", "INTEGER DEFAULT 0"),
            
            # Счетчики и попытки
            ("billing_attempts", "INTEGER DEFAULT 0"),
            ("failed_payments_count", "INTEGER DEFAULT 0"),
            ("payment_attempts", "INTEGER DEFAULT 0"),
            
            # Персонализация цен
            ("personal_price", "INTEGER NULL"),  # в копейках
            ("price_locked_until", "DATETIME NULL"),
            
            # Дополнительные поля
            ("tariff", "TEXT NULL"),
            ("tariff_purchased_at", "DATETIME NULL"),
            ("subscription_active_manager", "BOOLEAN DEFAULT TRUE"),
            ("subscription_active_user", "BOOLEAN DEFAULT TRUE"),
            ("has_access", "BOOLEAN DEFAULT FALSE"),
        ]
        
        # Добавляем новые колонки, если их нет
        added_columns = 0
        for column_name, column_definition in new_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}")
                    logger.info(f"✅ Добавлена колонка: {column_name}")
                    added_columns += 1
                except sqlite3.Error as e:
                    logger.error(f"❌ Ошибка при добавлении колонки {column_name}: {e}")
            else:
                logger.info(f"⚠️ Колонка {column_name} уже существует")
        
        conn.commit()
        logger.info(f"Миграция завершена. Добавлено {added_columns} новых колонок.")
        
        # Обновляем существующие записи с дефолтными значениями
        update_existing_records(cursor)
        conn.commit()
        
        # Проверяем результат миграции
        cursor.execute("PRAGMA table_info(users)")
        final_columns = [row[1] for row in cursor.fetchall()]
        logger.info(f"Итого колонок после миграции: {len(final_columns)}")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_existing_records(cursor):
    """Обновляет существующие записи с дефолтными значениями"""
    logger.info("Обновляем существующие записи...")
    
    try:
        # Устанавливаем дефолтные значения для существующих пользователей
        cursor.execute("""
            UPDATE users 
            SET 
                subscription_type = CASE 
                    WHEN subscription_active = TRUE THEN 'telegram_payments'
                    ELSE 'free'
                END,
                payment_status = CASE 
                    WHEN subscription_active = TRUE THEN 'paid'
                    ELSE 'free'
                END,
                telegram_payments_status = CASE 
                    WHEN subscription_active = TRUE THEN 'active'
                    ELSE 'inactive'
                END,
                has_access = subscription_active,
                subscription_active_manager = TRUE,
                subscription_active_user = TRUE
            WHERE subscription_type IS NULL OR subscription_type = ''
        """)
        
        rows_updated = cursor.rowcount
        logger.info(f"✅ Обновлено {rows_updated} существующих записей")
        
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при обновлении существующих записей: {e}")


def create_new_database():
    """Создает новую базу данных с полной структурой под YooKassa"""
    logger.info("Создаем новую базу данных с поддержкой YooKassa")
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                
                -- Основная информация о подписке
                subscription_active BOOLEAN DEFAULT FALSE,
                subscription_end_date DATETIME NULL,
                auto_renewal BOOLEAN DEFAULT FALSE,
                left_group BOOLEAN DEFAULT FALSE,
                
                -- YooKassa интеграция
                yookassa_payment_method_id TEXT NULL,
                provider_payment_charge_id TEXT NULL,
                telegram_payment_charge_id TEXT NULL,
                invoice_payload TEXT NULL,
                invoice_message_id INTEGER NULL,
                
                -- Статусы
                telegram_payments_status TEXT NULL,
                subscription_type TEXT DEFAULT 'free',
                payment_status TEXT NULL,
                
                -- Финансы
                payment_currency TEXT DEFAULT 'RUB',
                payment_amount INTEGER NULL,
                subscription_amount REAL NULL,
                subscription_discount REAL DEFAULT 0.0,
                personal_price INTEGER NULL,
                price_locked_until DATETIME NULL,
                
                -- Временные метки
                last_payment_date DATETIME NULL,
                next_billing_date DATETIME NULL,
                subscription_created_at DATETIME NULL,
                subscription_cancelled_at DATETIME NULL,
                subscription_cancelled_reason TEXT NULL,
                
                -- Напоминания
                last_expiry_notification DATETIME NULL,
                last_reminder_sent DATETIME NULL,
                reminder_count INTEGER DEFAULT 0,
                
                -- Счетчики
                billing_attempts INTEGER DEFAULT 0,
                failed_payments_count INTEGER DEFAULT 0,
                payment_attempts INTEGER DEFAULT 0,
                
                -- Дополнительные поля
                tariff TEXT NULL,
                tariff_purchased_at DATETIME NULL,
                subscription_active_manager BOOLEAN DEFAULT TRUE,
                subscription_active_user BOOLEAN DEFAULT TRUE,
                has_access BOOLEAN DEFAULT FALSE,
                
                -- История платежей (JSON)
                payment_history TEXT NULL,
                
                -- Системные поля
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        conn.commit()
        logger.info("✅ Создана новая таблица users с поддержкой YooKassa")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при создании новой базы данных: {e}")
        return False
    finally:
        conn.close()


def test_migration():
    """Тестирует миграцию, создавая тестовые записи"""
    logger.info("Тестирование миграции...")
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        # Создаем тестового пользователя
        test_user_id = 123456789
        cursor.execute("""
            INSERT OR REPLACE INTO users (
                user_id, subscription_active, subscription_type, 
                payment_status, yookassa_payment_method_id
            ) VALUES (?, ?, ?, ?, ?)
        """, (test_user_id, True, 'telegram_payments', 'paid', 'test_payment_method_123'))
        
        # Проверяем, что запись создалась
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (test_user_id,))
        result = cursor.fetchone()
        
        if result:
            logger.info("✅ Тестовая запись создана успешно")
            # Удаляем тестовую запись
            cursor.execute("DELETE FROM users WHERE user_id = ?", (test_user_id,))
            logger.info("✅ Тестовая запись удалена")
        else:
            logger.error("❌ Не удалось создать тестовую запись")
            return False
        
        conn.commit()
        return True
        
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при тестировании: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("🚀 Запуск миграции базы данных для YooKassa...")
    
    # Выполняем миграцию
    if migrate_database():
        print("✅ Миграция базы данных успешно завершена!")
        
        # Тестируем результат
        if test_migration():
            print("✅ Тестирование прошло успешно!")
            print("\n📋 Следующие шаги:")
            print("1. Обновите переменные окружения в .env")
            print("2. Добавьте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")
            print("3. Добавьте PROVIDER_TOKEN от @BotFather")
            print("4. Запустите бота: python bot.py")
        else:
            print("❌ Тестирование не прошло")
    else:
        print("❌ Миграция не удалась")