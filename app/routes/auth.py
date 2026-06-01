from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.auth.service import authenticate, check_rate_limit, record_failed_attempt
from app import config

bp = Blueprint("auth", __name__)


def _ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        ip = _ip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not check_rate_limit(ip, config.LOGIN_MAX_ATTEMPTS, config.LOGIN_LOCKOUT_MINUTES):
            flash("Zu viele fehlgeschlagene Versuche. Bitte warte ein paar Minuten.", "error")
            return render_template("login.html")

        user = authenticate(current_app.user_repo, username, password)
        if user:
            session.permanent = True
            session["username"] = user["username"]
            session["display_name"] = user["display_name"]
            session["role"] = user["role"]
            current_app.audit.login_ok(user["username"], ip)
            return redirect(url_for("main.dashboard"))
        else:
            record_failed_attempt(ip)
            current_app.audit.login_fail(username, ip)
            flash("Ungültige Anmeldedaten.", "error")

    return render_template("login.html")


@bp.post("/logout")
def logout():
    ip = _ip()
    username = session.get("username", "?")
    current_app.audit.logout(username, ip)
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/")
def index():
    if "username" in session:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))
