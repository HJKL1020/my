from app import create_app, db
from app.models import Admin, User # Add other models if needed for startup checks
import threading
import os

# Import the bot runner function
from bot import run_bot

app = create_app()

# Function to create initial admin user if none exists
def create_initial_admin():
    with app.app_context():
        if db.session.query(Admin).count() == 0:
            print("No admin user found. Creating initial admin...")
            admin_username = os.environ.get("ADMIN_USERNAME", "HJKL966") # Default or from env
            admin_password = os.environ.get("ADMIN_PASSWORD", "Aa442240180") # Default or from env
            if not admin_username or not admin_password:
                print("ADMIN_USERNAME or ADMIN_PASSWORD not set. Cannot create initial admin.")
                return
            
            admin = Admin(username=admin_username)
            admin.set_password(admin_password)
            db.session.add(admin)
            try:
                db.session.commit()
                print(f"Initial admin user \'{admin_username}\' created successfully.")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating initial admin user: {e}")
        else:
            print("Admin user(s) already exist.")

if __name__ == "__main__":
    # Create initial admin user if needed (run once)
    create_initial_admin()

    # Start the Telegram bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, args=(app,), daemon=True)
    bot_thread.start()

    # Run the Flask web server
    # Use host=\'0.0.0.0\' to make it accessible externally if needed
    # Use port specified by environment or default (e.g., 5000)
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False) # Turn off debug mode for production/threading

