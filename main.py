# main.py
import os
import time
import asyncio
import sqlite3
import re
from telethon import TelegramClient, events, types
from telethon.errors import FloodWaitError, UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipant

# ----------------- Config from env -----------------
API_ID = int(os.getenv("API_ID") or 0)
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")  # e.g. https://t.me/spredsubscriberAjay755 or @spredsubscriberAjay755
CHANNEL_2 = os.getenv("CHANNEL_2")  # e.g. https://t.me/Girls_movies_intrester_com_me
UPI_ID = os.getenv("UPI_ID") or "7051946740@ybl"  # default to your UPI if not set

DB = "data.db"
os.makedirs("payments", exist_ok=True)

# ----------------- Database -----------------
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

def set_trial(user_id):
    import datetime
    expires = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, trial_expires_at, paid_until, channels_joined) VALUES (?, ?, ?, COALESCE((SELECT channels_joined FROM users WHERE user_id=?),0))",
              (user_id, expires, None, user_id))
    conn.commit()
    conn.close()
    return expires

def mark_paid(user_id, days=30, txnid=None, filename=None):
    import datetime
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
    import datetime
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

def user_channels_joined(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT channels_joined FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])

# ----------------- Telethon client -----------------
if not API_ID or not API_HASH or not BOT_TOKEN:
    raise SystemExit("Environment variables API_ID, API_HASH and BOT_TOKEN must be set")

client = TelegramClient("bot", API_ID, API_HASH)

# regex to detect txn ids (simple heuristic — adjust if needed)
TXN_RE = re.compile(r'\b[0-9A-Za-z]{6,30}\b')

# Anti-flood: per-user timestamp
recent_users = {}

async def is_member_of_channel(user_id, channel):
    """
    Returns True if user_id is participant of channel.
    channel can be @username or invite link. We try to resolve entity.
    """
    try:
        # resolve channel entity
        ch_entity = await client.get_entity(channel)
        # call GetParticipantRequest
        await client(GetParticipantRequest(ch_entity, user_id))
        return True
    except UserNotParticipantError:
        return False
    except Exception as e:
        # could be channel missing or privacy; treat as False
        return False

# Flood-wait safe start
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

# ----------------- Handlers -----------------

@client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    if has_access(user_id):
        await event.respond("✅ آپ کے پاس پہلے ہی access ہے — enjoy!")
        return
    expires = set_trial(user_id)
    await event.respond(
        f"🎁 You got a 1-day free trial (until {expires}).\n\n"
        f"📢 Please JOIN these channels first:\n"
        f"{CHANNEL_1}\n{CHANNEL_2}\n\n"
        f"💰 To extend, pay ₹10 via UPI to {UPI_ID} and send a screenshot or paste txn id here.\n"
        "After payment, your access will be activated for 30 days."
    )

@client.on(events.ChatAction)
async def welcome_new(event):
    # When new member joins a group where the bot is present
    if event.user_joined or event.user_added:
        try:
            user = await event.get_user()
            await event.reply(
                f"👋 Welcome {user.first_name}!\n\n"
                f"Please JOIN these channels before chatting:\n{CHANNEL_1}\n{CHANNEL_2}\n\n"
                f"Then pay ₹10 to {UPI_ID} and send a screenshot here to get full access."
            )
        except Exception as e:
            print("welcome error:", e)

@client.on(events.NewMessage)
async def payment_and_group_control(event):
    # avoid reacting to our own or other bots or edited messages
    if event.out or (event.sender and getattr(event.sender, "bot", False)):
        return

    # If user sends a photo (assume payment screenshot)
    user_id = event.sender_id

    # Rate limit: avoid replying too often per user
    now = time.time()
    if user_id in recent_users and now - recent_users[user_id] < 5:
        return
    recent_users[user_id] = now

    # If private chat: handle payments and instructions
    if event.is_private:
        # If photo(s) -> save screenshot & auto mark paid
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

        # Check text for txn id
        text = (event.raw_text or "").strip()
        m = TXN_RE.search(text)
        if m and len(m.group(0)) >= 6:
            txn = m.group(0)
            paid_until = mark_paid(user_id, days=30, txnid=txn)
            await event.respond(f"✔️ Transaction id `{txn}` received and accepted. Access active until {paid_until} UTC.")
            return

        # Otherwise: remind to join channels and pay
        await event.respond(
            f"Please join these channels first:\n{CHANNEL_1}\n{CHANNEL_2}\n\n"
            f"Then pay ₹10 to {UPI_ID} and send screenshot here. After verification, you'll get 30 days access."
        )
        return

    # If message is in a group: enforce subscription/access
    if event.is_group:
        # skip if this message is from the bot itself
        if event.message and event.message.sender_id == (await client.get_me()).id:
            return

        # If user has access -> allow
        if has_access(user_id):
            return  # do nothing, allow message

        # If user doesn't have access, check if they joined channels (we try)
        joined1 = await is_member_of_channel(user_id, CHANNEL_1)
        joined2 = await is_member_of_channel(user_id, CHANNEL_2)
        if joined1 and joined2:
            # mark channels joined and give trial if none
            set_channels_joined(user_id)
            # if no trial or paid, give trial now
            if not has_access(user_id):
                set_trial(user_id)
                await event.reply("🎁 You were given a 1-day trial for joining the channels. Enjoy!")
            return

        # Neither paid nor joined: delete message (if bot has permission) and instruct
        try:
            await event.delete()
        except Exception:
            pass
        try:
            await event.reply(
                f"❌ You need access to chat.\n1) Join these channels: {CHANNEL_1} and {CHANNEL_2}\n"
                f"2) Pay ₹10 via UPI to {UPI_ID} and send a screenshot in private to me.\n\n"
                "After that you'll be allowed to chat."
            )
        except Exception as e:
            print("reply error:", e)

# ----------------- Keep process alive and auto-reconnect loop -----------------
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
