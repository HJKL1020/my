# Telegram Bot Logic
import os
import logging
import re
import asyncio
import tempfile
import shutil
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

import instaloader

from app import create_app, db
from app.models import User, Download, Setting # Assuming Download model exists
from datetime import datetime, timezone

# --- Configuration & Globals ---

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid GET request spam
logging.getLogger("httpx") .setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load config from environment
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
REQUIRED_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID") # e.g., -1001234567890 (numeric ID)
REQUIRED_CHANNEL_USERNAME = os.environ.get("REQUIRED_CHANNEL_USERNAME", "YOUR_CHANNEL_USERNAME") # e.g., @HJKL966
ADMIN_USER_IDS = [int(admin_id.strip()) for admin_id in os.environ.get("ADMIN_USER_IDS", "").split(",") if admin_id.strip().isdigit()]

# Instaloader instance (configure as needed)
L = instaloader.Instaloader(
    download_pictures=True,
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    post_metadata_txt_pattern="", # Avoid creating txt files
    max_connection_attempts=3,
    request_timeout=15,
)
# L.login(username, password) # Optional: for private profiles or potentially better quality/rate limits

# --- Helper Functions ---

async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int) -> tuple[bool, str | None]:
    """Checks if a user is a member of the required channel. Returns (is_subscribed, status)."""
    if not REQUIRED_CHANNEL_ID:
        logger.warning("Required channel ID not configured. Skipping subscription check.")
        return True, "not_configured"

    if user_id in ADMIN_USER_IDS:
        logger.info(f"User {user_id} is an admin. Skipping subscription check.")
        return True, "admin"

    try:
        # Ensure REQUIRED_CHANNEL_ID is an integer if it's a numeric string
        channel_id_int = int(REQUIRED_CHANNEL_ID)
        member = await context.bot.get_chat_member(chat_id=channel_id_int, user_id=user_id)
        status = member.status
        logger.info(f"User {user_id} status in channel {channel_id_int}: {status}")
        # Valid statuses: administrator, creator, member. 'restricted' might be ok sometimes but often not.
        # 'left' or 'kicked' means not subscribed.
        is_member = status in ["administrator", "creator", "member"]
        return is_member, status

    except ValueError:
        logger.error(f"Invalid REQUIRED_CHANNEL_ID format: {REQUIRED_CHANNEL_ID}. Must be numeric.")
        # Notify admin or raise a configuration error?
        # For now, block the user as channel is misconfigured.
        await context.bot.send_message(chat_id, "حدث خطأ في إعدادات البوت. يرجى التواصل مع المسؤول.")
        return False, "config_error"
    except TelegramError as e:
        logger.error(f"Error checking subscription for user {user_id} in channel {REQUIRED_CHANNEL_ID}: {e}")
        # Handle specific errors
        if "user not found" in str(e).lower():
            # User is not in the channel
            return False, "not_found"
        elif "chat not found" in str(e).lower() or "invalid chat id" in str(e).lower():
            logger.error(f"Bot cannot access channel {REQUIRED_CHANNEL_ID}. Is it public or is the bot an admin?")
            await context.bot.send_message(chat_id, "حدث خطأ في الوصول إلى القناة المطلوبة. يرجى التواصل مع المسؤول.")
            return False, "channel_error" # Treat as not subscribed due to config/access issue
        elif "bot was kicked" in str(e).lower():
             logger.error(f"Bot was kicked from channel {REQUIRED_CHANNEL_ID}.")
             await context.bot.send_message(chat_id, "حدث خطأ في الوصول إلى القناة المطلوبة. يرجى التواصل مع المسؤول.")
             return False, "bot_kicked"
        else:
            # Other Telegram errors (e.g., network, rate limits)
            # Retry might be possible, but for now, assume not subscribed
            return False, "telegram_error"
    except Exception as e:
        logger.error(f"Unexpected error checking subscription for user {user_id}: {e}", exc_info=True)
        return False, "unexpected_error" # Assume not subscribed on unknown error

