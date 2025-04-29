# Telegram Bot Logic
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from app import create_app, db
from app.models import User, Download, Setting
from datetime import datetime, timezone

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration --- (Load from environment or config file)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
REQUIRED_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID") # e.g., -1001234567890 (numeric ID) or "@HJKL966"
REQUIRED_CHANNEL_USERNAME = "@HJKL966" # For display and joining link

# --- Helper Functions ---

async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Checks if a user is a member of the required channel."""
    if not REQUIRED_CHANNEL_ID:
        logger.warning("Required channel ID not configured. Skipping subscription check.")
        return True # Skip check if channel ID is not set
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        logger.info(f"User {user_id} status in channel {REQUIRED_CHANNEL_ID}: {member.status}")
        # Valid statuses: administrator, creator, member, restricted (sometimes)
        return member.status in ["administrator", "creator", "member"]
    except telegram.error.BadRequest as e:
        # Handle cases like "user not found" or "chat not found"
        logger.error(f"Error checking subscription for user {user_id} in channel {REQUIRED_CHANNEL_ID}: {e}")
        if "user not found" in str(e):
            # User might have blocked the bot or deleted account
            return False
        # If chat not found, the channel ID might be wrong
        # Consider returning True to avoid blocking users due to config error, or log and return False
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking subscription for user {user_id}: {e}")
        return False # Assume not subscribed on error

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    telegram_user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"Received /start command from user {telegram_user.id} ({telegram_user.username})")

    # Use Flask app context to interact with the database
    app = context.application.flask_app
    with app.app_context():
        user = db.session.query(User).filter_by(telegram_user_id=telegram_user.id).first()
        if not user:
            logger.info(f"New user: {telegram_user.id}. Adding to database.")
            user = User(
                telegram_user_id=telegram_user.id,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                username=telegram_user.username,
                joined_at=datetime.now(timezone.utc),
                last_active_at=datetime.now(timezone.utc)
            )
            db.session.add(user)
        else:
            logger.info(f"Existing user: {telegram_user.id}. Updating last active time.")
            user.last_active_at = datetime.now(timezone.utc)
            # Optionally update names if they changed
            user.first_name = telegram_user.first_name
            user.last_name = telegram_user.last_name
            user.username = telegram_user.username

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error handling user {telegram_user.id}: {e}")
            await update.message.reply_text("حدث خطأ في الخادم، يرجى المحاولة مرة أخرى لاحقاً.")
            return

        # Check subscription status
        subscribed = await is_user_subscribed(context, telegram_user.id)

        if subscribed:
            await update.message.reply_text(
                f"أهلاً بك {telegram_user.first_name}! يمكنك الآن إرسال روابط انستقرام لتحميلها."
            )
        else:
            channel_username_no_at = REQUIRED_CHANNEL_USERNAME.lstrip("@")
            keyboard = [
                [InlineKeyboardButton("اشتراك في القناة", url=f"https://t.me/{channel_username_no_at}")],
                [InlineKeyboardButton("تحقق من الاشتراك", callback_data="check_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"مرحباً {telegram_user.first_name}! لاستخدام البوت، يرجى الاشتراك في قناتنا أولاً: {REQUIRED_CHANNEL_USERNAME}\n\nبعد الاشتراك، اضغط على زر التحقق.",
                reply_markup=reply_markup
            )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the callback query for checking subscription."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer() # Answer the callback query first

    logger.info(f"Received check_subscription callback from user {user_id}")

    subscribed = await is_user_subscribed(context, user_id)

    if subscribed:
        await query.edit_message_text(
            text="شكراً لاشتراكك! يمكنك الآن إرسال روابط انستقرام لتحميلها."
        )
        # Update user's last active time in DB
        app = context.application.flask_app
        with app.app_context():
            user = db.session.query(User).filter_by(telegram_user_id=user_id).first()
            if user:
                user.last_active_at = datetime.now(timezone.utc)
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Database error updating last active time for user {user_id}: {e}")
    else:
        # Re-send the initial message with buttons if still not subscribed
        channel_username_no_at = REQUIRED_CHANNEL_USERNAME.lstrip("@")
        keyboard = [
            [InlineKeyboardButton("اشتراك في القناة", url=f"https://t.me/{channel_username_no_at}")],
            [InlineKeyboardButton("تحقق من الاشتراك", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                text=f"لم يتم اكتشاف اشتراكك بعد. يرجى التأكد من اشتراكك في {REQUIRED_CHANNEL_USERNAME} ثم الضغط على زر التحقق مرة أخرى.",
                reply_markup=reply_markup
            )
        except telegram.error.BadRequest as e:
            # Handle case where message hasn't changed (user clicks check multiple times without subscribing)
            if "Message is not modified" in str(e):
                logger.info(f"User {user_id} clicked check subscription again, message not modified.")
            else:
                raise e

# --- Message Handlers ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular messages, looking for Instagram links."""
    user_id = update.effective_user.id
    text = update.message.text

    logger.info(f"Received message from user {user_id}: {text}")

    # Use Flask app context
    app = context.application.flask_app
    with app.app_context():
        # 1. Check if user exists and is not banned
        user = db.session.query(User).filter_by(telegram_user_id=user_id).first()
        if not user:
            # Should not happen if /start is used first, but handle defensively
            await update.message.reply_text("يرجى استخدام الأمر /start أولاً.")
            return
        if user.is_banned:
            await update.message.reply_text("عذراً، لقد تم حظرك من استخدام البوت.")
            return

        # 2. Update last active time
        user.last_active_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error updating last active time for user {user_id}: {e}")
            # Continue processing even if DB update fails here

        # 3. Check subscription (redundant if using /start flow correctly, but good failsafe)
        subscribed = await is_user_subscribed(context, user_id)
        if not subscribed:
            channel_username_no_at = REQUIRED_CHANNEL_USERNAME.lstrip("@")
            keyboard = [
                [InlineKeyboardButton("اشتراك في القناة", url=f"https://t.me/{channel_username_no_at}")],
                [InlineKeyboardButton("تحقق من الاشتراك", callback_data="check_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"يرجى الاشتراك في قناتنا أولاً: {REQUIRED_CHANNEL_USERNAME}\n\nبعد الاشتراك، اضغط على زر التحقق.",
                reply_markup=reply_markup
            )
            return

        # 4. Check if the message contains an Instagram link
        # Basic check, can be improved with regex
        if "instagram.com/" in text:
            await handle_instagram_link(update, context, user, text)
        else:
            await update.message.reply_text("يرجى إرسال رابط منشور أو مقطع ريلز أو ستوري من انستقرام.")

async def handle_instagram_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, url: str) -> None:
    """Handles the logic for downloading Instagram content."""
    logger.info(f"Processing Instagram link {url} for user {user.telegram_user_id}")
    await update.message.reply_text("جارٍ معالجة الرابط... قد يستغرق الأمر بعض الوقت.")

    # !!! Placeholder for Instaloader logic !!!
    # This part is complex and needs careful implementation:
    # 1. Initialize Instaloader (potentially with login credentials from config/db)
    # 2. Handle different types of links (post, reel, story, profile)
    # 3. Download the media (video, image)
    # 4. Handle potential errors (private account, invalid link, rate limits, login required)
    # 5. Send the downloaded media back to the user
    # 6. Record the download in the database

    download_status = "failed"
    error_msg = "ميزة التحميل قيد التطوير حالياً."
    content_type = "unknown"

    try:
        # --- Start Placeholder Logic ---
        # Simulate processing time
        # import time
        # time.sleep(5)

        # Simulate success/failure
        # download_status = "success"
        # error_msg = None
        # content_type = "video" # or "image"
        # await update.message.reply_video(video=open("path/to/downloaded/video.mp4", "rb"), caption="تم التحميل بنجاح!")
        # --- End Placeholder Logic ---

        # Replace placeholder with actual Instaloader call
        await update.message.reply_text(error_msg)

    except Exception as e:
        logger.error(f"Error processing Instagram link {url} for user {user.telegram_user_id}: {e}")
        error_msg = f"حدث خطأ غير متوقع أثناء معالجة الرابط: {e}"
        await update.message.reply_text(error_msg)
        download_status = "failed"

    # Record download attempt in DB (even if failed)
    app = context.application.flask_app
    with app.app_context():
        download_record = Download(
            user_id=user.id,
            content_type=content_type,
            content_url=url,
            status=download_status,
            error_message=error_msg,
            downloaded_at=datetime.now(timezone.utc)
        )
        db.session.add(download_record)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error saving download record for user {user.telegram_user_id}: {e}")

# --- Main Bot Function ---

def run_bot(flask_app):
    """Starts the Telegram bot."""
    if not BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot start.")
        return

    logger.info("Starting Telegram bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    # Store flask_app instance in bot application context for database access in handlers
    application.flask_app = flask_app

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot (using polling for simplicity, webhooks are better for production)
    logger.info("Bot polling started.")
    application.run_polling()

if __name__ == "__main__":
    # This allows running the bot standalone for testing, but needs Flask app context
    # For proper integration, run via run.py or similar
    logger.warning("Running bot standalone. Database interactions might fail without Flask app context.")
    # You might need to manually create app context here for standalone testing
    # app = create_app()
    # with app.app_context():
    #     run_bot(app)
    pass # Avoid running standalone by default

