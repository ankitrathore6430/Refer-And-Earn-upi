# bot.py (Definitive, Consolidated, and FINAL Stable Version)
import logging
import asyncio
import json
import math
import aiosqlite
from datetime import date, datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes,
    PicklePersistence
)
from urllib.parse import quote_plus

# =====================================================================================
# 1. CONFIGURATION
# =====================================================================================
BOT_TOKEN = "8279192976:AAGuHbODhn70R1zaV8ETk7chWE_HHxdRGYA" 
ADMIN_ID = 745211839 
ADMIN_USERNAME = "AnkitRathore"

DEFAULT_SETTINGS = {
    "min_withdrawal": 150.0, "referral_bonus": 10.0,
    "task_bonus": 10.0, "daily_bonus": 10.0,
    "hourly_bonus": 2.0
}
DEFAULT_TASKS = [
    {"name": "Task 1: IG Downloader", "bot": "Instagram_vdownloder_bot"},
    {"name": "Task 2: UserInfo Pro", "bot": "Userinfo_pro2_bot"},
    {"name": "Task 3: YT Downloader", "bot": "YouTubeDownloadermp3bot"}
]

DATABASE_NAME = 'bot_database.db'
USERS_PER_PAGE = 10

# Conversation states
GET_BROADCAST_MESSAGE, GET_USER_ID, GET_AMOUNT, CONFIRM_UPDATE = range(1, 5)
UPI_ID = range(5, 6) 
GET_NEW_VALUE = range(6, 7)

# =====================================================================================
# 2. DATABASE FUNCTIONS
# =====================================================================================
async def init_db(application) -> None:
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, username TEXT, 
                balance REAL DEFAULT 0.0, referral_count INTEGER DEFAULT 0, referred_by INTEGER,
                task1_completed BOOLEAN DEFAULT FALSE, task2_completed BOOLEAN DEFAULT FALSE, task3_completed BOOLEAN DEFAULT FALSE,
                is_banned BOOLEAN DEFAULT FALSE, last_bonus_claim DATE,
                task1_started BOOLEAN DEFAULT FALSE, task2_started BOOLEAN DEFAULT FALSE, task3_started BOOLEAN DEFAULT FALSE,
                last_hourly_claim DATETIME
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, first_name TEXT NOT NULL,
                amount REAL NOT NULL, upi_id TEXT NOT NULL, status TEXT DEFAULT 'pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        await db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        await db.commit()
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        tasks_json = json.dumps(DEFAULT_TASKS)
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('tasks', tasks_json))
        await db.commit()

async def get_all_settings():
    settings = {}
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                if row['key'] == 'tasks': settings[row['key']] = json.loads(row['value'])
                else:
                    try: settings[row['key']] = float(row['value'])
                    except ValueError: settings[row['key']] = row['value']
    if 'hourly_bonus' not in settings:
        settings['hourly_bonus'] = DEFAULT_SETTINGS['hourly_bonus']
    return settings

async def update_setting(key, value):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE settings SET value = ? WHERE key = ?", (str(value), key))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def add_user(user_id, first_name, username, referred_by=None):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, first_name, username, referred_by) VALUES (?, ?, ?, ?)", (user_id, first_name, username, referred_by))
        await db.commit()

async def update_balance(user_id, amount_change):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount_change, user_id))
        await db.commit()

