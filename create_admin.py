#!/usr/bin/env python
import os
import sys
from app import create_app, db
from app.models import Admin

app = create_app()

# Define the admin credentials from user input
ADMIN_USERNAME = "HJKL966"
ADMIN_PASSWORD = "Aa442240280@"

def create_admin_user():
    with app.app_context():
        # Check if admin user already exists
        existing_admin = Admin.query.filter_by(username=ADMIN_USERNAME).first()
        if existing_admin:
            print(f"Admin user 	'{ADMIN_USERNAME}	' already exists. Updating password.")
            existing_admin.set_password(ADMIN_PASSWORD)
            db.session.add(existing_admin)
            print("Password updated.")
        else:
            print(f"Creating admin user 	'{ADMIN_USERNAME}	'...")
            admin = Admin(username=ADMIN_USERNAME)
            admin.set_password(ADMIN_PASSWORD)
            db.session.add(admin)
            print("Admin user created.")
        
        try:
            db.session.commit()
            print("Database changes committed successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"Error committing changes to database: {e}")
            sys.exit(1)

if __name__ == "__main__":
    print("Running admin user creation script...")
    create_admin_user()
    print("Admin user creation script finished.")

