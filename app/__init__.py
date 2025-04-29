from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config
import os

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login' # Assuming auth blueprint for login routes
login.login_message = 'الرجاء تسجيل الدخول للوصول إلى هذه الصفحة.'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)

    # Register blueprints here
    from app.routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.routes.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Create database tables if they don't exist (useful for SQLite)
    # For PostgreSQL with migrations, this isn't strictly necessary after initial migration
    # with app.app_context():
    #     db.create_all()

    return app

# Import models here to make them known to Flask-Migrate
from app import models