def get_channel_invite_link() -> str | None:
    """Gets the channel invite link based on configuration."""
    if not REQUIRED_CHANNEL_USERNAME:
        return None
    username = REQUIRED_CHANNEL_USERNAME.lstrip("@")
    return f"https://t.me/{username}"

async def send_subscription_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str | None = None)  -> None:
    """Sends the message asking the user to subscribe."""
    invite_link = get_channel_invite_link()
    if not invite_link or not REQUIRED_CHANNEL_USERNAME:
        await update.effective_message.reply_text("عذرًا، لم يتم تكوين قناة الاشتراك بشكل صحيح. يرجى التواصل مع المسؤول.")
        return

    keyboard = [
        [InlineKeyboardButton("1. اشتراك في القناة", url=invite_link)],
        [InlineKeyboardButton("2. تحقق من الاشتراك", callback_data="check_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    default_text = (
        f"عذراً، لاستخدام البوت يجب عليك الاشتراك في القناة أولاً: {REQUIRED_CHANNEL_USERNAME}\n\n"
        f"1. اضغط على الزر الأول للاشتراك.\n"
        f"2. اضغط على الزر الثاني للتحقق بعد اشتراكك."
    )
    text_to_send = message_text or default_text
    if update.callback_query:
        # If called from a callback, edit the original message
        try:
            await update.callback_query.edit_message_text(text=text_to_send, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except TelegramError as e:
            if "Message is not modified" in str(e):
                await update.callback_query.answer("لم يتغير شيء. يرجى الاشتراك أولاً ثم التحقق.")
            else:
                logger.error(f"Error editing message for subscription prompt: {e}")
                # Fallback: send a new message if editing fails
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text_to_send, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        # If called from a regular message, send a new message
        await update.effective_message.reply_text(text=text_to_send, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# --- Database Interaction within App Context ---

def get_or_create_user(telegram_user):
    """Gets or creates a user in the database within Flask app context."""
    user = db.session.query(User).filter_by(telegram_user_id=telegram_user.id).first()
    now = datetime.now(timezone.utc)
    if not user:
        logger.info(f"New user: {telegram_user.id}. Adding to database.")
        user = User(
            telegram_user_id=telegram_user.id,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            username=telegram_user.username,
            joined_at=now,
            last_active_at=now,
            is_subscribed=False # Initial state
        )
        db.session.add(user)
    else:
        logger.info(f"Existing user: {telegram_user.id}. Updating last active time.")
        user.last_active_at = now
        # Optionally update names if they changed
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        user.username = telegram_user.username
    try:
        db.session.commit()
        # Refresh user object to get ID if it was new
        db.session.refresh(user)
        return user
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database error handling user {telegram_user.id}: {e}", exc_info=True)
        return None

def update_user_subscription_status(user_id: int, is_subscribed: bool, status: str | None):
    """Updates the user's subscription status in the database."""
    user = db.session.query(User).filter_by(telegram_user_id=user_id).first()
    if user:
        # Logic for unsubscribe penalty:
        # If user was previously marked as subscribed in DB, but now is not
        if user.is_subscribed and not is_subscribed and status in ["left", "kicked", "not_found"]:
            logger.warning(f"User {user_id} unsubscribed from the channel. Banning user.")
            user.is_banned = True
            user.ban_reason = f"Unsubscribed from channel ({status})"
            # Optionally set ban_expires_at if ban is temporary

        user.is_subscribed = is_subscribed
        user.last_active_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error updating subscription status for user {user_id}: {e}", exc_info=True)

def record_download(user_id: int, url: str, success: bool, error_message: str | None = None):
    """Records a download attempt in the database."""
    user = db.session.query(User).filter_by(telegram_user_id=user_id).first()
    if user:
        download = Download(
            user_id=user.id,
            url=url,
            downloaded_at=datetime.now(timezone.utc),
            success=success,
            error_message=error_message
        )
        db.session.add(download)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error saving download record for user {user_id}: {e}", exc_info=True)

# --- Instagram Download Logic ---

async def download_instagram_post(url: str, user_id: int) -> tuple[list[Path], str | None, Path | None]:
    """Downloads media from an Instagram URL using Instaloader. Returns list of paths, error message, and temp dir path."""
    shortcode = None
    match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_\-]+)", url)
    if match:
        shortcode = match.group(1)

    if not shortcode:
        logger.warning(f"Could not extract shortcode from URL: {url}")
        return [], "لم يتم التعرف على رابط انستقرام صالح.", None

    temp_dir_path = None
    downloaded_files = []
    error_message = None

    try:
        # Create a unique temporary directory for this download
        temp_dir_path = Path(tempfile.mkdtemp(prefix=f"insta_{user_id}_{shortcode}_"))
        logger.info(f"Attempting download for shortcode {shortcode} into {temp_dir_path}")

        # Run instaloader download in a separate thread to avoid blocking asyncio loop
        def sync_download():
            try:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                L.download_post(post, target=temp_dir_path)
                return True
            except instaloader.exceptions.PrivateProfileNotFollowedException:
                logger.warning(f"Failed to download {shortcode}: Private profile not followed.")
                return "private"
            except instaloader.exceptions.ProfileNotExistsException:
                 logger.warning(f"Failed to download {shortcode}: Profile does not exist.")
                 return "profile_not_exist"
            except instaloader.exceptions.StoryItemUnavailableException:
                 logger.warning(f"Failed to download {shortcode}: Story item unavailable.")
                 return "story_unavailable"
            except instaloader.exceptions.QueryReturnedNotFoundException:
                logger.warning(f"Failed to download {shortcode}: Post not found (404). Might be deleted or private.")
                return "not_found"
            except instaloader.exceptions.LoginRequiredException:
                logger.warning(f"Failed to download {shortcode}: Login required.")
                return "login_required"
            except instaloader.exceptions.ConnectionException as e:
                logger.error(f"Instaloader connection error for {shortcode}: {e}")
                return "connection_error"
            except instaloader.exceptions.TooManyRequestsException:
                 logger.error(f"Instaloader hit rate limit for {shortcode}. Need to wait.")
                 return "rate_limit"
            except Exception as e:
                logger.error(f"Unexpected Instaloader error for {shortcode}: {e}", exc_info=True)
                return "instaloader_error"

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, sync_download)

        if result is True:
            # Find downloaded media files (jpg, mp4)
            for item in temp_dir_path.iterdir():
                if item.is_file() and item.suffix.lower() in [".jpg", ".jpeg", ".png", ".mp4"]:
                    downloaded_files.append(item)
            if not downloaded_files:
                logger.warning(f"Instaloader finished for {shortcode} but no media files found in {temp_dir_path}")
                error_message = "لم يتم العثور على وسائط بعد التحميل. قد يكون المنشور نصيًا فقط."
        else:
            # Handle specific error messages from instaloader
            if result == "private": error_message = "لا يمكن تحميل المنشور، الحساب خاص أو أنك لا تتابعه."
            elif result == "profile_not_exist": error_message = "لا يمكن تحميل المنشور، الحساب غير موجود."
            elif result == "story_unavailable": error_message = "لا يمكن تحميل الستوري، قد تكون انتهت صلاحيتها."
            elif result == "not_found": error_message = "لم يتم العثور على المنشور. قد يكون محذوفًا أو خاصًا."
            elif result == "login_required": error_message = "يتطلب هذا المنشور تسجيل الدخول إلى انستقرام لتحميله (غير مدعوم حاليًا)."
            elif result == "connection_error": error_message = "حدث خطأ في الاتصال بانستقرام. يرجى المحاولة مرة أخرى."
            elif result == "rate_limit": error_message = "لقد وصلنا إلى حد الطلبات مع انستقرام. يرجى الانتظار والمحاولة لاحقًا."
            else: error_message = "حدث خطأ غير متوقع أثناء محاولة التحميل من انستقرام."

    except Exception as e:
        logger.error(f"Error during download process for {url}: {e}", exc_info=True)
        error_message = "حدث خطأ عام أثناء عملية التحميل."
        # Clean up temp dir even on general error if it was created
        if temp_dir_path and temp_dir_path.exists():
             try:
                 shutil.rmtree(temp_dir_path)
                 logger.info(f"Cleaned up temp directory on error: {temp_dir_path}")
             except Exception as ce:
                 logger.error(f"Error cleaning up temp directory {temp_dir_path} on error: {ce}")
        temp_dir_path = None # Ensure it's not returned for cleanup again

    # Return the list of files, error message, and the temp dir path for cleanup
    return downloaded_files, error_message, temp_dir_path

async def send_downloaded_media(update: Update, context: ContextTypes.DEFAULT_TYPE, files: list[Path]):
    """Sends the downloaded media files to the user."""
    media_group = []
    capt = f"تم التحميل بواسطة: @{context.bot.username}"
    sent_media = False

    try:
        for file_path in files:
            if file_path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                media_group.append(InputMediaPhoto(media=open(file_path, "rb")))
            elif file_path.suffix.lower() == ".mp4":
                media_group.append(InputMediaVideo(media=open(file_path, "rb")))

        if not media_group:
            logger.warning("No media to send, although files list was not empty.")
            await update.effective_message.reply_text("لم يتم العثور على وسائط صالحة للإرسال.")
            return False # Indicate failure

        # Add caption to the first item only
        first_item = media_group[0]
        if hasattr(first_item, 'caption'):
            first_item.caption = capt
        elif isinstance(first_item, (InputMediaPhoto, InputMediaVideo)):
             # Recreate with caption if needed
             if isinstance(first_item, InputMediaPhoto):
                 media_group[0] = InputMediaPhoto(media=first_item.media, caption=capt)
             elif isinstance(first_item, InputMediaVideo):
                 media_group[0] = InputMediaVideo(media=first_item.media, caption=capt)

        # Send as media group if multiple items, otherwise single photo/video
        if len(media_group) > 1:
            logger.info(f"Sending {len(media_group)} items as media group to {update.effective_user.id}")
            # Split into chunks of 10 if necessary (Telegram limit)
            for i in range(0, len(media_group), 10):
                chunk = media_group[i:i+10]
                await context.bot.send_media_group(chat_id=update.effective_chat.id, media=chunk)
            sent_media = True
        elif len(media_group) == 1:
            item = media_group[0]
            logger.info(f"Sending single item ({item.__class__.__name__}) to {update.effective_user.id}")
            if isinstance(item, InputMediaPhoto):
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=item.media, caption=item.caption)
                sent_media = True
            elif isinstance(item, InputMediaVideo):
                await context.bot.send_video(chat_id=update.effective_chat.id, video=item.media, caption=item.caption)
                sent_media = True

    except TelegramError as e:
        logger.error(f"Failed to send media to {update.effective_user.id}: {e}")
        # Try sending a text message about the error
        try:
            await update.effective_message.reply_text(f"حدث خطأ أثناء إرسال الوسائط: {e}")
        except Exception as inner_e:
            logger.error(f"Failed to send error message about media failure: {inner_e}")
        sent_media = False # Mark as failed
    except Exception as e:
        logger.error(f"Unexpected error sending media: {e}", exc_info=True)
        try:
            await update.effective_message.reply_text("حدث خطأ غير متوقع أثناء إرسال الوسائط.")
        except Exception as inner_e:
             logger.error(f"Failed to send error message about unexpected media failure: {inner_e}")
        sent_media = False # Mark as failed
    finally:
        # Close file handles if they are open (important!)
        for item in media_group:
            if hasattr(item.media, 'close') and not item.media.closed:
                try:
                    item.media.close()
                except Exception as close_e:
                    logger.error(f"Error closing media file handle: {close_e}")
        return sent_media

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    telegram_user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"Received /start command from user {telegram_user.id} ({telegram_user.username})")

    # Use Flask app context to interact with the database
    app = context.application.flask_app
    with app.app_context():
        user = get_or_create_user(telegram_user)
        if not user:
            await update.message.reply_text("حدث خطأ في الخادم، يرجى المحاولة مرة أخرى لاحقاً.")
            return

        # Check subscription status
        is_subscribed, status = await is_user_subscribed(context, telegram_user.id, chat_id)
        update_user_subscription_status(user.telegram_user_id, is_subscribed, status)

        # Re-fetch user in case status changed (e.g., banned)
        user = db.session.query(User).filter_by(telegram_user_id=telegram_user.id).first()

        if user.is_banned:
             await update.message.reply_text(f"عذراً، لقد تم حظرك من استخدام البوت بسبب: {user.ban_reason}")
             return

        if is_subscribed:
            await update.message.reply_text(
                f"أهلاً بك {telegram_user.first_name}!\n\n"
                f"يمكنك الآن إرسال روابط انستقرام (صور، فيديوهات، ريلز) لتحميلها."
            )
        else:
            await send_subscription_prompt(update, context)

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the callback query for checking subscription."""
    query = update.callback_query
    telegram_user = query.from_user
    chat_id = update.effective_chat.id
    await query.answer() # Answer the callback query first
    logger.info(f"Received check_subscription callback from user {telegram_user.id}")

    app = context.application.flask_app
    with app.app_context():
        user = get_or_create_user(telegram_user) # Ensure user exists
        if not user:
            await context.bot.send_message(chat_id, "حدث خطأ في الخادم، يرجى المحاولة مرة أخرى لاحقاً.")
            return

        is_subscribed, status = await is_user_subscribed(context, telegram_user.id, chat_id)
        update_user_subscription_status(user.telegram_user_id, is_subscribed, status)

        # Re-fetch user in case status changed (e.g., banned)
        user = db.session.query(User).filter_by(telegram_user_id=telegram_user.id).first()

        if user.is_banned:
             # Edit the message to show ban reason
             try:
                 await query.edit_message_text(text=f"عذراً، لقد تم حظرك من استخدام البوت بسبب: {user.ban_reason}")
             except TelegramError as e:
                 logger.error(f"Error editing message to show ban status: {e}")
             return

        if is_subscribed:
            try:
                await query.edit_message_text(
                    text="شكراً لاشتراكك! يمكنك الآن إرسال روابط انستقرام لتحميلها."
                )
            except TelegramError as e:
                 logger.error(f"Error editing message after successful subscription check: {e}")
        else:
            # Re-send the prompt, possibly with a slightly different message
            await send_subscription_prompt(update, context, message_text=
                f"لم يتم اكتشاف اشتراكك بعد. يرجى التأكد من اشتراكك في {REQUIRED_CHANNEL_USERNAME} ثم الضغط على زر التحقق مرة أخرى."
            )

# --- Message Handlers ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular messages, looking for Instagram links."""
    if not update.message or not update.message.text:
        return # Ignore empty messages or updates without text

    telegram_user = update.effective_user
    chat_id = update.effective_chat.id
    text = update.message.text
    logger.info(f"Received message from user {telegram_user.id}: {text[:100]}...") # Log only first 100 chars

    # Use Flask app context
    app = context.application.flask_app
    with app.app_context():
        # 1. Get/Create User & Check Ban Status
        user = get_or_create_user(telegram_user)
        if not user:
            await update.message.reply_text("حدث خطأ في الخادم، يرجى المحاولة مرة أخرى لاحقاً.")
            return
        if user.is_banned:
            await update.message.reply_text(f"عذراً، لقد تم حظرك من استخدام البوت بسبب: {user.ban_reason}")
            return

        # 2. Check Subscription Status
        is_subscribed, status = await is_user_subscribed(context, telegram_user.id, chat_id)
        update_user_subscription_status(user.telegram_user_id, is_subscribed, status)

        # Re-fetch user in case status changed (e.g., banned)
        user = db.session.query(User).filter_by(telegram_user_id=telegram_user.id).first()
        if user.is_banned: # Check ban status again after potential update
             await update.message.reply_text(f"عذراً، لقد تم حظرك من استخدام البوت بسبب: {user.ban_reason}")
             return

        if not is_subscribed:
            await send_subscription_prompt(update, context)
            return

        # 3. Look for Instagram URL
        # Allow URLs with or without www., http/https, and trailing slash
        url_match = re.search(r"https?://(?:www\.) ?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_\-]+)/?", text)
        if not url_match:
            logger.info(f"Message from {telegram_user.id} is not a valid Instagram link.")
            # Optionally reply if message is not /start and not an insta link
            await update.message.reply_text("يرجى إرسال رابط منشور انستقرام صالح (صورة، فيديو، ريلز).")
            return # Return after sending the message

        insta_url = url_match.group(0) # Get the full matched URL
        shortcode = url_match.group(1) # Get the shortcode
        logger.info(f"Detected Instagram URL from {telegram_user.id}: {insta_url} (Shortcode: {shortcode})")

        # 4. Attempt Download
        status_message = await update.message.reply_text("⏳ جارٍ التحميل من انستقرام... يرجى الانتظار.", quote=True)
        downloaded_files = []
        temp_dir_to_clean = None
        download_success = False
        error_msg = None

        try:
            downloaded_files, error_msg, temp_dir_to_clean = await download_instagram_post(insta_url, telegram_user.id)

            if downloaded_files:
                # 5. Send Media
                sent_successfully = await send_downloaded_media(update, context, downloaded_files)
                if sent_successfully:
                    download_success = True
                    # Try deleting status message, ignore if fails (e.g., already deleted)
                    try: await status_message.delete()
                    except: pass
                else:
                    # Error message should have been sent by send_downloaded_media
                    error_msg = error_msg or "Failed to send media after download."
                    # Try editing status message, ignore if fails
                    try: await status_message.edit_text(error_msg if error_msg else "حدث خطأ غير متوقع أثناء إرسال الوسائط.")
                    except: pass
            else:
                # Handle download errors (error_msg should be set)
                # Try editing status message, ignore if fails
                try: await status_message.edit_text(error_msg if error_msg else "حدث خطأ غير معروف أثناء التحميل.")
                except: pass

        except Exception as e:
            logger.error(f"Error in download/send pipeline for {insta_url}: {e}", exc_info=True)
            error_msg = error_msg or "حدث خطأ فادح أثناء معالجة طلبك."
            try:
                await status_message.edit_text(error_msg)
            except TelegramError:
                 # If editing fails (e.g., message deleted), send new message
                 await update.message.reply_text(error_msg)
        finally:
            # 6. Record Download Attempt
            record_download(user.telegram_user_id, insta_url, download_success, error_msg)

            # 7. Cleanup Temporary Files
            if temp_dir_to_clean:
                try:
                    shutil.rmtree(temp_dir_to_clean)
                    logger.info(f"Cleaned up temporary directory: {temp_dir_to_clean}")
                except Exception as e:
                    logger.error(f"Error cleaning up temp directory {temp_dir_to_clean}: {e}", exc_info=True)

# --- Error Handler ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    # Optionally notify admin about critical errors
    # You can send a message to your admin ID here
    # admin_chat_id = ADMIN_USER_IDS[0] if ADMIN_USER_IDS else None
    # if admin_chat_id:
    #     try:
    #         error_text = f"Error: {context.error}\nUpdate: {update}"
    #         await context.bot.send_message(chat_id=admin_chat_id, text=error_text[:4000]) # Limit message length
    #     except Exception as e:
    #         logger.error(f"Failed to send error notification to admin: {e}")

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

    # Add the error handler
    application.add_error_handler(error_handler)

    # Start the Bot (using polling for simplicity, webhooks are better for production)
    logger.info("Bot polling started.")
    application.run_polling()

# --- Allow running standalone for testing (requires manual app context) ---
if __name__ == "__main__":
    # This allows running the bot standalone for testing, but needs Flask app context
    # For proper integration, run via run_telegram_bot.py or similar
    logger.warning("Running bot standalone. Database interactions might fail without Flask app context.")
    # Example (adjust based on your actual app structure):
    # app = create_app()
    # with app.app_context():
    #     run_bot(app)
    pass # Avoid running standalone by default

