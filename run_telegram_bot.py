# This script is dedicated to running the Telegram bot independently.

import os
import logging
import subprocess # <<< أضف هذا السطر
from bot import run_bot
from app import create_app

# Enable logging (optional but recommended for worker process)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

logger.info("Starting Telegram bot worker process...")

# --- Run Database Migrations ---
logger.info("Attempting to run database migrations for worker...")
try:
    # Use subprocess to run the flask db upgrade command
    result = subprocess.run(["flask", "db", "upgrade"], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        logger.info("Database migrations completed successfully for worker.")
        logger.info(f"Migration output:\n{result.stdout}")
    else:
        logger.error(f"Database migrations failed for worker. Return code: {result.returncode}")
        logger.error(f"Migration error output:\n{result.stderr}")
except FileNotFoundError:
    logger.error("Could not find 'flask' command. Make sure Flask is installed and in the PATH.")
except Exception as e:
    logger.error(f"An unexpected error occurred during database migration: {e}", exc_info=True)
# --- End Database Migrations ---


# Create the Flask app instance to provide context if needed by the bot
app = create_app()

# Check if essential bot environment variables are set
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
CHANNEL_USERNAME = os.environ.get("REQUIRED_CHANNEL_USERNAME")

if not BOT_TOKEN:
    logger.error("CRITICAL: TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot start.")
else:
    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL_ID not set. Subscription check might be skipped or fail if needed.")
    if not CHANNEL_USERNAME:
        logger.warning("REQUIRED_CHANNEL_USERNAME not set. Channel link might be missing in messages.")

    # Run the bot function, passing the app context
    try:
        # Ensure the bot runs within the app context if it needs db access
        with app.app_context():
            run_bot(app) # Pass app if run_bot needs it, otherwise remove
    except Exception as e:
        logger.critical(f"An error occurred while running the bot: {e}", exc_info=True)