async def increment_referral_count(user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def start_task(user_id, task_start_column):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        query = f"UPDATE users SET {task_start_column} = TRUE WHERE user_id = ?"
        await db.execute(query, (user_id,))
        await db.commit()

async def complete_task(user_id, task_id_column):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        query = f"UPDATE users SET {task_id_column} = TRUE WHERE user_id = ?"
        await db.execute(query, (user_id,))
        await db.commit()

async def create_withdrawal_request(user_id, first_name, amount, upi_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("INSERT INTO withdrawal_requests (user_id, first_name, amount, upi_id) VALUES (?, ?, ?, ?)", (user_id, first_name, amount, upi_id))
        await db.commit()
        return cursor.lastrowid

async def get_withdrawal_request(request_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawal_requests WHERE request_id = ?", (request_id,)) as cursor:
            return await cursor.fetchone()

async def update_withdrawal_status(request_id, status):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE withdrawal_requests SET status = ? WHERE request_id = ?", (status, request_id))
        await db.commit()

async def get_all_users_count():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("SELECT COUNT(user_id) FROM users") as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

async def get_all_user_ids():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_banned = FALSE") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def update_last_bonus_claim(user_id, claim_date):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE users SET last_bonus_claim = ? WHERE user_id = ?", (claim_date, user_id))
        await db.commit()

async def update_last_hourly_claim(user_id, claim_time):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE users SET last_hourly_claim = ? WHERE user_id = ?", (claim_time, user_id))
        await db.commit()

async def get_users_paginated(limit=10, offset=0):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, username, first_name, balance FROM users ORDER BY user_id ASC LIMIT ? OFFSET ?", (limit, offset)) as cursor:
            return await cursor.fetchall()
            
async def get_withdrawal_requests_paginated(limit=10, offset=0):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawal_requests ORDER BY request_id DESC LIMIT ? OFFSET ?", (limit, offset)) as cursor:
            return await cursor.fetchall()

async def get_all_withdrawal_requests_count():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("SELECT COUNT(request_id) FROM withdrawal_requests") as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

async def get_pending_withdrawal_count():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("SELECT COUNT(request_id) FROM withdrawal_requests WHERE status = 'pending'") as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

# =====================================================================================
# 3. KEYBOARD LAYOUTS
# =====================================================================================
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Tasks", callback_data='tasks'), InlineKeyboardButton("👥 Refer & Earn", callback_data='refer')],
        [InlineKeyboardButton("💰 My Balance", callback_data='balance'), InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data='daily_bonus'), InlineKeyboardButton("⏰ Hourly Bonus", callback_data='hourly_bonus')],
        [InlineKeyboardButton("ℹ️ Help / FAQ", callback_data='help'), InlineKeyboardButton("✉️ Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 View Stats", callback_data='admin_view_stats')],
        [InlineKeyboardButton("👥 List Users", callback_data='admin_list_users'), InlineKeyboardButton("📋 List Requests", callback_data='admin_list_requests')],
        [InlineKeyboardButton("💰 Update Balance", callback_data='admin_start_balance_update'), InlineKeyboardButton("📣 Broadcast", callback_data='admin_start_broadcast')],
        [InlineKeyboardButton("⚙️ Bot Settings", callback_data='admin_settings')]
    ]
    return InlineKeyboardMarkup(keyboard)

def settings_keyboard(settings):
    keyboard = [
        [InlineKeyboardButton(f"Refer Bonus: ₹{settings['referral_bonus']}", callback_data="settings_edit_referral_bonus")],
        [InlineKeyboardButton(f"Task Bonus: ₹{settings['task_bonus']}", callback_data="settings_edit_task_bonus")],
        [InlineKeyboardButton(f"Daily Bonus: ₹{settings['daily_bonus']}", callback_data="settings_edit_daily_bonus")],
        [InlineKeyboardButton(f"Hourly Bonus: ₹{settings['hourly_bonus']}", callback_data="settings_edit_hourly_bonus")],
        [InlineKeyboardButton(f"Min Withdrawal: ₹{settings['min_withdrawal']}", callback_data="settings_edit_min_withdrawal")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data='admin_panel')]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_main_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data='main_menu')]])

def back_to_admin_panel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data='admin_panel')]])

# =====================================================================================
# 4. HANDLERS (ALL IN ONE FILE)
# =====================================================================================

# --- Utility Handlers ---
async def post_init(app: Application) -> None:
    await init_db(app)
    app.bot_data['settings'] = await get_all_settings()
    logging.info("Bot settings loaded from database.")

