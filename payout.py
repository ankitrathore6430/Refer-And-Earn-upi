# refer_and_earn_bot/payout.py
from aiogram import types
from config import ADMIN_ID
from database import get_balance

withdraw_requests = {}

async def handle_withdrawal(message, user):
    balance = await get_balance(user.id)
    if balance < 150:
        await message.edit_text("❌ Minimum withdrawal is ₹150.", reply_markup=None)
        return
    await message.edit_text("💸 Enter your UPI ID to withdraw:")
    withdraw_requests[user.id] = balance

async def admin_withdraw_handler(message):
    if not withdraw_requests:
        await message.reply("No pending withdrawals.")
        return
    for uid, amount in withdraw_requests.items():
        await message.reply(f"User: {uid}\nAmount: ₹{amount}\nApprove or reject manually.")
