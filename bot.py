import os
import json
import logging
import datetime
from typing import Dict, List, Optional, Union, Any
import asyncio

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
try:
    # Aiogram 3.x
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
except ImportError:
    # Aiogram 2.x fallback
    from aiogram.contrib.fsm_storage.memory import MemoryStorage
    from aiogram.dispatcher import FSMContext
    from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiohttp import web
from pathlib import Path

# Import database functions
import db
# Import payment provider
from config import get_payment_provider

# Load environment variables
dotenv_path = Path('.') / '.env'
load_dotenv(dotenv_path=dotenv_path, override=True)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')

bot = Bot(token=API_TOKEN)

# Initialize Dispatcher based on aiogram version
try:
    # Try aiogram 2.x initialization (requires bot)
    dp = Dispatcher(bot, storage=MemoryStorage())
except TypeError:
    # Fallback to aiogram 3.x initialization (no bot in init)
    dp = Dispatcher(storage=MemoryStorage())

payment_provider = get_payment_provider()

# States
class UserStates(StatesGroup):
    main_menu = State()
    payment_process = State()

async def _set_state_safe(state: Optional[FSMContext], target_state: Any):
    if state is not None:
        for candidate in (target_state, getattr(target_state, "state", None)):
            if candidate is None:
                continue
            try:
                await state.set_state(candidate)
                return
            except Exception:
                pass
    try:
        await target_state.set()
    except Exception:
        pass


# Helper functions
async def get_user_price(user_id: int) -> float:
    """Get subscription price for user."""
    try:
        with open('price_config.json', 'r') as f:
            config = json.load(f)
        user_prices = config.get('user_prices', {})
        if str(user_id) in user_prices:
            return float(user_prices[str(user_id)])
        return float(config.get('default_price', os.getenv('DEFAULT_SUBSCRIPTION_PRICE', '9.99')))
    except FileNotFoundError:
        return float(os.getenv('DEFAULT_SUBSCRIPTION_PRICE', '9.99'))

async def create_payment_link(user_id: int) -> Dict[str, Any]:
    """Create payment link via provider."""
    try:
        amount = await get_user_price(user_id)
        currency = os.getenv('CURRENCY', 'USD')
        
        result = await payment_provider.create_subscription(
            user_id=user_id,
            amount=amount,
            currency=currency,
            interval='month',
            description='Monthly Subscription',
            metadata={'user_id': user_id}
        )
        
        return {'success': result.success, 'payment_url': result.payment_url, 'payment_id': result.payment_id, 'error': result.error}
    except Exception as e:
        logging.error(f"Error creating payment: {e}")
        return {'success': False, 'error': str(e)}

async def check_subscription_status(user_id: int) -> Dict[str, Any]:
    """Check subscription status from database."""
    try:
        user = await db.get_user(user_id)
        if not user or not user.get('subscription_active'):
            return {'active': False}
        
        end_date = user.get('subscription_end_date')
        if isinstance(end_date, str):
            end_date = datetime.datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        days_left = (end_date - datetime.datetime.now()).days if end_date else 0
        
        return {
            'active': True,
            'end_date': end_date,
            'days_left': days_left,
            'auto_renewal': user.get('auto_renewal', False)
        }
    except Exception as e:
        logging.error(f"Error checking subscription: {e}")
        return {'active': False}

async def send_payment_reminder(user_id: int, days_left: int):
    """Send a payment reminder to the user."""
    price = await get_user_price(user_id)
    message = f"Your subscription will expire in {days_left} day{'s' if days_left > 1 else ''}. "
    message += f"The renewal price is {price} rubles."
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Pay Now", callback_data=f"pay_{price}"))
    
    try:
        await bot.send_message(user_id, message, reply_markup=keyboard)
    except Exception as e:
        logging.error(f"Failed to send reminder to user {user_id}: {e}")

async def check_and_remove_unpaid_users():
    """Check for users who haven't paid in 2 days after expiration and remove them from the group."""
    users_to_kick = await db.get_expired_users_to_kick(days_threshold=2)
    
    for user_id in users_to_kick:
        try:
            # Remove user from the group
            await bot.kick_chat_member(GROUP_ID, user_id)
            # Mark user as left in the database
            await db.set_user_left_group(user_id, True)
            logging.info(f"User {user_id} removed from group due to non-payment")
        except Exception as e:
            # Log error but continue processing other users
            logging.error(f"Failed to remove user {user_id} from group: {e}")