async def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# --- User Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db_user = await get_user(user.id)
    if not db_user:
        referrer_id = None
        if context.args and len(context.args) > 0 and context.args[0].isdigit():
            potential_referrer_id = int(context.args[0])
            if await get_user(potential_referrer_id) and potential_referrer_id != user.id:
                referrer_id = potential_referrer_id
                referral_bonus = context.bot_data['settings']['referral_bonus']
                await increment_referral_count(referrer_id)
                await update_balance(referrer_id, referral_bonus)
                try:
                    await context.bot.send_message(chat_id=referrer_id, text=f"🎉 New Referral! {user.first_name} joined. You've earned ₹{referral_bonus:.2f}!")
                except Exception as e:
                    logging.warning(f"Could not notify referrer {referrer_id}: {e}")
        await add_user(user.id, user.first_name, user.username, referrer_id)
        await update.message.reply_text(f"Welcome, {user.first_name}!")
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = "👇 Please choose an option from the menu below:"
    reply_markup = main_menu_keyboard()
    if update.callback_query:
        await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=message_text, reply_markup=reply_markup)

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    tasks = context.bot_data['settings']['tasks']
    task_bonus = context.bot_data['settings']['task_bonus']
    message = f"Complete tasks to earn ₹{task_bonus:.2f} for each one!\n\n"
    keyboard = []
    for i, task in enumerate(tasks):
        completed_col = f"task{i+1}_completed"
        started_col = f"task{i+1}_started"
        status_icon = "✅" if db_user[completed_col] else ("⏳" if db_user[started_col] else "❌")
        message += f"{status_icon} {task['name']}\n"
        if not db_user[completed_col]:
            if not db_user[started_col]:
                keyboard.append([InlineKeyboardButton(f"➡️ Start Task {i+1}", callback_data=f"start_task_{i}")])
            else:
                keyboard.append([InlineKeyboardButton(f"💰 Confirm Completion for Task {i+1}", callback_data=f"claim_task_{i}")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data='main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query: await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup)
    else: await update.message.reply_text(text=message, reply_markup=reply_markup)

async def start_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, task_index: int):
    query = update.callback_query
    await query.answer()
    tasks = context.bot_data['settings']['tasks']
    task = tasks[task_index]
    started_col = f"task{task_index+1}_started"
    await start_task(query.from_user.id, started_col)
    message = (f"Great! You have started **{task['name']}**.\n\n"
               "**Step 1:** Click the button below to go to the bot and interact with it.\n"
               "**Step 2:** Come back here and click 'Back to Task List' to confirm your task.")
    keyboard = [
        [InlineKeyboardButton(f"🚀 Go to @{task['bot']}", url=f"https://t.me/{task['bot']}")],
        [InlineKeyboardButton("⬅️ Back to Task List", callback_data='tasks')]
    ]
    await query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def claim_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_index: int) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    task_bonus = context.bot_data['settings']['task_bonus']
    completed_col = f"task{task_index+1}_completed"
    started_col = f"task{task_index+1}_started"
    if not db_user[started_col]:
        await query.answer("Error: Please 'Start Task' before confirming.", show_alert=True); return
    if db_user[completed_col]:
        await query.answer("You have already claimed this task!", show_alert=True); return
    await complete_task(user_id, completed_col)
    await update_balance(user_id, task_bonus)
    await query.answer(f"✅ Confirmed! ₹{task_bonus:.2f} added.", show_alert=True)
    await show_tasks(update, context)

