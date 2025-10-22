import os
import asyncio
from telethon import TelegramClient, events, errors

# ---------------------------
# 1. Read environment variables (never hardcode secrets!)
# ---------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNELS = os.getenv("CHANNELS", "")  # comma separated, only @usernames

# Validate
if not (API_ID and API_HASH and BOT_TOKEN):
    raise RuntimeError("Missing API_ID, API_HASH or BOT_TOKEN in environment variables.")

# Normalize channels list
channels = [c.strip() for c in CHANNELS.split(",") if c.strip()]

# ---------------------------
# 2. Initialize Telegram Client
# ---------------------------
client = TelegramClient('bot', API_ID, API_HASH)

# ---------------------------
# 3. Helper function: check subscriptions
# ---------------------------
async def check_user_subscriptions(user_id):
    not_subscribed = []
    for ch in channels:
        try:
            await client.get_participant(ch, user_id)
        except errors.UserNotParticipantError:
            not_subscribed.append(ch)
        except errors.RPCError:
            not_subscribed.append(ch)
        except Exception:
            not_subscribed.append(ch)
    return not_subscribed

# ---------------------------
# 4. Event: New user joins / added
# ---------------------------
@client.on(events.ChatAction)
async def handler(event):
    if event.user_joined or event.user_added:
        try:
            user = await event.get_user()
            not_subs = await check_user_subscriptions(user.id)
            if not_subs:
                text = (
                    f"Welcome {user.first_name or 'there'}! 👋\n\n"
                    "Please subscribe to these channels to continue:\n" +
                    "\n".join(f"- {c}" for c in not_subs) +
                    "\n\nAfter subscribing, send any message here to continue."
                )
                await event.reply(text)
            else:
                await event.reply(
                    f"Welcome {user.first_name or 'there'}! ✅ You are subscribed — enjoy the chat."
                )
        except Exception as e:
            await event.reply("Welcome! Please make sure you are subscribed to required channels to continue.")
            print("Error in welcome handler:", e)

# ---------------------------
# 5. Run the bot
# ---------------------------
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Bot started successfully.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
