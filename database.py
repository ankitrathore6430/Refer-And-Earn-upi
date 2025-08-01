# refer_and_earn_bot/database.py
import motor.motor_asyncio
from config import MONGO_URI

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.refer_bot

async def db_init():
    await db.users.create_index("user_id", unique=True)

async def get_user(user_id):
    return await db.users.find_one({"user_id": str(user_id)})

async def add_user(user, ref=None):
    await db.users.insert_one({
        "user_id": str(user.id),
        "username": user.username,
        "ref": str(ref) if ref else None,
        "balance": 0,
        "referrals": 0,
        "tasks": {}
    })

async def update_balance(user_id, amount):
    await db.users.update_one({"user_id": str(user_id)}, {"$inc": {"balance": amount}})

async def get_balance(user_id):
    user = await get_user(user_id)
    return user["balance"] if user else 0

async def get_referrals(user_id):
    user = await get_user(user_id)
    return user["referrals"] if user else 0

async def record_referral(ref_id):
    await db.users.update_one({"user_id": str(ref_id)}, {"$inc": {"referrals": 1, "balance": 10}})

async def check_task(user_id, task_id):
    user = await get_user(user_id)
    return user["tasks"].get(task_id, False)

async def complete_task(user_id, task_id):
    user = await get_user(user_id)
    if user["tasks"].get(task_id):
        return False
    await db.users.update_one({"user_id": str(user_id)}, {"$set": {f"tasks.{task_id}": True}})
    await update_balance(user_id, 10)
    return True