async def scheduled_tasks():
    """Run scheduled tasks."""
    while True:
        try:
            await check_and_remove_unpaid_users()
        except Exception as e:
            logging.error(f"Error in scheduled_tasks: {e}")
        await asyncio.sleep(86400)

# Price configuration commands
# Note: The following handlers use aiogram 2.x syntax which is incompatible with 3.x
# For testing purposes, we'll define them but not register them during import
def register_handlers(dp):
    """Register all bot handlers - call this function to register handlers properly."""
    dp.message.register(set_price_command, commands=['set_price'])
    dp.message.register(cmd_start, commands=['start'])
    dp.callback_query.register(process_subscription, lambda c: c.data == 'subscribe', state=UserStates.main_menu)
    dp.callback_query.register(show_subscription_status, lambda c: c.data == 'subscription_status', state=UserStates.main_menu)
    dp.callback_query.register(cancel_auto_renewal, lambda c: c.data == 'cancel_auto_renewal', state=UserStates.main_menu)
    dp.callback_query.register(back_to_menu, lambda c: c.data == 'back_to_menu', state='*')
    dp.message.register(demo_complete, commands=['demo_complete'])


async def set_price_command(message: types.Message):
    """Handle price updates from admins."""
    try:
        args = message.get_args().split()
        if len(args) != 2:
            raise ValueError("Requires 2 arguments: regular_price returning_price")

        regular = int(args[0])
        returning = int(args[1])

        if regular <= 0 or returning <= 0:
            raise ValueError("Prices must be positive integers")

        with open('price_config.json', 'w') as f:
            json.dump({'regular_price': regular, 'returning_price': returning}, f)

        await message.answer(f"✅ Prices updated:\nRegular: {regular} RUB\nReturning: {returning} RUB")
    except Exception as e:
        logging.error(f"Price update error: {e}")
        await message.answer(f"❌ Error: {str(e)}")

# Command handlers
async def cmd_start(message: types.Message, state: Optional[FSMContext] = None):
    """Handle the /start command - introduce the bot and show main menu."""
    user_id = message.from_user.id
    
    # Check if user exists, if not, add them
    user = await db.get_user(user_id)
    if not user:
        await db.add_or_update_user(user_id, {
            'subscription_active': False,
            'subscription_end_date': None,
            'auto_renewal': False,
            'left_group': False,
            'payment_history': [] # Initialize with empty history
        })
        logging.info(f"New user {user_id} added to database.")
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Subscribe", callback_data="subscribe"),
        InlineKeyboardButton("My Subscription", callback_data="subscription_status"),
        InlineKeyboardButton("Cancel Auto-Renewal", callback_data="cancel_auto_renewal")
    )
    
    await message.answer(
        "Welcome to the Subscription Bot!\n\n"
        "This bot helps you manage your subscription to our group.",
        reply_markup=keyboard
    )
    await _set_state_safe(state, UserStates.main_menu)

async def process_subscription(callback_query: CallbackQuery, state: FSMContext):
    """Process subscription request."""
    user_id = callback_query.from_user.id
    
    result = await create_payment_link(user_id)

    if result['success']:
        amount = await get_user_price(user_id)
        currency = os.getenv('CURRENCY', 'USD')
        
        # Check if demo mode - auto-activate subscription
        if os.getenv('PAYMENT_PROVIDER', 'demo').lower() == 'demo':
            end_date = datetime.datetime.now() + datetime.timedelta(days=30)
            await db.update_user_subscription(
                user_id,
                is_active=True,
                end_date=end_date,
                auto_renewal=True
            )
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("📊 My Subscription", callback_data="subscription_status"))
            keyboard.add(InlineKeyboardButton("Back to Menu", callback_data="back_to_menu"))
            
            message_text = f"✅ Subscription activated!\n\n💰 Amount: {amount} {currency}\n📅 Valid until: {end_date.strftime('%Y-%m-%d')}\n🔄 Auto-renewal: enabled\n\n🎭 Demo mode - no real payment required"
        else:
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("💳 Pay Now", url=result['payment_url']),
                InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")
            )
            message_text = f"💰 Amount: {amount} {currency}\n🔄 Auto-renewal: enabled\n\nClick 'Pay Now' to complete payment."
        
        try:
            await callback_query.message.edit_text(message_text, reply_markup=keyboard)
        except Exception:
            await bot.send_message(user_id, message_text, reply_markup=keyboard)
            
        await _set_state_safe(state, UserStates.main_menu)
    else:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Back to Menu", callback_data="back_to_menu"))
        message_text = f"❌ Error: {result.get('error', 'Unknown error')}\n\nPlease try again later."
        
        try:
            await callback_query.message.edit_text(message_text, reply_markup=keyboard)
        except Exception:
            await bot.send_message(user_id, message_text, reply_markup=keyboard)
        await _set_state_safe(state, UserStates.main_menu)

