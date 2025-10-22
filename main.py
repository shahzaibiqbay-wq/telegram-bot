import os
import datetime
import sqlite3
from telethon import TelegramClient, events, types
import asyncio

# ---------------- Environment ----------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNELS = [os.getenv("CHANNEL_1"), os.getenv("CHANNEL_2")]
UPI_ID = os.getenv("UPI_ID")

DB = "data.db"
os.makedirs("payments", exist_ok=True)

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            trial_expires_at TEXT,
            paid_until TEXT,
            channels_joined INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
init_db()

def has_access(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT trial_expires_at, paid_until FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    now = datetime.datetime.utcnow()
    for val in row[:2]:
        if val and datetime.datetime.fromisoformat(val) > now:
            return True
    return False

def mark_paid(user_id, days=30):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    paid_until = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat()
    c.execute("REPLACE INTO users (user_id, trial_expires_at, paid_until, channels_joined) VALUES (?, ?, ?, ?)",
              (user_id, None, paid_until, 1))
    conn.commit()
    conn.close()
    return paid_until

def set_trial(user_id):
    expires = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("REPLACE INTO users (user_id, trial_expires_at, paid_until, channels_joined) VALUES (?, ?, ?, ?)",
              (user_id, expires.isoformat(), None, 0))
    conn.commit()
    conn.close()
    return expires

def update_channel_join(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET channels_joined=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# ---------------- Telegram Bot ----------------
client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ---- /start command ----
@client.on(events.NewMessage(pattern="/start"))
async def start(event):
    user_id = event.sender_id
    if has_access(user_id):
        await event.respond("✅ You already have access! Enjoy the bot.")
    else:
        expires = set_trial(user_id)
        channel_text = "\n".join([f"🔗 Join {ch}" for ch in CHANNELS])
        await event.respond(f"🎁 You got 1-day free trial! Expires: {expires}\n"
                            f"{channel_text}\n\n💰 To extend access, pay ₹10 via UPI to {UPI_ID} and send screenshot here.")

# ---- Payment / screenshot handler ----
@client.on(events.NewMessage)
async def payment_handler(event):
    user_id = event.sender_id
    if event.photo:
        file_path = await event.download_media(file="payments/")
        paid_until = mark_paid(user_id, days=30)
        await event.reply(f"✔️ Payment verified (manual). Your access is active until {paid_until} UTC.")

# ---- Check new chat members for welcome ----
@client.on(events.ChatAction)
async def welcome_new_member(event):
    if event.user_added or event.user_joined:
        user = await event.get_user()
        user_id = user.id
        # welcome message
        channel_text = "\n".join([f"🔗 Join {ch}" for ch in CHANNELS])
        await event.reply(f"👋 Welcome {user.first_name}!\n{channel_text}\n"
                          f"💰 Pay ₹10 via UPI {UPI_ID} after joining channels to get full access.")

# ---- Group message filter ----
@client.on(events.NewMessage)
async def group_message_filter(event):
    if isinstance(event.chat, types.Chat) or isinstance(event.chat, types.Channel) or isinstance(event.chat, types.InputPeerChannel):
        user_id = event.sender_id
        if not has_access(user_id):
            # delete message and warn user
            try:
                await event.delete()
            except:
                pass
            await event.respond("❌ You need active access! Join channels & pay ₹10 via UPI, then send screenshot to use bot.")

# ---------------- Run Bot ----------------
print("🤖 Bot is running...")
client.run_until_disconnected()
