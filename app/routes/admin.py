# Placeholder for admin dashboard routes
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required
from app import db
from app.models import User

bp = Blueprint("admin", __name__)

@bp.route("/dashboard")
@login_required # Protect this route
def dashboard():
    # This will render the admin dashboard template
    return render_template("admin/dashboard.html")

@bp.route("/users")
@login_required
def users_list():
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("ADMIN_USERS_PER_PAGE", 15) # Configurable items per page
    users = db.session.query(User).order_by(User.joined_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template("admin/users.html", users=users)

@bp.route("/users/<int:user_id>/ban", methods=["GET"]) # Use GET for simplicity, POST is better practice
@login_required
def ban_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_banned = True
        # Add ban reason later if needed
        try:
            db.session.commit()
            flash(f"تم حظر المستخدم {user.username or user.telegram_user_id} بنجاح.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"حدث خطأ أثناء حظر المستخدم: {e}", "danger")
    else:
        flash("المستخدم غير موجود.", "warning")
    return redirect(url_for("admin.users_list", page=request.args.get("page", 1)))

@bp.route("/users/<int:user_id>/unban", methods=["GET"]) # Use GET for simplicity, POST is better practice
@login_required
def unban_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_banned = False
        user.ban_reason = None # Clear ban reason
        try:
            db.session.commit()
            flash(f"تم إلغاء حظر المستخدم {user.username or user.telegram_user_id} بنجاح.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"حدث خطأ أثناء إلغاء حظر المستخدم: {e}", "danger")
    else:
        flash("المستخدم غير موجود.", "warning")
    return redirect(url_for("admin.users_list", page=request.args.get("page", 1)))

# Add other admin routes here later (messages, settings, etc.)



from app.models import User, Setting # Add Setting import
from datetime import datetime, timezone # Import datetime

# ... (previous code) ...

@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        try:
            settings_to_update = [
                "telegram_channel_url",
                "tiktok_profile_url",
                "bot_username",
                "warning_message_text",
                "warning_message_color"
            ]
            for key in settings_to_update:
                value = request.form.get(key)
                if value is not None:
                    setting = db.session.get(Setting, key)
                    if setting:
                        setting.value = value
                        setting.last_updated_at = datetime.now(timezone.utc)
                        # Assuming current_user is the logged-in admin
                        # setting.last_updated_by_admin_id = current_user.id
                    else:
                        # Create new setting if it doesn't exist
                        new_setting = Setting(
                            key=key,
                            value=value,
                            # last_updated_by_admin_id=current_user.id,
                            last_updated_at=datetime.now(timezone.utc)
                            # Add description if needed
                        )
                        db.session.add(new_setting)
            db.session.commit()
            flash("تم تحديث الإعدادات بنجاح!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"حدث خطأ أثناء تحديث الإعدادات: {e}", "danger")
        return redirect(url_for("admin.settings"))

    # For GET request
    try:
        settings_keys = [
            "telegram_channel_url",
            "tiktok_profile_url",
            "bot_username",
            "warning_message_text",
            "warning_message_color"
        ]
        settings_data = {}
        for key in settings_keys:
            setting = db.session.get(Setting, key)
            if setting:
                settings_data[key] = setting.value
            else:
                # Provide default values if setting not found in DB
                if key == "warning_message_text":
                    settings_data[key] = "يمنع استخدام البوت لتحميل محتوى غير اخلاقي ويتم حظر اي شخص"
                elif key == "warning_message_color":
                    settings_data[key] = "red"
                else:
                    settings_data[key] = ""

    except Exception as e:
        flash(f"حدث خطأ أثناء تحميل الإعدادات: {e}", "danger")
        settings_data = {}

    return render_template("admin/settings.html", settings=settings_data)

# ... (rest of the code) ...



import telegram
import threading
import os
from app.models import User, Setting, Message # Add Message import
from datetime import datetime, timezone # Import datetime

# Function to send message in a background thread
def send_telegram_message_async(bot_token, chat_id, text):
    try:
        bot = telegram.Bot(token=bot_token)
        # Using await inside async function if library supports it, or run_sync for sync context
        # For simplicity here, assuming sync call works or using a simple thread
        bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        current_app.logger.info(f"Message sent to {chat_id}")
    except Exception as e:
        current_app.logger.error(f"Failed to send message to {chat_id}: {e}")

# ... (previous code) ...

@bp.route("/broadcast", methods=["GET", "POST"])
@login_required
def broadcast():
    if request.method == "POST":
        target_group = request.form.get("target_group")
        message_text = request.form.get("message_text")
        bot_token = current_app.config.get("TELEGRAM_BOT_TOKEN")

        if not message_text:
            flash("نص الرسالة لا يمكن أن يكون فارغاً.", "warning")
            return redirect(url_for("admin.broadcast"))

        if not bot_token:
            flash("لم يتم تكوين توكن بوت التليجرام في الإعدادات.", "danger")
            return redirect(url_for("admin.broadcast"))

        try:
            users_to_message = []
            if target_group == "all":
                users_to_message = db.session.query(User).filter_by(is_banned=False).all()
            # Add other target groups logic here later

            if not users_to_message:
                flash("لم يتم العثور على مستخدمين لإرسال الرسالة إليهم.", "warning")
                return redirect(url_for("admin.broadcast"))

            # Record the broadcast message in the database (optional)
            # Assuming sender_id=0 or a specific admin ID for broadcasts
            # broadcast_msg = Message(message_text=message_text, is_broadcast=True, sender_id=current_user.id)
            # db.session.add(broadcast_msg)
            # db.session.commit()

            # Send messages in background threads to avoid blocking
            sent_count = 0
            failed_count = 0
            threads = []
            for user in users_to_message:
                # Create and start a new thread for each message
                thread = threading.Thread(target=send_telegram_message_async, args=(bot_token, user.telegram_user_id, message_text))
                threads.append(thread)
                thread.start()
                sent_count += 1 # Assuming thread starts successfully, actual success is logged inside thread

            # Optionally wait for threads to complete, but might still timeout request
            # for thread in threads:
            #     thread.join(timeout=5) # Wait max 5 seconds per thread

            flash(f"بدأ إرسال الرسالة الجماعية إلى {sent_count} مستخدم في الخلفية.", "success")

        except Exception as e:
            # db.session.rollback()
            flash(f"حدث خطأ أثناء بدء إرسال الرسالة الجماعية: {e}", "danger")

        return redirect(url_for("admin.broadcast"))

    # For GET request
    return render_template("admin/broadcast.html")

# ... (rest of the code) ...

