# -*- coding: utf-8 -*-
import os
import re
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID") # You might need this for Pyrogram Client
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH") # You might need this for Pyrogram Client
TELEGRAM_CHANNEL_ID = int(os.environ.get("TELEGRAM_CHANNEL_ID", 0))
REQUIRED_CHANNEL_USERNAME = os.environ.get("REQUIRED_CHANNEL_USERNAME")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_USER_IDS = [int(admin_id.strip()) for admin_id in os.environ.get("ADMIN_USER_IDS", "").split(',') if admin_id.strip().isdigit()]

# --- Database Setup ---
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String)
    joined_at = Column(DateTime, default=datetime.utcnow)
    download_count = Column(Integer, default=0)
    last_download_at = Column(DateTime)

class DownloadLog(Base):
    __tablename__ = 'download_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    url = Column(String, nullable=False)
    download_time = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error_message = Column(String)

engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        # Adjust DATABASE_URL for SQLAlchemy if it starts with postgres://
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        logger.info("Database connected and tables created/verified.")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        engine = None
        SessionLocal = None
else:
    logger.warning("DATABASE_URL not set. Database features will be disabled.")

# --- Helper Functions ---
def get_db():
    if not SessionLocal:
        return None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def add_or_update_user(db_session, user_data):
    if not db_session:
        return
    try:
        user = db_session.query(User).filter(User.user_id == user_data.id).first()
        if not user:
            user = User(
                user_id=user_data.id,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                username=user_data.username
            )
            db_session.add(user)
            logger.info(f"New user added: {user_data.id}")
        else:
            # Optionally update user info if it changed
            user.first_name = user_data.first_name
            user.last_name = user_data.last_name
            user.username = user_data.username
            logger.debug(f"User info updated: {user_data.id}")
        db_session.commit()
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error adding/updating user {user_data.id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error with user {user_data.id}: {e}")

def log_download(db_session, user_id, url, success=True, error_message=None):
    if not db_session:
        return
    try:
        log_entry = DownloadLog(
            user_id=user_id,
            url=url,
            success=success,
            error_message=error_message
        )
        db_session.add(log_entry)

        # Update user download count
        user = db_session.query(User).filter(User.user_id == user_id).first()
        if user:
            user.download_count += 1
            user.last_download_at = datetime.utcnow()

        db_session.commit()
        logger.info(f"Download logged for user {user_id}. Success: {success}")
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error logging download for user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error logging download for user {user_id}: {e}")

def get_user_stats(db_session, user_id):
    if not db_session:
        return None, None
    try:
        user = db_session.query(User).filter(User.user_id == user_id).first()
        if user:
            return user.download_count, user.last_download_at
        return 0, None
    except SQLAlchemyError as e:
        logger.error(f"Error getting stats for user {user_id}: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error getting stats for user {user_id}: {e}")
        return None, None

def get_total_users(db_session):
    if not db_session:
        return 0
    try:
        return db_session.query(User).count()
    except SQLAlchemyError as e:
        logger.error(f"Error getting total users: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error getting total users: {e}")
        return 0

def get_total_downloads(db_session):
    if not db_session:
        return 0
    try:
        # Efficiently sum download counts from User table
        total = db_session.query(func.sum(User.download_count)).scalar()
        return total or 0
        # Alternative: Count DownloadLog entries
        # return db_session.query(DownloadLog).filter(DownloadLog.success == True).count()
    except SQLAlchemyError as e:
        logger.error(f"Error getting total downloads: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error getting total downloads: {e}")
        return 0

async def is_user_subscribed(client: Client, user_id: int) -> bool:
    if not REQUIRED_CHANNEL_USERNAME or not TELEGRAM_CHANNEL_ID:
        logger.warning("Subscription check skipped: Channel username or ID not configured.")
        return True # Skip check if not configured
    try:
        await client.get_chat_member(chat_id=TELEGRAM_CHANNEL_ID, user_id=user_id)
        logger.debug(f"User {user_id} is subscribed.")
        return True
    except UserNotParticipant:
        logger.info(f"User {user_id} is not subscribed.")
        return False
    except FloodWait as e:
        logger.warning(f"Flood wait of {e.value} seconds when checking subscription for {user_id}.")
        await asyncio.sleep(e.value + 1)
        return await is_user_subscribed(client, user_id) # Retry after waiting
    except Exception as e:
        logger.error(f"Error checking subscription for user {user_id}: {e}")
        return False # Assume not subscribed on error

# --- Instagram Download Logic ---

# Improved regex to handle various Instagram URL formats
INSTAGRAM_REGEX = r"https?://(?:www\.) ?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_\-]+)/?"

async def download_instagram_media(url: str):
    """Downloads media from an Instagram URL using an external API."""
    api_url = f"https://api.rival.rocks/media/instagram/download?url={url}"
    headers = {
        "accept": "application/json",
        # Add any necessary API keys or headers here if required by api.rival.rocks
        # "Authorization": "Bearer YOUR_API_KEY"
    }
    try:
        response = requests.get(api_url, headers=headers, timeout=60)  # Increased timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        if data and isinstance(data, list) and data[0].get('url'):
            media_url = data[0]['url']
            media_type = data[0].get('type', 'unknown') # video or image
            logger.info(f"Successfully retrieved media URL: {media_url} (Type: {media_type})")
            return media_url, media_type
        else:
            logger.warning(f"API response format unexpected or missing URL for {url}. Data: {data}")
            return None, None

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching from download API for {url}: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error during Instagram download for {url}: {e}")
        return None, None

# --- Pyrogram Bot Setup ---
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN not found in environment variables. Exiting.")
    exit()

# Use API ID and Hash if available, otherwise rely on Bot Token only
if TELEGRAM_API_ID and TELEGRAM_API_HASH:
    app = Client("instagram_downloader_bot", api_id=int(TELEGRAM_API_ID), api_hash=TELEGRAM_API_HASH, bot_token=TELEGRAM_BOT_TOKEN)
else:
    logger.warning("API_ID or API_HASH not found. Running in bot token mode.")
    app = Client("instagram_downloader_bot", bot_token=TELEGRAM_BOT_TOKEN, no_updates=False)

# --- Bot Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user = message.from_user
    db_session = next(get_db(), None)
    add_or_update_user(db_session, user)

    if not await is_user_subscribed(client, user.id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{REQUIRED_CHANNEL_USERNAME}")],
            [InlineKeyboardButton("تحققت", callback_data="check_subscription")]
        ])
        await message.reply_text(
            f"""👋 أهلًا بك {user.mention}!

لاستخدام البوت، يرجى الاشتراك في قناتنا أولاً: @{REQUIRED_CHANNEL_USERNAME}

اضغط على الزر أدناه للاشتراك ثم اضغط على 'تحققت'.""",
            reply_markup=keyboard,
            quote=True
        )
        # No return here, send welcome message below if subscribed
    else: # User is subscribed
        await message.reply_text(
            f"👋 أهلًا بك {user.mention}!\nأرسل لي رابط منشور (صورة أو فيديو أو Reels) من انستقرام لتحميله.",
            quote=True
        )
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    user_id = message.from_user.id
    db_session = next(get_db(), None)

    if not db_session:
        await message.reply_text("عذرًا، ميزة الإحصائيات غير متاحة حاليًا.", quote=True)
        return

    # Admin stats
    if user_id in ADMIN_USER_IDS:
        total_users = get_total_users(db_session)
        total_downloads = get_total_downloads(db_session)
        await message.reply_text(
            f"📊 **إحصائيات البوت:**\n\n👤 إجمالي المستخدمين: {total_users}\n📥 إجمالي التحميلات الناجحة: {total_downloads}",
            quote=True
        )
    else:
        # User stats
        count, last_dl = get_user_stats(db_session, user_id)
        if count is not None:
            last_dl_str = last_dl.strftime("%Y-%m-%d %H:%M:%S UTC") if last_dl else "لم تقم بالتحميل بعد"
            await message.reply_text(
                f"📊 **إحصائياتك:**\n\n📥 عدد التحميلات: {count}\n🕒 آخر تحميل: {last_dl_str}",
                quote=True
            )
        else:
            await message.reply_text("حدث خطأ أثناء جلب إحصائياتك.", quote=True)


