"""
Module for integration with Telegram Payments via YooKassa
Adapted for main project with aiogram and SQLite
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from aiogram import Bot, types
from aiogram.types import LabeledPrice
from dotenv import load_dotenv
from yookassa import Configuration, Payment
import uuid
import db

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# YooKassa settings for Telegram Payments
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN')
TEST_PROVIDER_TOKEN = os.getenv('TEST_PROVIDER_TOKEN', PROVIDER_TOKEN)
CURRENCY = os.getenv('CURRENCY', 'RUB')
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')

# YooKassa SDK configuration
if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
    logger.info("YooKassa SDK configured.")
else:
    logger.warning("YOOKASSA_SHOP_ID or YOOKASSA_SECRET_KEY not found. Direct API requests to YooKassa will be unavailable.")

# Check provider token availability
if not PROVIDER_TOKEN or PROVIDER_TOKEN.startswith('ЗАМЕНИТЕ_НА_ВАШ'):
    logger.warning("PROVIDER_TOKEN not configured! Payments will be unavailable.")
    logger.warning("To enable payments, connect YooKassa in BotFather and add PROVIDER_TOKEN to .env")
    PROVIDER_TOKEN = None
    TEST_PROVIDER_TOKEN = None
else:
    logger.info(f"PROVIDER_TOKEN configured: {PROVIDER_TOKEN[:15]}...")
    if "TEST" in PROVIDER_TOKEN:
        logger.info("Using test payment mode")

# Subscription tariffs (import from yookassa_subscriptions)
from yookassa_subscriptions import SUBSCRIPTION_TARIFFS


async def create_yookassa_direct_payment(
    bot: Bot,
    chat_id: int,
    tariff: str,
    user_id: int,
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Creates direct payment via YooKassa API with forced card saving.
    Bypasses Telegram Payments 2FA limitations for auto-payments.
    
    Args:
        bot: Telegram Bot object
        chat_id: User's chat ID
        tariff: Tariff type (basic, standard, premium)
        user_id: User ID
        test_mode: Test mode (default False)
    
    Returns:
        Dict with payment creation result
    """
    try:
        if tariff not in SUBSCRIPTION_TARIFFS:
            return {'success': False, 'error': f'Unknown tariff: {tariff}'}

        config = SUBSCRIPTION_TARIFFS[tariff]
        
        # Create payment via YooKassa API
        payment = Payment.create({
            "amount": {
                "value": f"{config['price'] / 100:.2f}",
                "currency": CURRENCY
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/your_bot"
            },
            "capture": True,
            "save_payment_method": True,  # Force save card
            "description": f"Subscription: {config['name']}",
            "metadata": {
                "user_id": str(user_id),
                "tariff": tariff,
                "chat_id": str(chat_id),
                "type": "subscription",
                "test_mode": str(test_mode)
            }
        }, uuid.uuid4())

        if payment.confirmation:
            # Send payment link to user
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    text="💳 Pay Subscription",
                    url=payment.confirmation.confirmation_url
                )
            )

            message_text = f"""
💳 <b>Subscription Payment</b>

📦 <b>Plan:</b> {config['name']}
💰 <b>Amount:</b> {config['price'] // 100} {CURRENCY}
📝 <b>Description:</b> {config['description']}

Click the button below to pay. After successful payment, your card will be saved for automatic subscription renewal.
            """

            await bot.send_message(
                chat_id=chat_id,
                text=message_text.strip(),
                reply_markup=keyboard,
                parse_mode='HTML'
            )

            # Save payment data
            payment_info = {
                'payment_id': payment.id,
                'tariff': tariff,
                'amount': config['price'],
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'test_mode': test_mode
            }

            await db.add_or_update_user(user_id, {
                'pending_payment': json.dumps(payment_info)
            })

            return {
                'success': True,
                'payment_id': payment.id,
                'confirmation_url': payment.confirmation.confirmation_url
            }
        else:
            return {'success': False, 'error': 'Failed to get payment link'}

    except Exception as e:
        logger.error(f"Error creating YooKassa direct payment: {e}")
        return {'success': False, 'error': str(e)}


