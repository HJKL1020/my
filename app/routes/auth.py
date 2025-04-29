# Placeholder for authentication routes
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app.models import Admin
from app import db

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard")) # Redirect to admin dashboard if already logged in

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        admin = Admin.query.filter_by(username=username).first()

        if admin and admin.check_password(password):
            login_user(admin) # Log in the admin user
            flash("تم تسجيل الدخول بنجاح!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("admin.dashboard"))
        else:
            flash("اسم المستخدم أو كلمة المرور غير صحيحة.", "danger")

    # For GET request or failed login, render the login template
    # We need to create login.html template later
    return render_template("auth/login.html")

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("تم تسجيل الخروج بنجاح.", "info")
    return redirect(url_for("main.index"))

