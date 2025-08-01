# refer_and_earn_bot/bot.py
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import start_webhook
from config import BOT_TOKEN, ADMIN_ID, WEBHOOK_URL, WEBHOOK_PATH, WEBAPP_HOST, WEBAPP_PORT
from database import db_init, get_user, add_user, update_balance, get_balance, get_referrals, check_task, complete_task, record_referral
from inline_buttons import main_menu, task_buttons
from tasks import verify_task
from payout import handle_withdrawal, admin_withdraw_handler

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    referrer_id = None
    if len(message.text.split()) > 1:
        referrer_id = message.text.split()[1]

    user = await get_user(message.from_user.id)
    if not user:
        await add_user(message.from_user, referrer_id)
        if referrer_id and str(message.from_user.id) != str(referrer_id):
            await record_referral(referrer_id)

    await message.answer("Welcome to Refer & Earn Bot!", reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == 'tasks')
async def show_tasks(callback: types.CallbackQuery):
    await callback.message.edit_text("📄 Task List:", reply_markup=await task_buttons(callback.from_user.id))

@dp.callback_query_handler(lambda c: c.data.startswith('verify_task_'))
async def verify_task_handler(callback: types.CallbackQuery):
    task_id = callback.data.split('_')[-1]
    result = await verify_task(callback.from_user.id, task_id)
    await callback.answer(result, show_alert=True)
    await callback.message.edit_reply_markup(await task_buttons(callback.from_user.id))

@dp.callback_query_handler(lambda c: c.data == 'refer')
async def refer_handler(callback: types.CallbackQuery):
    link = f"https://t.me/ReferAndEarn_upi_bot?start={callback.from_user.id}"
    refs = await get_referrals(callback.from_user.id)
    text = f"👥 Refer & Earn\nYour Link: {link}\nReferrals: {refs}"
    await callback.message.edit_text(text, reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == 'balance')
async def balance_handler(callback: types.CallbackQuery):
    balance = await get_balance(callback.from_user.id)
    await callback.message.edit_text(f"💰 Your Balance: ₹{balance}", reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == 'withdraw')
async def withdraw_handler(callback: types.CallbackQuery):
    await handle_withdrawal(callback.message, callback.from_user)

@dp.callback_query_handler(lambda c: c.data == 'help')
async def help_handler(callback: types.CallbackQuery):
    help_text = "ℹ️ Help / FAQ\n\n- Earn ₹10 per task\n- ₹10 per referral (instant)\n- Withdraw minimum ₹150 to UPI\n- Admin reviews payouts manually"
    await callback.message.edit_text(help_text, reply_markup=main_menu())

@dp.message_handler(commands=['admin'])
async def admin_cmd_handler(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await admin_withdraw_handler(message)

async def on_startup(dp):
    await db_init()
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
