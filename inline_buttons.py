# refer_and_earn_bot/inline_buttons.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import check_task

def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📋 Tasks", callback_data="tasks"),
        InlineKeyboardButton("👥 Refer & Earn", callback_data="refer"),
        InlineKeyboardButton("💰 My Balance", callback_data="balance"),
        InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
        InlineKeyboardButton("ℹ️ Help / FAQ", callback_data="help")
    )
    return kb

async def task_buttons(user_id):
    tasks = [
        ("1", "Start @Instagram_vdownloder_bot"),
        ("2", "Start @Userinfo_pro2_bot"),
        ("3", "Start @YouTubeDownloadermp3bot")
    ]
    kb = InlineKeyboardMarkup(row_width=1)
    for tid, label in tasks:
        completed = await check_task(user_id, tid)
        text = f"{'✅' if completed else '⬜️'} {label}"
        kb.add(InlineKeyboardButton(text, url=f"https://t.me/{label.split('@')[1]}" if not completed else None,
                                    callback_data=f"verify_task_{tid}" if not completed else "done"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="start"))
    return kb