async def show_subscription_status(callback_query: CallbackQuery, state: FSMContext):
    """Show subscription status."""
    user_id = callback_query.from_user.id
    status = await check_subscription_status(user_id)
    
    if status.get('active'):
        end_date = status.get('end_date')
        end_date_str = end_date.strftime('%d.%m.%Y %H:%M') if end_date else 'Unknown'
        days_left = status.get('days_left', 0)
        
        message = f"🟢 **Subscription Active**\n\n"
        message += f"📅 **Valid until:** {end_date_str}\n"
        message += f"⏰ **Days remaining:** {days_left}\n"
        message += f"🔄 **Auto-renewal:** {'enabled' if status.get('auto_renewal') else 'disabled'}"
    else:
        message = "🔴 **No active subscription**\n\nClick 'Subscribe' to get started."
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Back to Menu", callback_data="back_to_menu"))
    
    try:
        await callback_query.message.edit_text(message, reply_markup=keyboard, parse_mode='Markdown')
    except Exception:
        await bot.send_message(user_id, message, reply_markup=keyboard, parse_mode='Markdown')

async def cancel_auto_renewal(callback_query: CallbackQuery, state: FSMContext):
    """Cancel auto-renewal."""
    user_id = callback_query.from_user.id
    user = await db.get_user(user_id)
    
    if user and user.get('auto_renewal', False):
        try:
            subscription_id = user.get('subscription_id')
            if subscription_id:
                result = await payment_provider.cancel_subscription(subscription_id, "User requested")
                
                if result.success:
                    await db.update_user_subscription(
                        user_id, 
                        is_active=user.get('subscription_active', False), 
                        end_date=user.get('subscription_end_date'), 
                        auto_renewal=False
                    )
                    message = "✅ **Auto-renewal disabled**\n\nSubscription remains active until end date."
                else:
                    message = f"❌ **Error:** {result.error}"
            else:
                await db.update_user_subscription(
                    user_id, 
                    is_active=user.get('subscription_active', False), 
                    end_date=user.get('subscription_end_date'), 
                    auto_renewal=False
                )
                message = "✅ **Auto-renewal disabled**"
        except Exception as e:
            logging.error(f"Error cancelling auto-renewal: {e}")
            message = "❌ **Error**\n\nPlease try again later."
    else:
        message = "ℹ️ **Auto-renewal not active**"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Back to Menu", callback_data="back_to_menu"))
    
    try:
        await callback_query.message.edit_text(message, reply_markup=keyboard, parse_mode='Markdown')
    except Exception:
        await bot.send_message(user_id, message, reply_markup=keyboard, parse_mode='Markdown')

async def back_to_menu(callback_query: CallbackQuery, state: FSMContext):
    """Return to the main menu."""
    await cmd_start(callback_query.message)


async def demo_complete(message: types.Message):
    """Complete demo payment (demo mode only)."""
    if hasattr(payment_provider, 'complete_demo_payment'):
        args = message.get_args().split()
        if args:
            payment_id = args[0]
            result = await payment_provider.complete_demo_payment(payment_id)
            
            if result['success']:
                user_id = message.from_user.id
                end_date = datetime.datetime.now() + datetime.timedelta(days=30)
                
                await db.update_user_subscription(
                    user_id,
                    is_active=True,
                    end_date=end_date,
                    auto_renewal=True
                )
                
                await message.answer(f"✅ Payment completed!\n\nSubscription active until {end_date.strftime('%Y-%m-%d')}")
            else:
                await message.answer(f"❌ {result['error']}")
        else:
            await message.answer("Usage: /demo_complete [payment_id]")
    else:
        await message.answer("Demo mode not active")


async def on_startup(dp: Dispatcher):
    """Bot startup."""
    logging.info(f"Starting bot with {payment_provider.__class__.__name__}...")
    await db.init_db_pool()
    await db.conn.commit()
    asyncio.create_task(scheduled_tasks())
    logging.info("Bot started")

async def on_shutdown(dp: Dispatcher):
    """Bot shutdown."""
    logging.info("Shutting down...")
    await db.close_db_pool()
    logging.info("Bot stopped")


if __name__ == '__main__':
    import asyncio
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    # Create bot instance
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Register handlers
    register_handlers(dp)

    # Run the bot
    asyncio.run(dp.start_polling(bot, skip_updates=True))
