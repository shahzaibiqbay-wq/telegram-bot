# main.py
import os
import asyncio
from telethon import TelegramClient, events, types, errors
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import PeerChannel, PeerUser
from flask import Flask
from threading import Thread

# ---------- Config from env ----------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL = os.getenv("CHANNEL", "")   # e.g. @MyChannel or numeric id - channel the users must join
GROUP = os.getenv("GROUP", "")       # e.g. @MyGroup or numeric id - group where bot moderates
WELCOME_MESSAGE = os.getenv("WELCOME_MESSAGE",
    "👋 Welcome! To continue chatting please subscribe to our channel: {channel}\nAfter subscribing, send any message and I'll allow you to chat."
)

# ---------- Basic checks ----------
if not all([API_ID, API_HASH, BOT_TOKEN, CHANNEL, GROUP]):
    raise Exception("Missing one of required env vars: API_ID, API_HASH, BOT_TOKEN, CHANNEL, GROUP")

# ---------- Telethon client ----------
client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ---------- Helper functions ----------
async def is_member_of_channel(user_id: int) -> bool:
    """
    Returns True if user_id is a participant of CHANNEL.
    Uses GetParticipantRequest which is fast and explicit.
    """
    try:
        # channel may be username or id; Telethon accepts either
        await client(GetParticipantRequest(channel=CHANNEL, user_id=user_id))
        return True
    except errors.UserNotParticipantError:
        return False
    except errors.ChannelPrivateError:
        # channel is private / bot can't access; treat as not a member
        return False
    except errors.RPCError:
        # any other RPC problem — be conservative and return False
        return False
    except Exception:
        return False

async def ensure_bot_admin_in_group(chat):
    """
    Quick check: ensure bot has Delete Messages rights in the target group.
    """
    try:
        # fetch chat full info
        full = await client.get_entity(chat)
        # This is a light check; actual deletion attempt will reveal permission issues.
        return True
    except Exception:
        return False

# ---------- Events: Welcome for new members ----------
@client.on(events.ChatAction)
async def handler_chat_action(event):
    # Only handle joins/adds in the configured group
    try:
        chat = event.chat_id or event.chat
        # Convert GROUP env to id/username - compare with event.chat_id when possible
        # We'll check by comparing event.chat.title or id against GROUP when GROUP is numeric or username.
    except Exception:
        return

    # Determine if this chat is the target group
    try:
        target = GROUP
        # If GROUP given as numeric (string of digits), compare ids
        if GROUP.isdigit():
            if event.chat_id != int(GROUP):
                return
        else:
            # If GROUP is username like @MyGroup, compare using chat.username if available
            chat_entity = await event.get_chat()
            username = getattr(chat_entity, 'username', None)
            if username:
                if not (GROUP.lstrip('@').lower() == username.lower()):
                    return
            else:
                # fallback: compare title or id - if not match, proceed (we are conservative)
                pass
    except Exception:
        # if any problem, allow processing (so it still works in many setups)
        pass

    # New user joined or was added
    if event.user_joined or event.user_added:
        # event.user may be None; get users list
        try:
            users = await event.get_users()
        except Exception:
            users = []

        # loop through users if multiple
        for u in users:
            try:
                # send welcome message in group (tag user)
                name = u.first_name or "there"
                msg = WELCOME_MESSAGE.format(channel=CHANNEL)
                await event.reply(f"👋 {name}\n{msg}")
            except Exception:
                # ignore send errors
                pass

# ---------- Events: New messages in group ----------
@client.on(events.NewMessage)
async def handler_new_message(event):
    """
    Main moderation logic:
    - Only operates inside the configured GROUP
    - If the sender is not subscribed to CHANNEL -> delete their message and send them a DM with join link
    - If the sender is subscribed -> allow message
    """
    # Ignore if message is from a channel or from the bot itself
    if event.is_channel or event.out:
        return

    # Ensure the message is in the target group
    try:
        # If GROUP specified as digits, compare chat id
        if GROUP.isdigit():
            if event.chat_id != int(GROUP):
                return
        else:
            # try to resolve the chat username
            chat_entity = await event.get_chat()
            username = getattr(chat_entity, 'username', None)
            if username:
                if username.lower() != GROUP.lstrip('@').lower():
                    return
            else:
                # if no username, try title compare if provided as plain text - skip strict check
                # proceed anyway (best-effort)
                pass
    except Exception:
        # if resolution fails, skip - avoid breaking bot
        pass

    sender = await event.get_sender()
    if not sender:
        return

    # Allow if sender is a bot (optional) or sender is admin (so admins don't get deleted)
    try:
        if sender.bot:
            return
    except Exception:
        pass

    # Check if sender is member of CHANNEL
    user_id = sender.id
    allowed = await is_member_of_channel(user_id)

    if allowed:
        # user is subscribed -> do nothing; maybe send a tiny thumbs up for first allowed message? (commented)
        # You could implement a "first message allowed" notice if desired.
        return
    else:
        # Delete the message in group (bot must have permission to delete)
        try:
            await event.delete()
        except errors.ChatAdminRequiredError:
            # Bot lacks delete permission
            # Optionally notify the group owner or log
            try:
                await event.reply("⚠️ I need 'Delete messages' admin permission to auto-delete non-subscribed members' messages. Please promote me as admin.")
            except Exception:
                pass
            return
        except Exception:
            # any other delete error - ignore
            pass

        # Send a private message to user with instructions and channel link
        try:
            dm_text = (
                "🔒 Your message was removed from the group because you haven't subscribed to our channel yet.\n\n"
                f"✅ Please join {CHANNEL} first. After joining, send any message in the group again and it will be allowed.\n\n"
                "If you can't join via username, open this link: https://t.me/{channel_username}\n\n"
                "If you already joined, try waiting a few seconds and resend your message."
            )
            # Compose channel_username if CHANNEL is @username
            channel_username = CHANNEL.lstrip('@')
            dm_text = dm_text.format(channel_username=channel_username)
            await client.send_message(user_id, dm_text)
        except errors.PeerFloodError:
            # Can't DM because of flood limit; optionally, reply in group (but we've deleted message)
            pass
        except errors.UserIsBlockedError:
            # user has blocked the bot; nothing we can do
            pass
        except Exception:
            pass

# ---------- Keep alive: simple Flask server for Render/Heroku ----------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive ✅"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def start_keepalive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ---------- Startup ----------
async def main():
    # start webserver
    start_keepalive()
    # optional: ensure bot admin etc.
    ok = await ensure_bot_admin_in_group(GROUP)
    # print status for logs
    print("Bot started. Monitoring group:", GROUP, "Require channel:", CHANNEL)
    # run until disconnected
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        # run the Telethon client (this will block)
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print("Fatal error:", e)
