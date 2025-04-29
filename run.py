from app import create_app, db
from app.models import Admin, User # Add other models if needed for startup checks
import os

app = create_app()

# Function to create initial admin user if none exists
# NOTE: This might run every time a web worker starts. Consider moving to a migration script.
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

# Create initial admin user if needed (run once per worker start)
# This should ideally be handled differently in production (e.g., migrations)
create_initial_admin()

# The 'app' object is created above and is what Gunicorn needs (e.g., gunicorn run:app)
# No need for app.run() here for production deployment via Gunicorn.

