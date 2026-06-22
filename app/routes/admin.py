import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, current_app)
from app.admin.importer import parse_csv_upload, backup_results, validate_match_ids

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Pending imports stored in memory (sufficient for small institute)
_pending_imports: dict[str, dict] = {}


def _recompute_all():
    """Regenerate every derived artifact after points may have changed:
    the per-user result txt files and the materialized highscore cache."""
    current_app.player_results_writer.generate_all(
        current_app.user_repo, current_app.match_repo, current_app.tip_repo,
        current_app.result_repo, current_app.snapshot_repo, current_app.adj_repo,
    )
    current_app.leaderboard_cache.regenerate()


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("auth.login"))
        if session.get("role") != "admin":
            flash("Keine Berechtigung.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)
    return decorated


@bp.route("/")
@admin_required
def index():
    from app.admin.team_resolver import get_resolution_preview
    from app.routes.main import _WC_TEAM_FLAGS
    match_repo = current_app.match_repo
    result_repo = current_app.result_repo
    user_repo = current_app.user_repo
    matchdays = match_repo.matchdays()
    results = {r["match_id"]: r for r in result_repo.all()}
    users = user_repo.all()

    # Categorize matches into locked / final / open for the three status cards.
    locked_games, final_games, open_games = [], [], []
    for m in match_repo.all():
        r = results.get(m["match_id"])
        if r and r["status"] == "final":
            final_games.append({"m": m, "r": r, "game_status": "final"})
        elif r and r["status"] == "locked":
            locked_games.append({"m": m, "r": r, "game_status": "admin-locked"})
        elif match_repo.is_locked(m):
            locked_games.append({"m": m, "r": r, "game_status": "auto-locked"})
        else:
            open_games.append({"m": m, "r": r, "game_status": "open"})
    team_resolution_preview = get_resolution_preview(match_repo, result_repo)
    wc_picks_all = current_app.wc_pick_repo.all()
    wc_team_flags = _WC_TEAM_FLAGS
    wc_pick_locked = current_app.wc_pick_repo.is_pick_locked()
    return render_template("admin/index.html",
        matchdays=matchdays,
        match_repo=match_repo,
        results=results,
        locked_games=locked_games,
        final_games=final_games,
        open_games=open_games,
        users=users,
        team_resolution_preview=team_resolution_preview,
        wc_picks_all=wc_picks_all,
        wc_team_flags=wc_team_flags,
        wc_pick_locked=wc_pick_locked,
    )


@bp.post("/wc-pick-lock")
@admin_required
def wc_pick_lock():
    action = request.form.get("action")
    lock = action == "lock"
    current_app.wc_pick_repo.set_pick_locked(lock)
    flash("WM-Sieger-Tipp gesperrt." if lock else "WM-Sieger-Tipp entsperrt.", "success")
    return redirect(url_for("admin.index"))


@bp.post("/upload")
@admin_required
def upload():
    user = session["username"]
    audit = current_app.audit

    if "results_file" not in request.files:
        flash("Keine Datei ausgewählt.", "error")
        return redirect(url_for("admin.index"))

    f = request.files["results_file"]
    if not f.filename:
        flash("Keine Datei ausgewählt.", "error")
        return redirect(url_for("admin.index"))

    filename = f.filename.lower()
    if not (filename.endswith(".csv") or filename.endswith(".txt")):
        flash("Nur .csv oder .txt Dateien erlaubt.", "error")
        audit.import_failed(user, "wrong_file_type")
        return redirect(url_for("admin.index"))

    content = f.read()
    if len(content) > current_app.config.get("MAX_CONTENT_LENGTH", 1024 * 1024):
        flash("Datei zu groß (max. 1 MB).", "error")
        audit.import_failed(user, "file_too_large")
        return redirect(url_for("admin.index"))

    audit.result_upload(user, f.filename)

    rows, errors = parse_csv_upload(content)

    if errors:
        flash(f"Fehler in der Datei ({len(errors)} Fehler gefunden).", "error")
        return render_template("admin/preview.html",
            rows=rows, errors=errors, import_id=None,
            matchdays=current_app.match_repo.matchdays(),
        )

    # Validate match IDs
    id_errors = validate_match_ids(rows, current_app.match_repo)
    if id_errors:
        errors.extend(id_errors)
        flash(f"Unbekannte Spiel-IDs gefunden.", "error")
        return render_template("admin/preview.html",
            rows=rows, errors=errors, import_id=None,
            matchdays=current_app.match_repo.matchdays(),
        )

    import_id = uuid.uuid4().hex
    _pending_imports[import_id] = {
        "rows": rows,
        "uploaded_by": user,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "filename": f.filename,
    }

    return render_template("admin/preview.html",
        rows=rows, errors=[], import_id=import_id,
        matchdays=current_app.match_repo.matchdays(),
        match_repo=current_app.match_repo,
    )


@bp.post("/import/<import_id>/confirm")
@admin_required
def confirm_import(import_id: str):
    user = session["username"]
    audit = current_app.audit

    pending = _pending_imports.pop(import_id, None)
    if not pending:
        flash("Import-Session abgelaufen oder ungültig.", "error")
        return redirect(url_for("admin.index"))

    # Backup current results
    data_dir = current_app.config["DATA_DIR"]
    backup_results(data_dir)

    result_repo = current_app.result_repo
    result_repo.import_results(pending["rows"])

    _recompute_all()

    count = len(pending["rows"])
    audit.result_import(user, count)
    flash(f"{count} Ergebnisse erfolgreich importiert.", "success")
    return redirect(url_for("admin.index"))


@bp.get("/import/<import_id>/cancel")
@admin_required
def cancel_import(import_id: str):
    _pending_imports.pop(import_id, None)
    flash("Import abgebrochen.", "info")
    return redirect(url_for("admin.index"))


@bp.post("/users/<username>/payment")
@admin_required
def toggle_payment(username: str):
    user_repo = current_app.user_repo
    user = user_repo.find_by_username(username)
    if not user:
        flash(f"Nutzer '{username}' nicht gefunden.", "error")
        return redirect(url_for("admin.index"))
    new_paid = not user.get("paid", False)
    user_repo.save({**user, "paid": new_paid})
    current_app.audit.admin_action(
        session["username"],
        f"payment_set target={username} paid={1 if new_paid else 0}",
    )
    status = "bezahlt" if new_paid else "nicht bezahlt"
    flash(f"'{username}' als {status} markiert.", "success")
    return redirect(url_for("admin.index"))


@bp.post("/restart")
@admin_required
def restart_server():
    import threading, os, sys, subprocess
    flash("Server wird neu gestartet...", "info")
    def _restart():
        import time
        time.sleep(0.8)
        subprocess.Popen([sys.executable] + sys.argv)
        os._exit(0)
    threading.Thread(target=_restart, daemon=True).start()
    return redirect(url_for("admin.index"))


@bp.post("/match/<match_id>/score")
@admin_required
def set_match_score(match_id: str):
    result_repo = current_app.result_repo
    match_repo = current_app.match_repo

    match = match_repo.find(match_id)
    if not match:
        flash(f"Spiel '{match_id}' nicht gefunden.", "error")
        return redirect(url_for("admin.index"))

    status = request.form.get("status", "scheduled")
    if status not in ("scheduled", "final"):
        flash("Ungültiger Status.", "error")
        return redirect(url_for("admin.index"))

    home_goals_str = request.form.get("home_goals", "").strip()
    away_goals_str = request.form.get("away_goals", "").strip()
    home_goals = None
    away_goals = None

    if status == "final":
        try:
            home_goals = int(home_goals_str)
            away_goals = int(away_goals_str)
            if home_goals < 0 or away_goals < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Tore müssen ganze Zahlen >= 0 sein.", "error")
            return redirect(url_for("admin.index"))

    result_repo.upsert({
        "match_id": match_id,
        "home_goals_actual": home_goals,
        "away_goals_actual": away_goals,
        "status": status,
    })

    _recompute_all()

    current_app.audit.admin_action(
        session["username"],
        f"score_set match={match_id} {home_goals}:{away_goals} status={status}",
    )
    flash(f"Ergebnis für {match_id} gesetzt: {home_goals}:{away_goals} ({status}).", "success")
    return redirect(url_for("admin.index"))


@bp.post("/teams/save-all")
@admin_required
def save_all_team_names():
    from collections import defaultdict
    match_repo = current_app.match_repo
    all_matches = match_repo.all()
    GROUP_MATCHDAYS = {1, 2, 3}

    # Build proposed map — last submitted value wins (team-resolution inputs appear after aktuelle-spiele)
    proposed = {}
    for match in all_matches:
        mid = match["match_id"]
        h_values = request.form.getlist(f"home_{mid}")
        a_values = request.form.getlist(f"away_{mid}")
        h = h_values[-1].strip() if h_values else ""
        a = a_values[-1].strip() if a_values else ""
        proposed[mid] = {
            "home": h if h else match["home_team"],
            "away": a if a else match["away_team"],
        }

    # Reject empty names
    errors = []
    for match in all_matches:
        mid = match["match_id"]
        if not proposed[mid]["home"] or not proposed[mid]["away"]:
            errors.append(f"{mid}: Teamname darf nicht leer sein.")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin.index"))

    # Group stage: each old team name must map to exactly one new name across all occurrences
    group_matches = [m for m in all_matches if m["matchday"] in GROUP_MATCHDAYS]
    name_positions = defaultdict(list)
    for m in group_matches:
        name_positions[m["home_team"]].append((m["match_id"], "home"))
        name_positions[m["away_team"]].append((m["match_id"], "away"))

    for old_name, positions in name_positions.items():
        if len(positions) <= 1:
            continue
        new_names = {proposed[mid][side] for mid, side in positions}
        if len(new_names) > 1:
            affected = ", ".join(mid for mid, _ in positions)
            errors.append(
                f"'{old_name}' kommt in {len(positions)} Gruppenspielen vor ({affected}) — "
                f"alle müssen denselben neuen Namen bekommen."
            )

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin.index"))

    # Apply
    count = 0
    for match in all_matches:
        mid = match["match_id"]
        new_h, new_a = proposed[mid]["home"], proposed[mid]["away"]
        if new_h != match["home_team"] or new_a != match["away_team"]:
            match_repo.update_team_names(
                mid,
                new_h if new_h != match["home_team"] else None,
                new_a if new_a != match["away_team"] else None,
            )
            count += 1

    current_app.audit.admin_action(session["username"], f"team_names_saved count={count}")
    flash(f"{count} Spiel{'e' if count != 1 else ''} aktualisiert." if count else "Keine Änderungen.",
          "success" if count else "info")
    return redirect(url_for("admin.index"))


@bp.post("/resolve-teams")
@admin_required
def resolve_teams():
    from app.admin.team_resolver import get_resolution_preview, apply_resolutions
    match_repo = current_app.match_repo
    result_repo = current_app.result_repo
    preview = get_resolution_preview(match_repo, result_repo)
    count = apply_resolutions(preview, match_repo)
    current_app.audit.admin_action(
        session["username"],
        f"teams_resolved count={count}",
    )
    if count:
        flash(f"{count} Spiel{'e' if count != 1 else ''} aufgelöst.", "success")
    else:
        flash("Keine auflösbaren Platzhalter gefunden.", "info")
    return redirect(url_for("admin.index"))


@bp.post("/recalculate")
@admin_required
def recalculate():
    _recompute_all()
    flash("Punkte neu berechnet.", "success")
    return redirect(url_for("admin.index"))


@bp.post("/users/<username>/adjust")
@admin_required
def adjust_user_points(username: str):
    user_repo = current_app.user_repo
    adj_repo = current_app.adj_repo

    user = user_repo.find_by_username(username)
    if not user:
        flash(f"Nutzer '{username}' nicht gefunden.", "error")
        return redirect(url_for("admin.index"))

    delta_str = request.form.get("delta", "").strip()
    note = request.form.get("note", "").strip()

    try:
        delta = float(delta_str)
    except (ValueError, TypeError):
        flash("Delta muss eine Zahl sein (z.B. 2.0 oder -1.5).", "error")
        return redirect(url_for("admin.index"))

    adj_repo.add(username, delta, note)
    _recompute_all()
    current_app.audit.admin_action(
        session["username"],
        f"points_adjusted target={username} delta={delta} note={note}",
    )
    flash(f"Punkte für '{username}' angepasst: {delta:+.1f}.", "success")
    return redirect(url_for("admin.index"))


@bp.post("/world-cup-award")
@admin_required
def award_world_cup_points():
    from app.routes.main import _WC_TEAM_FLAGS
    first = request.form.get("first_place", "").strip()
    second = request.form.get("second_place", "").strip()
    third = request.form.get("third_place", "").strip()

    valid_teams = set(_WC_TEAM_FLAGS.keys())
    errors = []
    if first and first not in valid_teams:
        errors.append(f"Unbekanntes Team für 1. Platz: {first!r}")
    if second and second not in valid_teams:
        errors.append(f"Unbekanntes Team für 2. Platz: {second!r}")
    if third and third not in valid_teams:
        errors.append(f"Unbekanntes Team für 3. Platz: {third!r}")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin.index"))

    picks = current_app.wc_pick_repo.all()
    adj_repo = current_app.adj_repo
    awarded = 0
    for pick in picks:
        username = pick["username"]
        team = pick["team"]
        if first and team == first:
            adj_repo.add(username, 40, f"WM-Sieger-Tipp: {team} – 1. Platz")
            awarded += 1
        elif second and team == second:
            adj_repo.add(username, 25, f"WM-Sieger-Tipp: {team} – 2. Platz")
            awarded += 1
        elif third and team == third:
            adj_repo.add(username, 15, f"WM-Sieger-Tipp: {team} – 3. Platz")
            awarded += 1

    _recompute_all()
    current_app.audit.admin_action(
        session["username"],
        f"wc_points_awarded first={first} second={second} third={third} count={awarded}",
    )
    flash(f"WM-Sieger-Punkte vergeben: {awarded} Nutzer belohnt.", "success")
    return redirect(url_for("admin.index"))


@bp.post("/users/bulk")
@admin_required
def bulk_create_users():
    import re
    from app.auth.hashing import hash_password

    raw = request.form.get("bulk_users", "")
    user_repo = current_app.user_repo

    created = []
    errors = []

    for i, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in line.split(",", 2)]
        if len(parts) < 2:
            errors.append(f"Zeile {i}: Format muss 'username, passwort' sein")
            continue

        username, password = parts[0], parts[1]
        display_name = parts[2] if len(parts) > 2 else username

        if not re.fullmatch(r"[A-Za-z0-9_\-]{3,32}", username):
            errors.append(f"Zeile {i} ({username!r}): Ungültiger Benutzername")
            continue
        if len(password) < 8:
            errors.append(f"Zeile {i} ({username}): Passwort zu kurz (min. 8 Zeichen)")
            continue
        if ";" in display_name:
            errors.append(f"Zeile {i} ({username}): Anzeigename darf kein Semikolon enthalten")
            continue
        if len(display_name) > 50:
            errors.append(f"Zeile {i} ({username}): Anzeigename zu lang (max. 50 Zeichen)")
            continue
        if user_repo.find_by_username(username) is not None:
            errors.append(f"Zeile {i}: '{username}' existiert bereits")
            continue

        user_repo.save({
            "username": username,
            "password_hash": hash_password(password),
            "role": "user",
            "display_name": display_name,
            "active": True,
            "paid": False,
        })
        created.append(username)

    if created:
        current_app.audit.admin_action(
            session["username"],
            f"bulk_users_created count={len(created)} users={','.join(created)}",
        )
        flash(f"{len(created)} Nutzer angelegt: {', '.join(created)}", "success")
    for e in errors:
        flash(e, "error")
    if not created and not errors:
        flash("Keine Nutzer eingegeben.", "info")

    return redirect(url_for("admin.index"))