@app.on_message(filters.text & filters.private & ~filters.command("start") & ~filters.command("stats"))
async def handle_message(client: Client, message: Message):
    user = message.from_user
    text = message.text
    db_session = next(get_db(), None)
    add_or_update_user(db_session, user)

    # 1. Check subscription
    if not await is_user_subscribed(client, user.id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{REQUIRED_CHANNEL_USERNAME}") ],
            [InlineKeyboardButton("تحققت", callback_data="check_subscription")]
        ])
        await message.reply_text(
            f"⚠️ عذرًا {user.mention}، يجب عليك الاشتراك في القناة أولاً لاستخدام البوت: @{REQUIRED_CHANNEL_USERNAME}",
            reply_markup=keyboard,
            quote=True
        )
        return

    # 2. Validate Instagram URL
    url_match = re.search(INSTAGRAM_REGEX, text)
    if not url_match:
        await message.reply_text(
            "⚠️ الرابط الذي أرسلته لا يبدو كرابط منشور انستقرام صالح (صورة، فيديو، أو Reels). يرجى التأكد من الرابط وإعادة المحاولة.",
            quote=True
        )
        return

    instagram_url = url_match.group(0) # Get the full matched URL
    logger.info(f"User {user.id} sent URL: {instagram_url}")

    # 3. Process download
    status_message = await message.reply_text("⏳ جاري معالجة الرابط، يرجى الانتظار...", quote=True)

    media_url, media_type = await download_instagram_media(instagram_url)

    if media_url:
        try:
            if media_type == 'video':
                await client.send_video(message.chat.id, media_url, caption=f"تم التحميل بواسطة @{client.me.username}")
            elif media_type == 'image':
                await client.send_photo(message.chat.id, media_url, caption=f"تم التحميل بواسطة @{client.me.username}")
            else: # Handle cases where type might be unknown or different
                # Try sending as document as a fallback
                await client.send_document(message.chat.id, media_url, caption=f"تم التحميل بواسطة @{client.me.username}")
            
            log_download(db_session, user.id, instagram_url, success=True)
            await status_message.delete()
            logger.info(f"Media sent successfully to user {user.id} for URL: {instagram_url}")

        except FloodWait as e:
            logger.warning(f"Flood wait of {e.value} seconds when sending media to {user.id}.")
            await status_message.edit_text(f"⏳ نواجه بعض الضغط، سيتم إرسال الملف خلال {e.value} ثانية...")
            await asyncio.sleep(e.value + 1)
            # Retry sending after wait
            try:
                if media_type == 'video':
                    await client.send_video(message.chat.id, media_url, caption=f"تم التحميل بواسطة @{client.me.username}")
                elif media_type == 'image':
                    await client.send_photo(message.chat.id, media_url, caption=f"تم التحميل بواسطة @{client.me.username}")
                else:
                    await client.send_document(message.chat.id, media_url, caption=f"تم التحميل بواسطة @{client.me.username}")
                log_download(db_session, user.id, instagram_url, success=True)
                await status_message.delete()
            except Exception as retry_e:
                logger.error(f"Error sending media to {user.id} after flood wait: {retry_e}")
                await status_message.edit_text("❌ حدث خطأ أثناء إرسال الملف بعد الانتظار. يرجى المحاولة مرة أخرى.")
                log_download(db_session, user.id, instagram_url, success=False, error_message=str(retry_e))

        except Exception as e:
            logger.error(f"Error sending media to {user.id}: {e}")
            await status_message.edit_text("❌ حدث خطأ أثناء إرسال الملف. قد يكون الملف كبيرًا جدًا أو غير مدعوم.")
            log_download(db_session, user.id, instagram_url, success=False, error_message=str(e))
    else:
        await status_message.edit_text("❌ فشل تحميل الميديا من الرابط. قد يكون المنشور خاصًا، محذوفًا، أو أن هناك مشكلة في الخدمة الخارجية.")
        log_download(db_session, user.id, instagram_url, success=False, error_message="Failed to retrieve media URL from API")

