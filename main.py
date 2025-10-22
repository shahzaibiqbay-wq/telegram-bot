import os
import time
import asyncio
import sqlite3
import re
from telethon import TelegramClient, events
from telethon.errors import UserNotParticipantError, FloodWaitError
from telethon.tl.functions.channels import GetParticipantRequest

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID") or "your_api_id_here")
API_HASH = os.getenv("API_HASH") or "your_api_hash_here"
BOT_TOKEN = os.getenv("BOT_TOKEN") or "your_bot_token_here"
OWNER_ID = int(os.getenv("OWNER_ID") or 7051946740)
UPI_ID = os.getenv("UPI_ID") or "7051946740@ybl"
CHANNELS = os.getenv("CHANNELS", "").split(",") or [
    "https://t.me/spredsubscriberAjay755",
    "https://t.me/Girls_movies_intrester_com_me"
]

DB = "data.db"
os.makedirs("payments", exist_ok=True)

# ---------------- DATABASE ----------------
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            txnid TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- USER FUNCTIONS ----------------
import datetime

def set_trial(user_id):
    expires = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO users (user_id, trial_expires_at, paid_until, channels_joined) VALUES (?, ?, COALESCE((SELECT paid_until FROM users WHERE user_id=?),NULL), COALESCE((SELECT channels_joined FROM users WHERE user_id=?),0))",
        (user_id, expires, user_id, user_id)
    )
    conn.commit()
    conn.close()
    return expires

def mark_paid(user_id, days=30, txnid=None, filename=None):
    paid_until = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, trial_expires_at, paid_until, channels_joined) VALUES (?, NULL, ?, 1)",
              (user_id, paid_until))
    if txnid or filename:
        c.execute("INSERT INTO payments (user_id, filename, txnid, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, filename, txnid, datetime.datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return paid_until

def has_access(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT trial_expires_at, paid_until FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    now = datetime.datetime.utcnow()
    for val in row:
        if val:
            try:
                if datetime.datetime.fromisoformat(val) > now:
                    return True
            except Exception:
                continue
    return False

def set_channels_joined(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET channels_joined=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# ---------------- TELETHON CLIENT ----------------
client = TelegramClient("bot", API_ID, API_HASH)

TXN_RE = re.compile(r'\b[0-9A-Za-z]{6,30}\b')
recent_users = {}

async def is_member_of_channel(user_id, channel):
    try:
        ch_entity = await client.get_entity(channel)
        await client(GetParticipantRequest(ch_entity, user_id))
        return True
    except UserNotParticipantError:
        return False
    except Exception:
        return False

# ---------------- CONNECT CLIENT ----------------
def connect_client():
    while True:
        try:
            client.start(bot_token=BOT_TOKEN)
            print("✅ Bot connected")
            break
        except FloodWaitError as e:
            print(f"FloodWaitError: waiting {e.seconds} seconds...")
            time.sleep(e.seconds + 5)
        except Exception as e:
            print("Connect error:", e)
            time.sleep(5)

connect_client()

# ---------------- HANDLERS ----------------
@client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    if has_access(user_id):
        await event.respond("✅ آپ کے پاس پہلے ہی access ہے — enjoy!")
        return
    expires = set_trial(user_id)
    channels_text = "\n".join(CHANNELS)
    await event.respond(
        f"🎁 You got a 1-day free trial (until {expires}).\n\n"
        f"📢 Please JOIN these channels first:\n{channels_text}\n\n"
        f"💰 To extend, pay ₹10 via UPI to {UPI_ID} and send a screenshot or paste txn id here.\n"
        "After payment, your access will be activated for 30 days."
    )

@client.on(events.ChatAction)
async def welcome_new(event):
    if event.user_joined or event.user_added:
        try:
            user = await event.get_user()
            channels_text = "\n".join(CHANNELS)
            await event.reply(
                f"👋 Welcome {user.first_name}!\n\n"
                f"Please JOIN these channels before chatting:\n{channels_text}\n\n"
                f"Then pay ₹10 via UPI to {UPI_ID} and send a screenshot in private to get full access."
            )
        except Exception as e:
            print("welcome error:", e)

@client.on(events.NewMessage)
async def payment_and_group_control(event):
    if event.out or (event.sender and getattr(event.sender, "bot", False)):
        return

    user_id = event.sender_id
    now = time.time()
    if user_id in recent_users and now - recent_users[user_id] < 5:
        return
    recent_users[user_id] = now

    # Private chat handling
    if event.is_private:
        if event.media:
            try:
                file_path = await event.download_media(file="payments/")
                paid_until = mark_paid(user_id, days=30, filename=file_path)
                await event.respond(f"✔️ Payment screenshot received and accepted. Your access is active until {paid_until} UTC.")
                return
            except Exception as e:
                await event.respond("⚠️ Could not save screenshot, please try again.")
                print("save media error:", e)
                return

        text = (event.raw_text or "").strip()
        m = TXN_RE.search(text)
        if m and len(m.group(0)) >= 6:
            txn = m.group(0)
            paid_until = mark_paid(user_id, days=30, txnid=txn)
            await event.respond(f"✔️ Transaction id `{txn}` received and accepted. Access active until {paid_until} UTC.")
            return

        channels_text = "\n".join(CHANNELS)
        await event.respond(
            f"Please join these channels first:\n{channels_text}\n\n"
            f"Then pay ₹10 to {UPI_ID} and send screenshot here. After verification, you'll get 30 days access."
        )
        return

    # Group chat handling
    if event.is_group:
        if has_access(user_id):
            return

        joined_all = True
        for ch in CHANNELS:
            if not await is_member_of_channel(user_id, ch):
                joined_all = False
                break

        if joined_all:
            set_channels_joined(user_id)
            if not has_access(user_id):
                set_trial(user_id)
                await event.reply("🎁 You were given a 1-day trial for joining the channels. Enjoy!")
            return

        try:
            await event.delete()
        except Exception:
            pass

        channels_text = "\n".join(CHANNELS)
        try:
            await event.reply(
                f"❌ You need access to chat.\n1) Join these channels:\n{channels_text}\n"
                f"2) Pay ₹10 via UPI to {UPI_ID} and send a screenshot in private.\n\n"
                "After that you'll be allowed to chat."
            )
        except Exception as e:
            print("reply error:", e)

# ---------------- MAIN LOOP ----------------
async def main_loop():
    while True:
        try:
            print("Client is running (awaiting events)...")
            await client.run_until_disconnected()
        except FloodWaitError as e:
            print("FloodWaitError in main_loop:", e)
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            print("Unhandled error, will reconnect in 10s:", e)
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main_loop())
    except KeyboardInterrupt:
        print("Stopping by user")
