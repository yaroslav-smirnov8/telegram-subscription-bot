"""
Скрипт для проверки конфигурации бота перед запуском
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Загружаем переменные окружения
dotenv_path = Path('.') / '.env'
load_dotenv(dotenv_path=dotenv_path, override=True)

def check_env_variable(name, required=True):
    """Проверяет наличие переменной окружения"""
    value = os.getenv(name)
    if not value:
        if required:
            print(f"❌ ОШИБКА: {name} не установлен в .env файле")
            return False
        else:
            print(f"⚠️  ПРЕДУПРЕЖДЕНИЕ: {name} не установлен (опционально)")
            return True
    else:
        # Скрываем часть значения для безопасности
        if len(value) > 10:
            display_value = value[:10] + "..."
        else:
            display_value = value[:3] + "..."
        print(f"✅ {name}: {display_value}")
        return True

def main():
    print("=" * 60)
    print("Проверка конфигурации Telegram бота")
    print("=" * 60)
    print()

    all_ok = True

    # Обязательные параметры
    print("🔑 Обязательные параметры:")
    all_ok &= check_env_variable("TELEGRAM_API_TOKEN", required=True)
    all_ok &= check_env_variable("TELEGRAM_GROUP_ID", required=True)
    all_ok &= check_env_variable("TELEGRAM_ADMIN_IDS", required=True)
    print()

    # Параметры платежей
    print("💳 Параметры платежей:")
    all_ok &= check_env_variable("PROVIDER_TOKEN", required=True)
    print()

    # URL для редиректа
    print("🔗 URL для редиректа после оплаты:")
    check_env_variable("PAYMENT_SUCCESS_URL", required=False)
    check_env_variable("PAYMENT_FAIL_URL", required=False)
    print()

    # Проверка файлов
    print("📁 Проверка файлов:")
    files_to_check = [
        "bot.py",
        "db.py",
        "requirements.txt"
    ]

    for file in files_to_check:
        if Path(file).exists():
            print(f"✅ {file} найден")
        else:
            print(f"❌ {file} не найден")
            all_ok = False
    print()

    # Проверка базы данных
    print("📊 База данных:")
    db_file = Path("bot_database.db")
    if db_file.exists():
        size = db_file.stat().st_size
        print(f"✅ bot_database.db существует (размер: {size} байт)")
    else:
        print("ℹ️  bot_database.db будет создана при первом запуске")
    print()

    # Итоговый результат
    print("=" * 60)
    if all_ok:
        print("✅ Конфигурация корректна! Можно запустить бота.")
        print()
        print("Для запуска используйте:")
        print("  Windows: python bot.py")
        print("  Linux/macOS: python3 bot.py")
    else:
        print("❌ Обнаружены ошибки в конфигурации!")
        print("Пожалуйста, исправьте ошибки перед запуском бота.")
        sys.exit(1)
    print("=" * 60)

if __name__ == "__main__":
    main()
