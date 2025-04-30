# Placeholder for main routes
from flask import Blueprint, render_template, jsonify, current_app
from app import db
from app.models import User, Download, Setting
import datetime
import time

bp = Blueprint("main", __name__)

# Store app start time globally (simple approach)
# A more robust approach might involve storing/retrieving from DB or a file
app_start_time = time.time()

# Function to get stats from database
def get_stats_from_db():
    stats = {
        "visitors": 0,  # Visitor count needs a better mechanism (e.g., Redis, dedicated table, or analytics service)
                      # Using a placeholder or simple DB setting for now.
        "bot_users": 0,
        "bot_downloads": 0
    }
    try:
        # Example: Get visitor count from settings (assuming a key 'visitor_count' exists)
        # CORRECTED: Use filter_by for non-primary key lookup
        visitor_setting = db.session.query(Setting).filter_by(key="visitor_count").first()
        if visitor_setting:
            current_count = int(visitor_setting.value)
            # Increment visitor count - NOTE: This is basic and not thread-safe for high traffic
            # A proper solution is needed for production.
            current_count += 1
            visitor_setting.value = str(current_count)
            stats["visitors"] = current_count
            # db.session.commit() # Commit frequently might impact performance, consider batching or background task
        else:
            # Initialize setting if not found
            # CORRECTED: REMOVED description argument
            new_visitor_setting = Setting(key="visitor_count", value="1")
            db.session.add(new_visitor_setting)
            stats["visitors"] = 1
            # db.session.commit()

        # Get bot users count
        stats["bot_users"] = db.session.query(User).count()

        # Get bot downloads count
        stats["bot_downloads"] = db.session.query(Download).count()

        # Commit any changes made (like visitor count increment)
        db.session.commit()
    except Exception as e:
        db.session.rollback() # Rollback in case of error
        current_app.logger.error(f"Error getting stats from DB: {e}")
        # Return defaults or indicate error
        stats["visitors"] = "N/A"
        stats["bot_users"] = "N/A"
        stats["bot_downloads"] = "N/A"
    return stats

# Function to get warning message from database
def get_warning_message_from_db():
    default_warning = {
        "text": "يمنع استخدام البوت لتحميل محتوى غير اخلاقي ويتم حظر اي شخص",
        "color": "red"
    }
    try:
        # CORRECTED: Use filter_by for non-primary key lookup
        warning_text_setting = db.session.query(Setting).filter_by(key="warning_message_text").first()
        warning_color_setting = db.session.query(Setting).filter_by(key="warning_message_color").first()

        text = warning_text_setting.value if warning_text_setting else default_warning["text"]
        color = warning_color_setting.value if warning_color_setting else default_warning["color"]
        return {"text": text, "color": color}
    except Exception as e:
        current_app.logger.error(f"Error getting warning message from DB: {e}")
        return default_warning

@bp.route("/")
def index():
    # Render the main frontend page
    return render_template("index.html")

@bp.route("/api/stats")
def api_stats():
    # Use the new functions that query the database
    stats = get_stats_from_db()
    warning = get_warning_message_from_db()
    # Use the globally stored start time
    start_timestamp = app_start_time
    return jsonify({
        "visitors": stats["visitors"],
        "bot_users": stats["bot_users"],
        "bot_downloads": stats["bot_downloads"],
        "warning_message": warning["text"],
        "warning_color": warning["color"],
        "server_start_timestamp": start_timestamp
    })

