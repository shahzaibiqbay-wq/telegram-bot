from telethon import TelegramClient, events
import os

# ----- Environment Variables -----
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
channels = os.getenv("CHANNELS").split(",")

# Initialize client
client = TelegramClient('bot', api_id, api_hash).start(bot_token=bot_token)

# ----- Welcome Message -----
@client.on(events.ChatAction)
async def welcome(event):
    if event.user_joined or event.user_added:
        msg = (
            "👋 **Welcome to the group!**\n\n"
            "Before chatting, please subscribe to our channels:\n\n"
            f"📢 [Channel 1]({channels[0].strip()})\n"
            f"🎬 [Channel 2]({channels[1].strip()})\n\n"
            "After subscribing, you can chat freely! 😄"
        )
        await event.reply(msg, link_preview=False)

# ----- Subscription Check -----
@client.on(events.NewMessage)
async def check_subscription(event):
    user = await event.get_sender()
    subscribed = True
    for ch in channels:
        try:
            await client.get_participant(ch.strip(), user.id)
        except:
            subscribed = False
            break
    if not subscribed:
        warn = (
            "⚠️ Please subscribe to both channels before chatting:\n\n"
            f"📢 {channels[0].strip()}\n"
            f"🎬 {channels[1].strip()}"
        )
        await event.reply(warn, link_preview=False)
        await event.delete()

print("🤖 Bot is running 24/7...")
client.run_until_disconnected() telegram-bot