@bp.post("/users/<username>/delete")
@admin_required
def delete_user(username: str):
    if username == session["username"]:
        flash("Du kannst deinen eigenen Account nicht löschen.", "error")
        return redirect(url_for("admin.index"))
    user_repo = current_app.user_repo
    deleted = user_repo.delete(username)
    if not deleted:
        flash(f"Nutzer '{username}' nicht gefunden.", "error")
    else:
        current_app.audit.admin_action(
            session["username"],
            f"user_deleted target={username}",
        )
        flash(f"Nutzer '{username}' gelöscht.", "success")
    return redirect(url_for("admin.index"))


@bp.post("/users/<username>/password")
@admin_required
def change_user_password(username: str):
    from app.auth.hashing import hash_password
    user_repo = current_app.user_repo
    user = user_repo.find_by_username(username)
    if not user:
        flash(f"Nutzer '{username}' nicht gefunden.", "error")
        return redirect(url_for("admin.index"))
    password = request.form.get("password", "")
    if len(password) < 8:
        flash("Passwort muss mindestens 8 Zeichen haben.", "error")
        return redirect(url_for("admin.index"))
    user_repo.save({**user, "password_hash": hash_password(password)})
    current_app.audit.admin_action(
        session["username"],
        f"password_changed target={username}",
    )
    flash(f"Passwort für '{username}' geändert.", "success")
    return redirect(url_for("admin.index"))


@bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def create_user():
    import re
    from app.auth.hashing import hash_password

    if request.method == "GET":
        return render_template("admin/create_user.html")

    username = request.form.get("username", "").strip()
    display_name = request.form.get("display_name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")
    active = request.form.get("active", "1") == "1"

    errors = []

    if not username:
        errors.append("Benutzername darf nicht leer sein.")
    elif not re.fullmatch(r"[A-Za-z0-9_\-]{3,32}", username):
        errors.append("Benutzername: 3–32 Zeichen, nur Buchstaben, Ziffern, _ oder -")

    if role not in ("user", "admin"):
        errors.append("Ungültige Rolle.")

    if len(password) < 8:
        errors.append("Passwort muss mindestens 8 Zeichen haben.")

    if display_name and len(display_name) > 50:
        errors.append("Anzeigename zu lang (max. 50 Zeichen).")
    if display_name and ";" in display_name:
        errors.append("Anzeigename darf kein Semikolon enthalten.")

    if not errors:
        user_repo = current_app.user_repo
        if user_repo.find_by_username(username) is not None:
            errors.append(f"Benutzername '{username}' ist bereits vergeben.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("admin/create_user.html",
            username=username, display_name=display_name,
            role=role, active=active)

    user_repo = current_app.user_repo
    user_repo.save({
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "display_name": display_name or username,
        "active": active,
    })

    current_app.audit.admin_action(
        session["username"],
        f"user_created target={username} role={role}",
    )
    flash(f"Nutzer '{username}' erfolgreich angelegt.", "success")
    return redirect(url_for("admin.index"))
