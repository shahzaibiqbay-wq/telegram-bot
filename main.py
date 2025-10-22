import os
import time
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

# ---- Environment Variables ----
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")  # First channel link
CHANNEL_2 = os.getenv("CHANNEL_2")  # Second channel link

# ---- Initialize Client ----
client = TelegramClient("bot", API_ID, API_HASH)

# ---- Safe Connection (prevents FloodWaitError) ----
def connect_client():
    while True:
        try:
            client.start(bot_token=BOT_TOKEN)
            print("✅ Bot Connected Successfully!")
            break
        except FloodWaitError as e:
            print(f"⚠️ FloodWaitError: Waiting {e.seconds} seconds before reconnecting...")
            time.sleep(e.seconds + 5)
        except Exception as e:
            print(f"❌ Unexpected Error: {e}")
            time.sleep(10)

connect_client()

# ---- Welcome Message on new member ----
@client.on(events.ChatAction)
async def handler(event):
    if event.user_joined or event.user_added:
        await event.reply(
            "👋 Welcome! Please subscribe to my channels before chatting:\n\n"
            f"📢 {CHANNEL_1}\n📢 {CHANNEL_2}\n\n"
            "After subscribing, enjoy chatting! 💬"
        )

# ---- Chat Message Control ----
@client.on(events.NewMessage)
async def control_chat(event):
    if event.is_private:
        await event.respond(
            "⚠️ Please join both channels before continuing:\n"
            f"{CHANNEL_1}\n{CHANNEL_2}\n\n"
            "Once done, you’ll have full access ✅"
        )

# ---- Start Bot ----
print("🚀 Bot is running...")
client.run_until_disconnected()
