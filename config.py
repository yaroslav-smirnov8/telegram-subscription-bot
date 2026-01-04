"""Configuration and payment provider setup."""

import os
from dotenv import load_dotenv
from payment_providers import PaymentProvider, DemoPaymentProvider

# Load environment variables
load_dotenv()


def get_payment_provider() -> PaymentProvider:
    """Get configured payment provider based on environment settings.
    
    To switch payment providers:
    1. Set PAYMENT_PROVIDER in .env file (demo, stripe, etc.)
    2. Configure provider-specific credentials
    3. Uncomment and return the appropriate provider below
    
    Returns:
        Configured payment provider instance
    """
    provider_type = os.getenv('PAYMENT_PROVIDER', 'demo').lower()
    bot_username = os.getenv('BOT_USERNAME', 'your_bot')
    
    if provider_type == 'demo':
        return DemoPaymentProvider(bot_username=bot_username)
    
    # Uncomment and configure when ready to use Stripe:
    # elif provider_type == 'stripe':
    #     from payment_providers.stripe_example import StripePaymentProvider
    #     return StripePaymentProvider()
    
    # Add more providers here:
    # elif provider_type == 'paypal':
    #     from payment_providers.paypal import PayPalPaymentProvider
    #     return PayPalPaymentProvider()
    
    # Default to demo mode
    return DemoPaymentProvider(bot_username=bot_username)


# Bot configuration
TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')
TELEGRAM_ADMIN_IDS = os.getenv('TELEGRAM_ADMIN_IDS', '').split(',')

# Payment configuration
CURRENCY = os.getenv('CURRENCY', 'USD')
DEFAULT_SUBSCRIPTION_PRICE = float(os.getenv('DEFAULT_SUBSCRIPTION_PRICE', '9.99'))

# Webhook configuration
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', 'localhost')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8080'))
