# welcome_forcejoin_bot.py
# Deploy on Render (web service) using python-telegram-bot webhook mode
import os
import logging
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler

# ========== CONFIG (YOUR PROVIDED VALUES) ==========
BOT_TOKEN = "8138695060:AAHbL3oiE7tkQLPbxVi_YnBSRECEE4fH1rE"
API_ID = "27766103"
API_HASH = "5e3ef806cae22fa1e6975a0254de500c"
CHANNEL_USERNAME = "@SubscriberAjay755"
GROUP_USERNAME = "@GirlsMovies"
# Replace with a valid sticker file_id you want to send, or leave empty to skip sticker
WELCOME_STICKER_FILE_ID = ""  # e.g. "CAACAgUAAxkBAAEB..." or leave ""

# ==================================================
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(name)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running ✅")

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    chat = update.effective_chat
    for member in update.message.new_chat_members:
        try:
            # send sticker if set
            if WELCOME_STICKER_FILE_ID:
                try:
                    await bot.send_sticker(chat_id=chat.id, sticker=WELCOME_STICKER_FILE_ID)
                except Exception as s_err:
                    logger.warning("Sticker send failed: %s", s_err)

            welcome_text = (
                f"خوش آمدید, {member.mention_html()}!\n\n"
                "براہِ کرم پہلے ہمارا چینل جوائن کریں👇\n"
                f"{CHANNEL_USERNAME}\n\n"
                "جوائن کرنے کے بعد آپ پوری طرح سے گروپ میں بات کر سکتے ہیں۔"
            )
            await bot.send_message(chat_id=chat.id, text=welcome_text, parse_mode="HTML")

            # Try checking membership in channel; if not member, restrict sending messages
            try:
                member_status = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=member.id)
                if member_status.status in ("member", "creator", "administrator"):
                    logger.info("User %s already member of %s", member.id, CHANNEL_USERNAME)
                else:
                    await restrict_until_join(bot, chat.id, member.id)
            except Exception as e:
                # Could be private channel or bot not admin - we still inform user
                logger.warning("Could not verify channel membership (maybe bot not admin): %s", e)
                # Optionally restrict anyway (comment/uncomment next line)
                # await restrict_until_join(bot, chat.id, member.id)
        except Exception as e:
            logger.exception("Error in new_member_handler: %s", e)

async def restrict_until_join(bot, group_id: int, user_id: int):
    try:
        perms = ChatPermissions(can_send_messages=False)
        await bot.restrict_chat_member(chat_id=group_id, user_id=user_id, permissions=perms)
        await bot.send_message(chat_id=group_id,
                               text=f"براہِ کرم پہلے {CHANNEL_USERNAME} جوائن کریں — پھر آپ کو پوَرا access مل جائے گا.")
    except Exception as e:
        logger.exception("Failed to restrict user: %s", e)

async def verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    bot = context.bot
    try:
        member_status = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user.id)
        if member_status.status in ("member", "creator", "administrator"):
            # unrestrict
            perms = ChatPermissions(can_send_messages=True,
                                    can_send_media_messages=True,
