# This script is dedicated to running the Telegram bot independently.

import os
import logging
# import subprocess # No longer needed for migrations
from bot import run_bot
from app import create_app, db # Import db
from flask_migrate import upgrade # <<< Import upgrade function

# Enable logging (optional but recommended for worker process)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

logger.info("Starting Telegram bot worker process...")

# Create the Flask app instance to provide context if needed by the bot
# and to run migrations
app = create_app()

# --- Run Database Migrations Programmatically ---
try:
    with app.app_context():
        logger.info("Applying database migrations for worker...")
        upgrade() # <<< Run migrations using the imported function
        logger.info("Database migrations completed successfully for worker.")
except Exception as e:
    logger.error(f"Error applying database migrations for worker: {e}", exc_info=True)
    # Decide if you want the bot to continue running even if migrations fail
    # For now, we log the error and continue

# --- Start the Bot ---
# Check if essential bot environment variables are set
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
CHANNEL_USERNAME = os.environ.get("REQUIRED_CHANNEL_USERNAME")

if not BOT_TOKEN:
    logger.error("CRITICAL: TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot start.")
else:
    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL_ID not set. Subscription check will be skipped.")
    if not CHANNEL_USERNAME:
        logger.warning("REQUIRED_CHANNEL_USERNAME not set. Channel link might be missing in messages.")
    
    # Run the bot function, passing the app context
    # The run_bot function should contain the bot's main loop (e.g., application.run_polling())
    try:
        # Ensure the bot runs within the app context if it needs db access
        with app.app_context(): 
            run_bot(app) # Pass app if run_bot needs it, otherwise remove
    except Exception as e:
        logger.critical(f"An error occurred while running the bot: {e}", exc_info=True)

