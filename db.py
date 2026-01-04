import os
import json
import logging
import datetime
from typing import Dict, List, Optional, Tuple, Any

import sqlite3
import aiosqlite
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration - SQLite: No credentials needed
DB_FILE = 'bot_database.db' # SQLite database file

# Global connection pool (for SQLite, it's simpler to manage a single connection)
conn = None
_db_lock = None

async def init_db_pool(): # Renamed to init_db_connection for SQLite
    """Initialize the database connection."""
    global conn, _db_lock
    import asyncio
    
    if _db_lock is None:
        _db_lock = asyncio.Lock()
    
    async with _db_lock:
        if conn is not None:
            return  # Already initialized
        
        try:
            conn = await aiosqlite.connect(DB_FILE) # Connect to SQLite file
            await conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode for better concurrency
            await conn.execute("PRAGMA busy_timeout = 10000;") # Set timeout to 10 seconds (milliseconds)
            logging.info("SQLite database connection established with WAL mode.")
            await setup_database()
        except Exception as e:
            logging.error(f"Failed to create SQLite database connection: {e}")
            raise

async def close_db_pool(): # Renamed to close_db_connection for SQLite
    """Close the database connection."""
    global conn
    if conn:
        await conn.close()
        conn = None  # Reset global connection variable
        logging.info("SQLite database connection closed.")

async def setup_database():
    """Create necessary tables if they don't exist."""
    async with conn.cursor() as cur:
        try:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, -- Changed to INTEGER for SQLite
                    subscription_active BOOLEAN DEFAULT FALSE,
                    subscription_end_date DATETIME NULL,
                    auto_renewal BOOLEAN DEFAULT FALSE,
                    left_group BOOLEAN DEFAULT FALSE,
                    payment_history TEXT NULL, -- TEXT for JSON in SQLite
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- DATETIME for SQLite
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP -- DATETIME for SQLite
                );
            """)
            logging.info("Checked/Created 'users' table in SQLite database.")
        except Exception as e:
            logging.error(f"Error setting up database tables in SQLite: {e}")
            raise

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch user data from the database."""
    if not conn: await init_db_pool() # Ensure connection is initialized
    async with conn.cursor() as cur:
        await cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) # SQLite uses ? placeholders
        row = await cur.fetchone()
        if row:
            columns = [col[0] for col in cur.description]
            user = dict(zip(columns, row))
            for key in ("subscription_active", "auto_renewal", "left_group"):
                if key in user and user[key] is not None:
                    user[key] = bool(user[key])
            if user.get('payment_history'):
                # Deserialize JSON string back to Python list
                try:
                    user['payment_history'] = json.loads(user['payment_history'])
                except (json.JSONDecodeError, TypeError):
                    logging.warning(f"Could not decode payment_history for user {user_id}")
                    user['payment_history'] = [] # Default to empty list on error
            return user
        return None

async def add_or_update_user(user_id: int, data: Dict[str, Any]):
    """Add a new user or update an existing one."""
    if not conn: await init_db_pool()

    # Serialize payment_history to JSON string if present
    if 'payment_history' in data and isinstance(data['payment_history'], list):
        data['payment_history'] = json.dumps(data['payment_history'])

    fields = ', '.join([f"{key} = ?" for key in data.keys()]) # SQLite uses ? placeholders
    values = list(data.values())

    sql = f"""
        INSERT INTO users (user_id, {', '.join(data.keys())})
        VALUES (?, {', '.join(['?'] * len(data))})
        ON CONFLICT(user_id) DO UPDATE SET {', '.join([f"{key}=?" for key in data.keys()])}, updated_at = CURRENT_TIMESTAMP; -- SQLite ON CONFLICT syntax
    """

    async with conn.cursor() as cur:
        try:
            await cur.execute(sql, [user_id] + values + values) # Flatten values list
            await conn.commit()  # Commit changes
            logging.debug(f"User {user_id} added or updated in SQLite.")
        except Exception as e:
            logging.error(f"Error adding/updating user {user_id} in SQLite: {e}")
            raise

