from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login

class User(UserMixin, db.Model):
    __tablename__ = 'users' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True) # Use BigInteger for large IDs
    first_name = db.Column(db.String(64), nullable=True)
    last_name = db.Column(db.String(64), nullable=True)
    username = db.Column(db.String(64), nullable=True, index=True)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_active_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_subscribed = db.Column(db.Boolean, default=False, nullable=False) # <<< أضف هذا السطر
    is_banned = db.Column(db.Boolean, default=False, nullable=False)     # <<< أضف هذا السطر (لمنع من ألغوا الاشتراك)
    downloads = db.relationship('Download', backref='user', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username or self.telegram_user_id}>'

class Admin(UserMixin, db.Model):
    __tablename__ = 'admins' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(256)) # Increased length for potentially stronger hashes
    role = db.Column(db.String(64), default='admin') # Example role field
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Admin {self.username}>'

@login.user_loader
def load_user(id):
    # Check both User and Admin tables
    user = User.query.get(int(id))
    if user:
        return user
    return Admin.query.get(int(id))

# --- Models for Bot Functionality ---

class Download(db.Model):
    __tablename__ = 'downloads'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    download_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(64), default='success') # e.g., success, failed, pending
    error_message = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Download {self.id} by User {self.user_id}>'

class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Setting {self.key}>'

