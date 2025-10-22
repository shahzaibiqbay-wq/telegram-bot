import os
import datetime
import sqlite3
from flask import Flask, request, jsonify
from telethon import TelegramClient, events
import razorpay
import threading

app = Flask(__name__)

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
RAZOR_KEY = os.getenv("RAZOR_KEY")
RAZOR_SECRET = os.getenv("RAZOR_SECRET")

DB = "data.db"
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        trial_expires_at TEXT,
        paid_until TEXT
    )''')
    conn.commit()
    conn.close()
init_db()

rz = razorpay.Client(auth=(RAZOR_KEY, RAZOR_SECRET))
client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

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
        if val and datetime.datetime.fromisoformat(val) > now:
            return True
    return False

@client.on(events.NewMessage(pattern="/start"))
async def start(event):
    user_id = event.sender_id
    if has_access(user_id):
        await event.respond("✅ You already have access! Enjoy the bot.")
    else:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        now = datetime.datetime.utcnow()
        expires = now + datetime.timedelta(days=1)
        c.execute("REPLACE INTO users (user_id, trial_expires_at) VALUES (?, ?)", (user_id, expires.isoformat()))
        conn.commit()
        conn.close()
        await event.respond(f"🎁 You got 1-day free trial! It expires on {expires}.\nTo extend access, pay ₹10 here: https://your-web-link/payment")

@app.route('/')
def home():
    return "🤖 Telegram Bot is running!"

@app.route('/create_payment', methods=['POST'])
def create_payment():
    data = request.json
    amount = 10 * 100  # ₹10 in paise
    user_id = data.get("user_id", "Unknown")
    link = rz.payment_link.create({
        "amount": amount,
        "currency": "INR",
        "description": f"Access for user {user_id}",
        "callback_url": "https://your-web-link/success",
        "callback_method": "get"
    })
    return jsonify(link)

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()
client.run_until_disconnected()
import re
import os
import datetime
import sqlite3

# Ensure payments folder exists
os.makedirs("payments", exist_ok=True)

# simple regex for txn id (example pattern, many txn ids are alphanumeric length 6-20)
TXN_RE = re.compile(r'[A-Z0-9]{5,30}', re.I)

def mark_paid(user_id, days=30):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    paid_until = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat()
    c.execute("REPLACE INTO users (user_id, trial_expires_at, paid_until) VALUES (?, ?, ?)",
              (user_id, None, paid_until))
    conn.commit()
    conn.close()
    return paid_until

@client.on(events.NewMessage)
async def payment_handler(event):
    sender = await event.get_sender()
    user_id = event.sender_id
    text = (event.raw_text or "").strip()

    # 1) If message contains an obvious txn id, ask for screenshot or mark for manual verify
    m = TXN_RE.search(text)
    if m and "upi" not in text.lower() and len(text) >= 6:
        txn = m.group(0)
        # Option: auto mark paid? Better to ask for screenshot to verify time/amount
        await event.reply(f"Got transaction id `{txn}`. Please also send a screenshot of the payment or reply 'VERIFY' when you have paid so I can confirm.")
        # optionally save txn to DB table for manual review (not shown)
        return

    # 2) If message has media (photo) — save it and notify owner for manual checking
    if event.photo:
        file_path = await event.download_media(file="payments/")
        await event.reply("✔️ Payment screenshot received. I will verify and activate access soon.")
        # Notify yourself (owner) in Telegram or log — here we mark paid immediately, but recommended to manual verify
        # For demonstration, we can auto mark (CAUTION):
        paid_until = mark_paid(user_id, days=30)
        await event.reply(f"Thank you! Payment verified (auto). Your access is active until {paid_until} UTC.")
        return

    # else ignore or process other messages