async def show_referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    db_user = await get_user(user_id)
    referral_bonus = context.bot_data['settings']['referral_bonus']
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    # Text content for the shared message
    share_text_content = f"Hey! I'm earning money with this bot and thought you'd like it too. 💰\n\nIt's free, simple, and you can start right away.\n\nJoin me here 👇\n{referral_link}"
    
    # URL-encode the text and create a standard Telegram share link
    encoded_text = quote_plus(share_text_content)
    telegram_share_url = f"https://t.me/share/url?text={encoded_text}"
    
    # Message displayed to the user in the bot
    message = (f"*👥 Refer & Earn*\n\n"
               f"*Share your personal link with friends. You will earn ₹{referral_bonus:.2f} for every single friend who joins through it!*\n\n"
               f"*Your Link:*\n`{referral_link}`\n\n"
               f"*You have referred {db_user['referral_count']} friends so far.*")
               
    # The keyboard now uses a standard URL button for sharing
    keyboard = [[InlineKeyboardButton("🚀 Share with a Friend", url=telegram_share_url)], [InlineKeyboardButton("⬅️ Back to Menu", callback_data='main_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query: await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
    else: await update.message.reply_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    balance = (await get_user(update.effective_user.id))['balance']
    message = f"💰 *Your Current Balance*\n\nAvailable Balance: *₹{balance:.2f}*"
    if update.callback_query: await update.callback_query.edit_message_text(text=message, reply_markup=back_to_main_menu_keyboard(), parse_mode='Markdown')
    else: await update.message.reply_text(text=message, reply_markup=back_to_main_menu_keyboard(), parse_mode='Markdown')

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    min_withdrawal = context.bot_data['settings']['min_withdrawal']
    message = f"ℹ️ *Help & FAQ*\n\n*How do I earn?*\n- Complete tasks, refer friends, and claim your daily bonus.\n\n*How do I withdraw?*\n- Reach the minimum balance of ₹{min_withdrawal:.2f} and use the withdraw button."
    if update.callback_query: await update.callback_query.edit_message_text(text=message, reply_markup=back_to_main_menu_keyboard(), parse_mode='Markdown')
    else: await update.message.reply_text(text=message, reply_markup=back_to_main_menu_keyboard(), parse_mode='Markdown')

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    daily_bonus_amount = context.bot_data['settings']['daily_bonus']
    last_claim_str = db_user['last_bonus_claim']
    today = date.today()
    message_to_user = ""
    if last_claim_str and date.fromisoformat(last_claim_str) == today:
        message_to_user = "You have already claimed your daily bonus today!"
    else:
        await update_balance(user_id, daily_bonus_amount)
        await update_last_bonus_claim(user_id, today)
        message_to_user = f"🎉 Congratulations! You've received your daily bonus of ₹{daily_bonus_amount:.2f}."
    if query: await query.answer(message_to_user, show_alert=True)
    else: await update.message.reply_text(message_to_user)

async def hourly_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    hourly_bonus_amount = context.bot_data['settings']['hourly_bonus']
    now = datetime.now()
    message_to_user = ""
    if 'last_hourly_claim' in db_user.keys() and db_user['last_hourly_claim']:
        last_claim_str = db_user['last_hourly_claim']
        last_claim_time = datetime.fromisoformat(last_claim_str)
        time_since_claim = now - last_claim_time
        if time_since_claim < timedelta(hours=1):
            remaining_time = timedelta(hours=1) - time_since_claim
            minutes_left = math.ceil(remaining_time.total_seconds() / 60)
            message_to_user = f"Please wait {minutes_left} more minutes to claim your next hourly bonus."
    if not message_to_user:
        await update_balance(user_id, hourly_bonus_amount)
        await update_last_hourly_claim(user_id, now)
        message_to_user = f"🎉 You've received your hourly bonus of ₹{hourly_bonus_amount:.2f}!"
    if update.callback_query:
        await update.callback_query.answer(message_to_user, show_alert=True)
    else:
        await update.message.reply_text(message_to_user)

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = f"For any help or support, you can contact the admin directly by messaging @{ADMIN_USERNAME}."
    keyboard = [[InlineKeyboardButton("✉️ Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]]
    await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    balance = (await get_user(user_id))['balance']
    min_withdrawal = context.bot_data['settings']['min_withdrawal']
    message = f"Sorry, you need at least ₹{min_withdrawal:.2f} to withdraw."
    if balance < min_withdrawal:
        if update.callback_query: await update.callback_query.answer(message, show_alert=True)
        else: await update.message.reply_text(message)
        return ConversationHandler.END
    message = "Please enter your UPI ID to proceed:"
    if update.callback_query: await update.callback_query.edit_message_text(text=message)
    else: await update.message.reply_text(message)
    return UPI_ID

async def get_upi_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    upi_id = update.message.text.strip()
    if '@' not in upi_id or len(upi_id) < 5:
        await update.message.reply_text("That is not a valid UPI ID. Please try again or type /cancel."); return UPI_ID
    balance = (await get_user(user.id))['balance']
    request_id = await create_withdrawal_request(user.id, user.first_name, balance, upi_id)
    await update_balance(user.id, -balance)
    await update.message.reply_text(f"✅ Your withdrawal request for ₹{balance:.2f} has been submitted.")
    admin_message = f"🔔 *New Withdrawal Request* `#{request_id}`\n\nUser: {user.first_name} (`{user.id}`)\nAmount: *₹{balance:.2f}*\nUPI ID: `{upi_id}`"
    admin_kb = [[InlineKeyboardButton("✅ Approve", callback_data=f'admin_approve_{request_id}'), InlineKeyboardButton("❌ Reject", callback_data=f'admin_reject_{request_id}')]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=InlineKeyboardMarkup(admin_kb), parse_mode='Markdown')
    await show_main_menu(update, context)
    return ConversationHandler.END

# --- Admin Handlers ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        if update.message: await update.message.reply_text("You are not authorized.")
        return
    message_text = "👑 *Admin Panel*\n\nWelcome, Admin! Please choose an action."
    reply_markup = admin_panel_keyboard()
    if update.callback_query: await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    total_users = await get_all_users_count()
    total_pending = await get_pending_withdrawal_count()
    stats_text = (f"📊 *Bot Statistics*\n\n"
                  f"👥 Total Users: *{total_users}*\n"
                  f"⏳ Pending Withdrawals: *{total_pending}*")
    if update.callback_query: await update.callback_query.edit_message_text(text=stats_text, parse_mode='Markdown', reply_markup=back_to_admin_panel_keyboard())
    else: await update.message.reply_text(text=stats_text, parse_mode='Markdown')

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> None:
    if not await is_admin(update.effective_user.id): return
    offset = (page - 1) * USERS_PER_PAGE
    users = await get_users_paginated(limit=USERS_PER_PAGE, offset=offset)
    total_users = await get_all_users_count()
    total_pages = math.ceil(total_users / USERS_PER_PAGE) if total_users > 0 else 1
    if not users:
        text = "There are no users."
        if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=back_to_admin_panel_keyboard())
        else: await update.message.reply_text(text, reply_markup=back_to_admin_panel_keyboard())
        return
    message_text = "👥 *User List*\n\n"
    for i, user in enumerate(users):
        user_identifier = f"@{user['username']}" if user['username'] else f"{user['first_name']}"
        message_text += f"**{offset + i + 1}.** `{user['user_id']}`\n   - {user_identifier}\n   - Balance: **₹{user['balance']:.2f}**\n\n"
    row = []
    if page > 1: row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_list_users_{page - 1}"))
    if total_pages > 1: row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="noop"))
    if page < total_pages: row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_list_users_{page + 1}"))
    keyboard = [row, [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data='admin_panel')]]
    if update.callback_query: await update.callback_query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else: await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def list_withdrawal_requests(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> None:
    if not await is_admin(update.effective_user.id): return
    offset = (page - 1) * USERS_PER_PAGE
    requests = await get_withdrawal_requests_paginated(limit=USERS_PER_PAGE, offset=offset)
    total_requests = await get_all_withdrawal_requests_count()
    total_pages = math.ceil(total_requests / USERS_PER_PAGE) if total_requests > 0 else 1

    query = update.callback_query
    keyboard = [] # Initialize the keyboard

    if not requests:
        text = "There are no withdrawal requests."
        if query: await query.edit_message_text(text, reply_markup=back_to_admin_panel_keyboard())
        else: await update.message.reply_text(text, reply_markup=back_to_admin_panel_keyboard())
        return

    message_text = "📋 *Withdrawal Request History*\n\n"
    for req in requests:
        status_icon = "⏳" if req['status'] == 'pending' else ("✅" if req['status'] == 'approved' else "❌")
        timestamp = req['timestamp'].split('.')[0]
        message_text += (f"{status_icon} *Request #{req['request_id']}* ({req['status'].capitalize()})\n"
                         f"   - **User:** {req['first_name']} (`{req['user_id']}`)\n"
                         f"   - **Amount:** ₹{req['amount']:.2f}\n"
                         f"   - **UPI ID:** `{req['upi_id']}`\n"
                         f"   - **Date:** {timestamp}\n\n")
        
        # --- NEW FEATURE ---
        # If the request is pending, add Approve/Reject buttons for it
        if req['status'] == 'pending':
            approve_button = InlineKeyboardButton(f"✅ Approve #{req['request_id']}", callback_data=f"admin_approve_{req['request_id']}")
            reject_button = InlineKeyboardButton(f"❌ Reject #{req['request_id']}", callback_data=f"admin_reject_{req['request_id']}")
            keyboard.append([approve_button, reject_button])

    # Add pagination buttons
    pagination_row = []
    if page > 1: pagination_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_list_requests_{page - 1}"))
    if total_pages > 1: pagination_row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="noop"))
    if page < total_pages: pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_list_requests_{page + 1}"))
    if pagination_row: keyboard.append(pagination_row)

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query: await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def start_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = "Please send the message you want to broadcast.\n\nType /cancel to abort."
    if not await is_admin(update.effective_user.id): return ConversationHandler.END
    if update.callback_query:
        await update.callback_query.edit_message_text(text=message)
    else:
        await update.message.reply_text(message)
    return GET_BROADCAST_MESSAGE
async def get_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_ids = await get_all_user_ids()
    await update.message.reply_text(f"✅ Starting broadcast to {len(user_ids)} users...")
    success, fail = 0, 0
    for user_id in user_ids:
        try: await context.bot.send_message(chat_id=user_id, text=update.message.text); success += 1
        except Exception as e: fail += 1; logging.warning(f"Broadcast failed for {user_id}: {e}")
    await update.message.reply_text(f"Broadcast finished.\n\nSent: {success} | Failed: {fail}")
    await admin_panel(update, context)
    return ConversationHandler.END

async def start_balance_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = "Please send the Telegram User ID of the user.\n\nType /cancel to abort."
    if not await is_admin(update.effective_user.id): return ConversationHandler.END
    if update.callback_query:
        await update.callback_query.edit_message_text(text=message)
    else:
        await update.message.reply_text(message)
    return GET_USER_ID
async def get_target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: user_id = int(update.message.text)
    except ValueError: await update.message.reply_text("Invalid ID. Please send a numeric ID or /cancel."); return GET_USER_ID
    target_user = await get_user(user_id)
    if not target_user: await update.message.reply_text("User not found. Try again or /cancel."); return GET_USER_ID
    context.user_data.update({'target_user_id': user_id, 'target_user_name': target_user['first_name']})
    await update.message.reply_text(f"✅ User: {target_user['first_name']}.\nEnter amount to add or subtract (e.g., `50` or `-10`).")
    return GET_AMOUNT
async def get_update_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: amount = float(update.message.text)
    except ValueError: await update.message.reply_text("Invalid amount. Try again or /cancel."); return GET_AMOUNT
    context.user_data['update_amount'] = amount
    user_id, user_name = context.user_data['target_user_id'], context.user_data['target_user_name']
    action_text = "add" if amount >= 0 else "subtract"
    kb = [[InlineKeyboardButton("✅ Yes, I am sure", callback_data='confirm_update_yes'), InlineKeyboardButton("❌ No, cancel", callback_data='confirm_update_no')]]
    await update.message.reply_text(f"⚠️ *Final Confirmation*\n\nAre you sure you want to *{action_text} ₹{abs(amount):.2f}* to *{user_name} ({user_id})*?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return CONFIRM_UPDATE
async def process_balance_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm_update_yes':
        user_id, amount = context.user_data['target_user_id'], context.user_data['update_amount']
        await update_balance(user_id, amount)
        await query.edit_message_text(text=f"✅ Success! Balance updated by ₹{amount:.2f}.")
        try: await context.bot.send_message(chat_id=user_id, text=f"🔔 Admin Update: Your balance has been manually adjusted by *₹{amount:.2f}*.", parse_mode='Markdown')
        except Exception as e: await query.message.reply_text(f"Note: Could not notify user. Error: {e}")
    else: await query.edit_message_text(text="Operation cancelled.")
    context.user_data.clear()
    await admin_panel(update, context)
    return ConversationHandler.END

async def show_settings_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings_data = context.bot_data['settings']
    message_text = "⚙️ *Bot Settings*\n\nSelect a value to edit. Changes take effect immediately."
    await query.edit_message_text(text=message_text, reply_markup=settings_keyboard(settings_data), parse_mode='Markdown')
    
async def start_setting_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    setting_key = query.data.replace("settings_edit_", "")
    context.user_data['setting_to_edit'] = setting_key
    current_value = context.bot_data['settings'][setting_key]
    await query.edit_message_text(
        text=f"Editing *{setting_key.replace('_', ' ').title()}*.\n"
             f"Current value: `{current_value}`\n\n"
             "Please send the new numeric value, or /cancel to go back.",
        parse_mode='Markdown'
    )
    return GET_NEW_VALUE
async def get_new_setting_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_value_str = update.message.text
    setting_key = context.user_data.get('setting_to_edit')
    if not setting_key:
        await update.message.reply_text("An error occurred. Please start over.", reply_markup=back_to_admin_panel_keyboard())
        return ConversationHandler.END
    try:
        new_value = float(new_value_str)
        if new_value < 0:
            await update.message.reply_text("Value cannot be negative. Please try again or /cancel."); return GET_NEW_VALUE
    except ValueError:
        await update.message.reply_text("Invalid input. Please send a numeric value or /cancel."); return GET_NEW_VALUE
    await update_setting(setting_key, new_value)
    context.bot_data['settings'][setting_key] = new_value
    logging.info(f"Admin {update.effective_user.id} updated setting '{setting_key}' to '{new_value}'")
    await update.message.reply_text(f"✅ Success! *{setting_key.replace('_', ' ').title()}* has been updated to `{new_value}`.", parse_mode='Markdown')
    context.user_data.clear()
    await admin_panel(update, context)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.")
    await show_main_menu(update, context)
    return ConversationHandler.END
async def cancel_admin_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Admin operation cancelled.")
    context.user_data.clear()
    await admin_panel(update, context)
    return ConversationHandler.END

async def user_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    if data == 'main_menu': await show_main_menu(update, context)
    elif data == 'tasks': await show_tasks(update, context)
    elif data == 'refer': await show_referral_info(update, context)
    elif data == 'balance': await show_balance(update, context)
    elif data == 'help': await show_help(update, context)
    elif data == 'daily_bonus': await daily_bonus(update, context)
    elif data == 'hourly_bonus': await hourly_bonus(update, context)
    elif data.startswith('start_task_'):
        await start_task_handler(update, context, task_index=int(data.split('_')[-1]))
    elif data.startswith('claim_task_'):
        await claim_task(update, context, task_index=int(data.split('_')[-1]))
    else:
        await query.answer()

async def admin_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    if not await is_admin(update.effective_user.id):
        await query.answer("You are not authorized.", show_alert=True); return
    
    if data == 'admin_panel': await admin_panel(update, context)
    elif data == 'admin_view_stats': await admin_stats(update, context)
    elif data.startswith('admin_list_users'):
        parts = data.split('_')
        page = int(parts[-1]) if len(parts) > 2 and parts[-1].isdigit() else 1
        await list_users(update, context, page=page)
    elif data.startswith('admin_list_requests'):
        parts = data.split('_')
        page = int(parts[-1]) if len(parts) > 2 and parts[-1].isdigit() else 1
        await list_withdrawal_requests(update, context, page=page)
    elif data.startswith('admin_approve') or data.startswith('admin_reject'):
        await query.answer()
        request_id = int(data.split('_')[-1])
        request_data = await get_withdrawal_request(request_id)
        if not request_data or request_data['status'] != 'pending':
            await query.edit_message_text(text=f"Request #{request_id} has already been processed."); return
        user_id, amount = request_data['user_id'], request_data['amount']
        if 'approve' in data:
            await update_withdrawal_status(request_id, 'approved')
            await query.edit_message_text(text=f"✅ Request #{request_id} for ₹{amount:.2f} has been APPROVED.")
            try: await context.bot.send_message(chat_id=user_id, text=f"🎉 Your withdrawal request for ₹{amount:.2f} has been approved!")
            except Exception as e: logging.warning(f"Could not notify user {user_id} of approval: {e}")
        elif 'reject' in data:
            await update_withdrawal_status(request_id, 'rejected')
            await update_balance(user_id, amount)
            await query.edit_message_text(text=f"❌ Request #{request_id} for ₹{amount:.2f} has been REJECTED.")
            try: await context.bot.send_message(chat_id=user_id, text=f"⚠️ Your withdrawal request was rejected and the amount returned to your balance.")
            except Exception as e: logging.warning(f"Could not notify user {user_id} of rejection: {e}")
    elif data == 'admin_settings':
        await show_settings_panel(update, context)
    else:
        await query.answer()

# =====================================================================================
# 5. FLASK WEB SERVER FOR UPTIME
# =====================================================================================
flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "OK", 200
def run_flask(): flask_app.run(host='0.0.0.0', port=8080, use_reloader=False)

# =====================================================================================
# 6. MAIN APPLICATION EXECUTION
# =====================================================================================
def main() -> None:
    persistence = PicklePersistence(filepath="bot_persistence")
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).post_init(post_init).build()
    
    # --- Conversation Handlers ---
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_withdrawal, pattern=r'^withdraw$'), CommandHandler('withdraw', start_withdrawal)],
        states={UPI_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_upi_id)]},
        fallbacks=[CommandHandler('cancel', cancel_conversation)], persistent=True, name="withdraw_conv"
    )
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_broadcast_command, pattern=r'^admin_start_broadcast$'), CommandHandler('broadcast', start_broadcast_command)],
        states={GET_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_broadcast_message)]},
        fallbacks=[CommandHandler('cancel', cancel_admin_conversation)], persistent=True, name="broadcast_conv"
    )
    update_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_balance_update_command, pattern=r'^admin_start_balance_update$'), CommandHandler('updatebalance', start_balance_update_command)],
        states={
            GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target_user_id)],
            GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_update_amount)],
            CONFIRM_UPDATE: [CallbackQueryHandler(process_balance_update, pattern=r'^confirm_update_')]
        },
        fallbacks=[CommandHandler('cancel', cancel_admin_conversation)], persistent=True, name="update_balance_conv"
    )
    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_setting_edit, pattern=r'^settings_edit_')],
        states={GET_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_setting_value)]},
        fallbacks=[CommandHandler('cancel', cancel_admin_conversation)],
        persistent=True, name="settings_conv"
    )

    # --- Register all handlers with Priority Groups ---
    # Group 0: Commands and Conversations (highest priority)
    app.add_handler(CommandHandler("start", start), group=0)
    app.add_handler(CommandHandler("admin", admin_panel), group=0)
    app.add_handler(CommandHandler("tasks", show_tasks), group=0)
    app.add_handler(CommandHandler("refer", show_referral_info), group=0)
    app.add_handler(CommandHandler("balance", show_balance), group=0)
    app.add_handler(CommandHandler("bonus", daily_bonus), group=0)
    app.add_handler(CommandHandler("help", show_help), group=0)
    app.add_handler(CommandHandler("contact", contact_admin), group=0)
    app.add_handler(CommandHandler("stats", admin_stats), group=0)
    app.add_handler(CommandHandler("listusers", list_users), group=0)
    app.add_handler(CommandHandler("requests", list_withdrawal_requests), group=0)
    app.add_handler(CommandHandler("hourly", hourly_bonus), group=0)

    app.add_handler(withdraw_conv, group=0)
    app.add_handler(broadcast_conv, group=0)
    app.add_handler(update_balance_conv, group=0)
    app.add_handler(settings_conv, group=0)
    
    # Group 1: Admin button router
    app.add_handler(CallbackQueryHandler(admin_callback_router, pattern=r'^admin_'), group=1)
    
    # Group 2: User button router (general fallback)
    app.add_handler(CallbackQueryHandler(user_button_handler), group=2)

    # --- Start the Bot & Web Server ---
    logging.info("Bot and web server are starting...")
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    app.run_polling()

if __name__ == '__main__':
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
    main()