async def update_user_subscription(user_id: int, is_active: bool, end_date: Optional[datetime.datetime], auto_renewal: bool, payment_info: Optional[Dict] = None):
    """Update subscription details and optionally add to payment history."""
    if not conn: await init_db_pool()

    user = await get_user(user_id)
    if not user:
        # Should not happen if user exists, but handle defensively
        user_data = {
            'subscription_active': is_active,
            'subscription_end_date': end_date,
            'auto_renewal': auto_renewal,
            'payment_history': [payment_info] if payment_info else []
        }
        await add_or_update_user(user_id, user_data)
        return

    # Update fields
    update_data = {
        'subscription_active': is_active,
        'subscription_end_date': end_date,
        'auto_renewal': auto_renewal
    }

    # Append to payment history if provided
    current_history = user.get('payment_history', [])
    if not isinstance(current_history, list): # Handle potential decoding issues
         current_history = []
    if payment_info:
        current_history.append(payment_info)
    update_data['payment_history'] = json.dumps(current_history) # Serialize back to JSON

    fields = ', '.join([f"{key} = ?" for key in update_data.keys()]) # SQLite uses ? placeholders
    values = list(update_data.values())

    sql = f"UPDATE users SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?" # SQLite uses ? placeholders

    async with conn.cursor() as cur:
        try:
            await cur.execute(sql, values + [user_id]) # Append user_id at the end
            await conn.commit()  # Commit changes
            logging.info(f"Subscription updated for user {user_id} in SQLite.")
        except Exception as e:
            logging.error(f"Error updating subscription for user {user_id} in SQLite: {e}")
            raise

async def set_user_left_group(user_id: int, left: bool):
    """Mark a user as having left the group."""
    if not conn: await init_db_pool()
    sql = "UPDATE users SET left_group = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?" # SQLite uses ? placeholders
    async with conn.cursor() as cur:
        try:
            await cur.execute(sql, (left, user_id))
            await conn.commit()  # Commit changes
            logging.info(f"Set left_group={left} for user {user_id} in SQLite.")
        except Exception as e:
            logging.error(f"Error setting left_group for user {user_id}: {e}")
            raise

async def get_users_for_reminder(days_before_expiry: List[int]) -> List[Dict[str, Any]]:
    """Get users whose subscription expires in specified number of days."""
    if not conn: await init_db_pool()

    # Create date conditions for each day offset
    date_conditions = []
    today = datetime.date.today()
    for days in days_before_expiry:
        target_date = today + datetime.timedelta(days=days)
        # Check for expiry on the target date (ignoring time part for the check)
        date_conditions.append(f"DATE(subscription_end_date) = '{target_date.strftime('%Y-%m-%d')}'")

    if not date_conditions:
        return []

    sql = f"""
        SELECT user_id, subscription_end_date, left_group
        FROM users
        WHERE subscription_active = TRUE
        AND subscription_end_date IS NOT NULL
        AND ({' OR '.join(date_conditions)});
    """

    async with conn.cursor() as cur:
        try:
            await cur.execute(sql)
            users = await cur.fetchall()
            return users if users else []
        except Exception as e:
            logging.error(f"Error fetching users for reminder from SQLite: {e}")
            return [] # Return empty list on error

async def get_expired_users_to_kick(days_threshold: int) -> List[int]:
    """Get users whose subscription expired more than 'days_threshold' ago and haven't renewed."""
    if not conn: await init_db_pool()

    threshold_date = datetime.datetime.now() - datetime.timedelta(days=days_threshold)

    sql = """
        SELECT user_id
        FROM users
        WHERE subscription_active = FALSE
        AND left_group = FALSE -- Only consider those not already marked as left
        AND subscription_end_date IS NOT NULL
        AND subscription_end_date < ?; -- SQLite uses ? placeholders
    """

    async with conn.cursor() as cur:
        try:
            await cur.execute(sql, (threshold_date,)) # Pass threshold_date as parameter
            users = await cur.fetchall()
            return [user['user_id'] for user in users] if users else []
        except Exception as e:
            logging.error(f"Error fetching expired users from SQLite: {e}")
            return [] # Return empty list on error
# Example of how to use the pool in bot.py startup/shutdown
# async def on_startup(dp):
#     await init_db_pool()
#     # ... other startup tasks

# async def on_shutdown(dp):
#     await close_db_pool()
#     # ... other shutdown tasks