@app.on_callback_query(filters.regex("^check_subscription$"))
async def check_subscription_callback(client: Client, callback_query: CallbackQuery):
    user = callback_query.from_user

    if await is_user_subscribed(client, user.id):
        await callback_query.answer("شكراً لاشتراكك! يمكنك الآن استخدام البوت.", show_alert=True)
        await callback_query.message.edit_text(
            f"✅ تم التحقق من اشتراكك {user.mention}!\n\nأرسل لي رابط منشور (صورة أو فيديو أو Reels) من انستقرام لتحميله."
        )       # Add user to DB after successful check if not already added
        db_session = next(get_db(), None)
        add_or_update_user(db_session, user)
    else:
        await callback_query.answer("لم يتم التحقق من اشتراكك بعد. يرجى التأكد من اشتراكك في القناة والمحاولة مرة أخرى.", show_alert=True)

# --- Flask App (Optional - for webhooks or simple status page) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!", 200

# Add more Flask routes if needed, e.g., for webhook
# @flask_app.route('/webhook', methods=['POST'])
# def webhook():
#     # Process Telegram update
#     return jsonify(success=True)

# --- Main Execution ---
async def main():
    try:
        logger.info("Starting Pyrogram client...")
        await app.start()
        me = await app.get_me()
        logger.info(f"Bot @{me.username} started successfully!")
        # Keep the bot running
        await asyncio.Event().wait() # Keep running indefinitely
    except Exception as e:
        logger.critical(f"Critical error during bot startup or runtime: {e}")
    finally:
        logger.info("Stopping Pyrogram client...")
        if app.is_initialized:
             await app.stop()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    # You can choose to run Flask or just the Pyrogram bot
    # To run Flask (e.g., for webhooks or status page):
    # from threading import Thread
    # bot_thread = Thread(target=asyncio.run, args=(main(),))
    # bot_thread.start()
    # flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
    
    # To run only the Pyrogram bot (polling mode):
    asyncio.run(main())

