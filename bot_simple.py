"""Simplified subscription bot with pluggable payment providers."""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiohttp import web

import db
from config import get_payment_provider, TELEGRAM_API_TOKEN, CURRENCY, DEFAULT_SUBSCRIPTION_PRICE

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
bot = Bot(token=TELEGRAM_API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
payment_provider = get_payment_provider()

# States
class UserStates(StatesGroup):
    main_menu = State()
    payment_process = State()


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Handle /start command."""
    user_id = message.from_user.id
    
    # Initialize user in database
    user = await db.get_user(user_id)
    if not user:
        await db.add_or_update_user(user_id, {
            'subscription_active': False,
            'subscription_end_date': None,
            'auto_renewal': False
        })
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💳 Subscribe", callback_data="subscribe"),
        InlineKeyboardButton("📊 My Subscription", callback_data="status"),
        InlineKeyboardButton("❌ Cancel Auto-Renewal", callback_data="cancel")
    )
    
    await message.answer(
        "🤖 Welcome to Subscription Bot!\n\n"
        "Manage your subscription easily.",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data == 'subscribe')
async def process_subscribe(callback: types.CallbackQuery):
    """Handle subscription request."""
    user_id = callback.from_user.id
    
    # Create payment via provider
    result = await payment_provider.create_subscription(
        user_id=user_id,
        amount=DEFAULT_SUBSCRIPTION_PRICE,
        currency=CURRENCY,
        interval='month',
        description='Monthly Subscription',
        metadata={'user_id': user_id}
    )
    
    if result.success:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("💳 Pay Now", url=result.payment_url))
        keyboard.add(InlineKeyboardButton("« Back", callback_data="back"))
        
        instructions = result.metadata.get('instructions', '')
        demo_note = "\n\n🎭 Demo Mode: " + instructions if instructions else ""
        
        await callback.message.edit_text(
            f"💰 Subscription: {DEFAULT_SUBSCRIPTION_PRICE} {CURRENCY}/month\n"
            f"🔄 Auto-renewal: enabled{demo_note}",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            f"❌ Error: {result.error}\n\nPlease try again later."
        )


@dp.callback_query_handler(lambda c: c.data == 'status')
async def show_status(callback: types.CallbackQuery):
    """Show subscription status."""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if user and user.get('subscription_active'):
        end_date = user.get('subscription_end_date')
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date)
        
        days_left = (end_date - datetime.now()).days if end_date else 0
        
        message = (
            f"✅ Subscription Active\n\n"
            f"📅 Valid until: {end_date.strftime('%Y-%m-%d')}\n"
            f"⏰ Days left: {days_left}\n"
            f"🔄 Auto-renewal: {'enabled' if user.get('auto_renewal') else 'disabled'}"
        )
    else:
        message = "❌ No active subscription\n\nClick 'Subscribe' to get started."
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("« Back", callback_data="back"))
    
    await callback.message.edit_text(message, reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == 'cancel')
async def cancel_subscription(callback: types.CallbackQuery):
    """Cancel auto-renewal."""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if user and user.get('auto_renewal'):
        subscription_id = user.get('subscription_id')
        if subscription_id:
            result = await payment_provider.cancel_subscription(subscription_id)
            
            if result.success:
                await db.update_user_subscription(
                    user_id,
                    is_active=user.get('subscription_active'),
                    end_date=user.get('subscription_end_date'),
                    auto_renewal=False
                )
                message = "✅ Auto-renewal cancelled\n\nYour subscription remains active until the end date."
            else:
                message = f"❌ Error: {result.error}"
        else:
            message = "❌ No subscription found"
    else:
        message = "ℹ️ Auto-renewal is not active"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("« Back", callback_data="back"))
    
    await callback.message.edit_text(message, reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == 'back')
async def back_to_menu(callback: types.CallbackQuery):
    """Return to main menu."""
    await cmd_start(callback.message)


@dp.message_handler(commands=['demo_complete'])
async def demo_complete(message: types.Message):
    """Complete demo payment (demo mode only)."""
    if hasattr(payment_provider, 'complete_demo_payment'):
        args = message.get_args().split()
        if args:
            payment_id = args[0]
            result = await payment_provider.complete_demo_payment(payment_id)
            
            if result['success']:
                # Activate subscription
                user_id = message.from_user.id
                end_date = datetime.now() + timedelta(days=30)
                
                await db.update_user_subscription(
                    user_id,
                    is_active=True,
                    end_date=end_date,
                    auto_renewal=True
                )
                
                await message.answer(
                    f"✅ Demo payment completed!\n\n"
                    f"Subscription activated until {end_date.strftime('%Y-%m-%d')}"
                )
            else:
                await message.answer(f"❌ {result['error']}")
        else:
            await message.answer("Usage: /demo_complete [payment_id]")
    else:
        await message.answer("Demo mode not active")


async def on_startup(dp: Dispatcher):
    """Initialize on startup."""
    await db.init_db_pool()
    logger.info(f"Bot started with {payment_provider.__class__.__name__}")


async def on_shutdown(dp: Dispatcher):
    """Cleanup on shutdown."""
    await db.close_db_pool()
    logger.info("Bot stopped")


if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
