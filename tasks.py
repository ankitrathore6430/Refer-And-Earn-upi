# refer_and_earn_bot/tasks.py
from aiogram import Bot
from config import BOT_TOKEN
from database import complete_task

bot = Bot(token=BOT_TOKEN)

async def verify_task(user_id, task_id):
    completed = await complete_task(user_id, task_id)
    if completed:
        return "✅ Task verified! ₹10 added to your wallet."
    return "⚠️ Task already completed or verification failed."
