from pyrogram import Client, filters
from pyrogram.types import ChatPermissions
import os

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = os.environ.get("CHANNEL")
GROUP = os.environ.get("GROUP")

bot = Client("AjayBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ✅ جب کوئی نیا ممبر group میں join کرے
@bot.on_message(filters.new_chat_members)
def welcome_message(client, message):
    for member in message.new_chat_members:
        message.reply_text(
            f"👋 Welcome {member.mention} to {message.chat.title}!\n"
            f"Please make sure you’ve joined our channel 👉 {CHANNEL}"
        )

# ✅ جب کوئی group میں message کرے (force join check)
@bot.on_message(filters.chat(GROUP) & filters.text & ~filters.service)
def force_join_check(client, message):
    message.reply_text(
        f"⚠️ {message.from_user.mention}, kindly join our channel {CHANNEL} to continue chatting!"
    )

print("✅ Bot is starting...")
bot.run()
