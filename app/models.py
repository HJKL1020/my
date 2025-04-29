from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login

# User loader function for Flask-Login
@login.user_loader
def load_user(id):
    return db.session.get(Admin, int(id))

class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(64), default='admin')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    announcements = db.relationship('Announcement', backref='author', lazy='dynamic')
    forbidden_content_reviews = db.relationship('ForbiddenContent', backref='reviewer', lazy='dynamic', foreign_keys='ForbiddenContent.reviewed_by_admin_id')
    settings_updates = db.relationship('Setting', backref='updater', lazy='dynamic')
    logs = db.relationship('Log', backref='admin', lazy='dynamic')
    music_uploads = db.relationship('Music', backref='uploader', lazy='dynamic')
    warnings_issued = db.relationship('Warning', backref='issuer', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Admin {self.username}>'

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, index=True, unique=True, nullable=False)
    first_name = db.Column(db.String(128))
    last_name = db.Column(db.String(128))
    username = db.Column(db.String(128), index=True, unique=True)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text)
    ban_expires_at = db.Column(db.DateTime)
    warning_count = db.Column(db.Integer, default=0)
    last_warning_at = db.Column(db.DateTime)
    joined_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    last_active_at = db.Column(db.DateTime, index=True)

    downloads = db.relationship('Download', backref='user', lazy='dynamic')
    messages_sent = db.relationship('Message', backref='sender', lazy='dynamic', foreign_keys='Message.sender_id')
    messages_received = db.relationship('Message', backref='recipient', lazy='dynamic', foreign_keys='Message.recipient_id')
    reports_made = db.relationship('ForbiddenContent', backref='reporter', lazy='dynamic', foreign_keys='ForbiddenContent.reported_by_user_id')
    warnings_received = db.relationship('Warning', backref='user', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username or self.telegram_user_id}>'

class Download(db.Model):
    __tablename__ = 'downloads'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content_type = db.Column(db.String(64))
    content_url = db.Column(db.Text)
    downloaded_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(64), default='success')
    error_message = db.Column(db.Text)

    def __repr__(self):
        return f'<Download {self.id} by User {self.user_id}>'

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id')) # Null for broadcast
    message_text = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    is_broadcast = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Message {self.id} from User {self.sender_id}>'

class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=False)
    announcement_text = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Announcement {self.id}>'

class ForbiddenContent(db.Model):
    __tablename__ = 'forbidden_content'
    id = db.Column(db.Integer, primary_key=True)
    reported_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'))
    content_url = db.Column(db.Text, unique=True, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(64), default='reported') # reported, reviewed, action_taken
    action_taken = db.Column(db.String(128)) # user_warned, user_banned, content_ignored
    reported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<ForbiddenContent {self.content_url}>'

class Setting(db.Model):
    __tablename__ = 'settings'
    key = db.Column(db.String(128), primary_key=True, unique=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    last_updated_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'))
    last_updated_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Setting {self.key}>'

class Log(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id')) # Null for system actions
    action_type = db.Column(db.String(128), nullable=False)
    details = db.Column(db.Text)
    target_type = db.Column(db.String(64))
    target_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    ip_address = db.Column(db.String(64))

    def __repr__(self):
        return f'<Log {self.id} - {self.action_type}>'

class Music(db.Model):
    __tablename__ = 'music'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    artist = db.Column(db.String(256))
    file_path = db.Column(db.Text, nullable=False)
    source_url = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    uploaded_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'))
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Music {self.title}>'

class Warning(db.Model):
    __tablename__ = 'warnings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id')) # Null for auto-warnings
    reason = db.Column(db.Text, nullable=False)
    warning_level = db.Column(db.Integer, default=1)
    issued_at = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Warning {self.id} for User {self.user_id}>'

class Theme(db.Model):
    __tablename__ = 'themes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    css_variables = db.Column(db.Text) # Store as JSON string
    is_active = db.Column(db.Boolean, default=False) # Only one theme active via Settings table
    icon_url = db.Column(db.Text)

    def __repr__(self):
        return f'<Theme {self.name}>'

