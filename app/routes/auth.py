import re
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.auth.service import authenticate, check_rate_limit, record_failed_attempt
from app.auth.hashing import hash_password
from app import config

bp = Blueprint("auth", __name__)

_USERNAME_RE = re.compile(r"[A-Za-z0-9_\-]{3,32}")


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


@bp.route("/register", methods=["GET", "POST"])
def register():
    if "username" in session:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []

        if not username:
            errors.append("Benutzername darf nicht leer sein.")
        elif not _USERNAME_RE.fullmatch(username):
            errors.append("Benutzername: 3–32 Zeichen, nur Buchstaben, Ziffern, _ oder -")

        if display_name and len(display_name) > 50:
            errors.append("Anzeigename zu lang (max. 50 Zeichen).")
        if display_name and ";" in display_name:
            errors.append("Anzeigename darf kein Semikolon enthalten.")

        if len(password) < 8:
            errors.append("Passwort muss mindestens 8 Zeichen haben.")
        elif password != confirm_password:
            errors.append("Passwörter stimmen nicht überein.")

        if not errors and current_app.user_repo.find_by_username(username) is not None:
            errors.append(f"Benutzername '{username}' ist bereits vergeben.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", username=username, display_name=display_name)

        current_app.user_repo.save({
            "username": username,
            "password_hash": hash_password(password),
            "role": "user",
            "display_name": display_name or username,
            "active": True,
        })
        current_app.audit.admin_action(username, f"self_registered ip={_ip()}")
        flash("Konto erfolgreich erstellt. Du kannst dich jetzt anmelden.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


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