async def create_invoice(
    bot: Bot,
    chat_id: int,
    tariff: str,
    user_id: int,
    test_mode: bool = False,
    is_recurring: bool = False
) -> Dict[str, Any]:
    """
    Creates and sends invoice to user via Telegram Payments
    
    Args:
        bot: Telegram bot instance
        chat_id: Chat ID for sending invoice
        tariff: Tariff type (basic, standard, premium)
        user_id: Telegram user ID
        test_mode: Use test mode
        is_recurring: Is payment recurring (for card saving)
        
    Returns:
        Dict with invoice creation result
    """
    try:
        if tariff not in SUBSCRIPTION_TARIFFS:
            return {'success': False, 'error': f'Unknown tariff: {tariff}'}

        config = SUBSCRIPTION_TARIFFS[tariff]
        
        # Select provider token
        provider_token = TEST_PROVIDER_TOKEN if test_mode else PROVIDER_TOKEN
        
        if not provider_token:
            return {'success': False, 'error': 'Provider token not configured'}

        # Create unique payload
        payload = json.dumps({
            'user_id': user_id,
            'tariff': tariff,
            'subscription': True,
            'is_recurring': is_recurring,
            'test_mode': test_mode,
            'timestamp': datetime.now().isoformat()
        })

        # Create price list
        prices = [LabeledPrice(config['name'], config['price'])]

        # Send invoice
        message = await bot.send_invoice(
            chat_id=chat_id,
            title=f"Subscription: {config['name']}",
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

        # Save payment data
        payment_info = {
            'tariff': tariff,
            'amount': config['price'],
            'payload': payload,
            'message_id': message.message_id,
            'status': 'pending',
            'test_mode': test_mode,
            'created_at': datetime.now().isoformat()
        }

        await db.add_or_update_user(user_id, {
            'pending_payment': json.dumps(payment_info)
        })

        logger.info(f"Created invoice for user {user_id}, tariff {tariff}")
        
        return {
            'success': True,
            'message_id': message.message_id,
            'payload': payload,
            'amount': config['price']
        }

    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        return {'success': False, 'error': str(e)}


def parse_payload(payload: str) -> Dict[str, Any]:
    """
    Parses payload from payment to extract information
    
    Args:
        payload: Payload string from payment
        
    Returns:
        Dict with parsed data
    """
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        logger.error(f"Error parsing payload: {payload}")
        return {}


def get_tariff_info(tariff: str) -> Dict[str, Any]:
    """
    Returns tariff information
    
    Args:
        tariff: Tariff type
        
    Returns:
        Dict with tariff information
    """
    return SUBSCRIPTION_TARIFFS.get(tariff, SUBSCRIPTION_TARIFFS['basic'])


def is_test_payment(provider_token: str) -> bool:
    """
    Checks if payment is test
    
    Args:
        provider_token: Provider token
        
    Returns:
        bool: True if test payment
    """
    return "TEST" in provider_token if provider_token else False


async def send_payment_notification(
    bot: Bot,
    user_id: int,
    notification_type: str,
    **kwargs
) -> bool:
    """
    Sends payment status notification to user
    
    Args:
        bot: Telegram bot instance
        user_id: User ID
        notification_type: Notification type
        **kwargs: Additional parameters
        
    Returns:
        bool: True if notification sent successfully
    """
    try:
        messages = {
            'payment_successful': """
🎉 <b>Payment processed successfully!</b>

Your subscription has been activated. Thank you for your payment!
            """,
            'payment_failed': """
❌ <b>Payment processing error</b>

Unfortunately, we couldn't process your payment. Please try again or contact support.
            """,
            'subscription_expiring': f"""
⏰ <b>Subscription expiring</b>

Your subscription expires in {kwargs.get('days_left', 0)} days.
Don't forget to renew your subscription to continue using the service.
            """,
            'subscription_expired': """
⚠️ <b>Subscription expired</b>

Your subscription has expired. To continue using the service, please renew your subscription.
            """,
            'auto_renewal_failed': """
❌ <b>Auto-renewal error</b>

Failed to automatically renew your subscription. Please check your card balance or update payment details.
            """
        }

        message_text = messages.get(notification_type, "Payment notification")
        
        await bot.send_message(
            chat_id=user_id,
            text=message_text.strip(),
            parse_mode='HTML'
        )
        
        return True

    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        return False


class TelegramPaymentsManager:
    """Manager for working with subscriptions via Telegram Payments"""

    def __init__(self):
        pass

    async def process_successful_payment(
        self,
        bot: Bot,
        user_id: int,
        payment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Processes successful payment and activates subscription

        Args:
            bot: Telegram bot instance
            user_id: User ID
            payment_data: Payment data (from pre_checkout_query or webhook)

        Returns:
            Dict with processing result
        """
        try:
            # Parse payload
            payload_str = payment_data.get('invoice_payload', '{}')
            payload = parse_payload(payload_str)
            
            tariff = payload.get('tariff', 'basic')
            
            # Get payment_method_id from YooKassa API if available
            provider_charge_id = payment_data.get('provider_payment_charge_id')
            payment_method_id = None
            
            if provider_charge_id and YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
                payment_method_id = await get_payment_method_from_yookassa(provider_charge_id)

            # Update user subscription
            await self._update_user_subscription(
                user_id, tariff, payment_data, payment_method_id
            )

            # Send successful activation notification
            await send_payment_notification(bot, user_id, 'payment_successful')

            logger.info(f"Successfully processed payment for user {user_id}")
            
            return {
                'success': True,
                'has_auto_renewal': bool(payment_method_id)
            }

        except Exception as e:
            logger.error(f"Error processing successful payment: {e}")
            await send_payment_notification(bot, user_id, 'payment_failed')
            return {'success': False, 'error': str(e)}

    async def _update_user_subscription(
        self,
        user_id: int,
        tariff: str,
        payment_data: Dict[str, Any],
        payment_method_id: Optional[str] = None
    ):
        """Updates user subscription data in DB"""
        try:
            # Calculate subscription end date (30 days)
            expires_at = datetime.now() + timedelta(days=30)
            
            # Prepare payment information
            payment_info = {
                'amount': payment_data.get('total_amount', 0),
                'currency': payment_data.get('currency', CURRENCY),
                'provider_payment_charge_id': payment_data.get('provider_payment_charge_id'),
                'telegram_payment_charge_id': payment_data.get('telegram_payment_charge_id'),
                'tariff': tariff,
                'payment_date': datetime.now().isoformat(),
                'status': 'completed'
            }

            # Update subscription
            await db.update_user_subscription(
                user_id, True, expires_at, bool(payment_method_id), payment_info
            )

            # Save additional user data
            user_data = {
                'current_tariff': tariff,
                'payment_method_id': payment_method_id,
                'next_billing_date': expires_at.isoformat() if payment_method_id else None,
                'billing_attempts': 0
            }

            await db.add_or_update_user(user_id, {'user_data': json.dumps(user_data)})

            logger.info(f"Updated subscription for user {user_id}")

        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            raise

    async def check_subscription_expiry(self, user) -> bool:
        """
        Checks if user's subscription has expired

        Args:
            user: User object from database

        Returns:
            bool: True if subscription active, False if expired
        """
        try:
            if not user.get('subscription_active'):
                return False

            end_date_str = user.get('subscription_end_date')
            if not end_date_str:
                return False

            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            return datetime.now() < end_date

        except Exception as e:
            logger.error(f"Error checking subscription expiry: {e}")
            return False

    async def get_subscription_info(self, user) -> Dict[str, Any]:
        """
        Gets user subscription information

        Args:
            user: User object from database

        Returns:
            Dict with subscription information
        """
        try:
            user_data = json.loads(user.get('user_data', '{}'))
            
            info = {
                'active': user.get('subscription_active', False),
                'end_date': user.get('subscription_end_date'),
                'auto_renewal': user.get('auto_renewal', False),
                'tariff': user_data.get('current_tariff', 'basic'),
                'has_payment_method': bool(user_data.get('payment_method_id'))
            }

            if info['end_date']:
                try:
                    end_date = datetime.fromisoformat(info['end_date'].replace('Z', '+00:00'))
                    days_left = (end_date - datetime.now()).days
                    info['days_left'] = max(0, days_left)
                except:
                    info['days_left'] = 0

            return info

        except Exception as e:
            logger.error(f"Error getting subscription info: {e}")
            return {
                'active': False,
                'end_date': None,
                'auto_renewal': False,
                'tariff': 'basic',
                'has_payment_method': False,
                'days_left': 0
            }


def get_telegram_payments_manager():
    """Creates Telegram Payments manager instance"""
    return TelegramPaymentsManager()


async def check_expiring_subscriptions(bot: Bot) -> int:
    """
    Checks expiring subscriptions and sends notifications

    Args:
        bot: Telegram bot instance

    Returns:
        int: Number of sent notifications
    """
    try:
        # Get users with expiring subscriptions
        users_7_days = await db.get_users_for_reminder([7])
        users_3_days = await db.get_users_for_reminder([3])
        users_1_day = await db.get_users_for_reminder([1])

        notification_count = 0

        # Send notifications
        for users, days_left in [(users_7_days, 7), (users_3_days, 3), (users_1_day, 1)]:
            for user in users:
                try:
                    await send_payment_notification(
                        bot, user['user_id'], 'subscription_expiring', days_left=days_left
                    )
                    notification_count += 1
                except Exception as e:
                    logger.error(f"Error sending notification to user {user['user_id']}: {e}")

        logger.info(f"Sent {notification_count} subscription expiry notifications")
        return notification_count

    except Exception as e:
        logger.error(f"Error checking expiring subscriptions: {e}")
        return 0


async def deactivate_expired_telegram_subscriptions() -> int:
    """
    Deactivates expired Telegram Payments subscriptions

    Returns:
        int: Number of deactivated subscriptions
    """
    try:
        # Get users with expired subscriptions (more than 2 days ago)
        expired_users = await db.get_expired_users_to_kick(2)
        
        deactivated_count = 0
        for user in expired_users:
            try:
                # Deactivate subscription
                await db.update_user_subscription(
                    user['user_id'], False, None, False, {
                        'deactivation_reason': 'subscription_expired',
                        'deactivated_at': datetime.now().isoformat()
                    }
                )
                
                # Clear auto-renewal data
                user_data = {
                    'payment_method_id': None,
                    'auto_renewal': False,
                    'current_tariff': None
                }
                await db.add_or_update_user(user['user_id'], {'user_data': json.dumps(user_data)})
                
                deactivated_count += 1
                
            except Exception as e:
                logger.error(f"Error deactivating subscription for user {user['user_id']}: {e}")

        logger.info(f"Deactivated {deactivated_count} expired subscriptions")
        return deactivated_count

    except Exception as e:
        logger.error(f"Error deactivating expired subscriptions: {e}")
        return 0


async def get_payment_method_from_yookassa(provider_payment_charge_id: str) -> Optional[str]:
    """
    Gets payment_method_id from YooKassa API by provider_payment_charge_id.
    Returns payment_method_id or None if error occurred.
    """
    try:
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            logger.warning("YooKassa API not configured")
            return None
            
        payment = Payment.find_one(provider_payment_charge_id)
        
        if payment and hasattr(payment, 'payment_method') and payment.payment_method:
            return payment.payment_method.id
        else:
            logger.warning(f"Payment method not found for payment {provider_payment_charge_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting payment_method_id from YooKassa: {e}")
        return None


async def create_recurring_payment(user_id: int, tariff: str, amount: int) -> Dict[str, Any]:
    """
    Creates recurring payment via YooKassa API.
    """
    try:
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            return {'success': False, 'error': 'YooKassa API not configured'}

        # Get user data
        user = await db.get_user(user_id)
        if not user:
            return {'success': False, 'error': 'User not found'}

        user_data = json.loads(user.get('user_data', '{}'))
        payment_method_id = user_data.get('payment_method_id')
        
        if not payment_method_id:
            return {'success': False, 'error': 'No saved payment method'}

        config = SUBSCRIPTION_TARIFFS.get(tariff, SUBSCRIPTION_TARIFFS['basic'])
        
        # Create recurring payment
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
            "description": f"Subscription auto-renewal: {config['name']}",
            "metadata": {
                "user_id": str(user_id),
                "tariff": tariff,
                "type": "subscription_renewal"
            }
        }, uuid.uuid4())

        if payment.status == 'succeeded':
            return {
                'success': True,
                'payment_id': payment.id,
                'amount': amount
            }
        else:
            return {
                'success': False,
                'error': f"Payment failed: {payment.status}"
            }

    except Exception as e:
        logger.error(f"Error creating recurring payment: {e}")
        return {'success': False, 'error': str(e)}


async def auto_renew_subscriptions(bot: Bot) -> int:
    """
    Automatically renews subscriptions for users with saved cards
    
    Args:
        bot: Telegram bot instance
        
    Returns:
        int: Number of processed renewal attempts
    """
    try:
        from yookassa_subscriptions import get_subscription_manager
        
        manager = get_subscription_manager()
        return await manager.auto_renew_all_subscriptions(bot)

    except Exception as e:
        logger.error(f"Error auto-renewing subscriptions: {e}")
        return 0
