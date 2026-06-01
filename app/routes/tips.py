from datetime import datetime, timezone
from flask import Blueprint, request, redirect, url_for, session, flash, current_app, jsonify
from app import config

bp = Blueprint("tips", __name__)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def _validate_goals(value: str) -> tuple[int | None, str | None]:
    try:
        n = int(value)
    except (ValueError, TypeError):
        return None, "Tore müssen eine Ganzzahl sein"
    if n < 0:
        return None, "Tore dürfen nicht negativ sein"
    if n > config.MAX_GOALS:
        return None, f"Tore dürfen nicht größer als {config.MAX_GOALS} sein"
    return n, None


@bp.post("/tip/<match_id>")
@login_required
def save_tip(match_id: str):
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    audit = current_app.audit
    user = session["username"]

    match = match_repo.find(match_id)
    if not match:
        flash("Spiel nicht gefunden.", "error")
        return redirect(url_for("main.dashboard"))

    if match_repo.is_matchday_locked(match["matchday"]):
        flash("Tippfrist abgelaufen – dieser Spieltag kann nicht mehr getippt werden.", "error")
        return redirect(url_for("main.matchday", matchday=match["matchday"]))

    home_raw = request.form.get("home_goals", "")
    away_raw = request.form.get("away_goals", "")
    is_risk_str = request.form.get("is_risk", "0")
    is_risk = is_risk_str in ("1", "on", "true", "yes")

    home, err = _validate_goals(home_raw)
    if err:
        flash(f"Heimtore: {err}", "error")
        return redirect(url_for("main.matchday", matchday=match["matchday"]))

    away, err = _validate_goals(away_raw)
    if err:
        flash(f"Auswärtstore: {err}", "error")
        return redirect(url_for("main.matchday", matchday=match["matchday"]))

    matchday = match["matchday"]

    # Handle risk pick exclusivity: unset old risk pick for this matchday if needed
    if is_risk:
        old_risk = tip_repo.get_user_risk_pick_for_matchday(user, matchday, match_repo)
        if old_risk and old_risk != match_id:
            old_tip = tip_repo.get_user_tip(user, old_risk)
            old_match = match_repo.find(old_risk)
            if old_tip and old_match and not match_repo.is_matchday_locked(old_match["matchday"]):
                tip_repo.save_tip(user, old_risk, old_tip["home_goals_tip"], old_tip["away_goals_tip"], False)
                audit.risk_changed(user, old_risk, False)

    tip_repo.save_tip(user, match_id, home, away, is_risk)
    audit.tip_saved(user, match_id, home, away, is_risk)

    flash(f"Tipp gespeichert: {home}:{away}" + (" (Hochrisikospiel)" if is_risk else ""), "success")
    return redirect(url_for("main.matchday", matchday=matchday))


@bp.post("/tips/bulk/<int:matchday>")
@login_required
def save_bulk_tips(matchday: int):
    """Save all tips for a matchday at once."""
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    audit = current_app.audit
    user = session["username"]

    matches = match_repo.by_matchday(matchday)
    if not matches:
        flash("Spieltag nicht gefunden.", "error")
        return redirect(url_for("main.dashboard"))

    saved = 0
    errors = []
    for m in matches:
        if match_repo.is_locked(m):
            continue
        home_raw = request.form.get(f"home_goals_{m['match_id']}", "")
        away_raw = request.form.get(f"away_goals_{m['match_id']}", "")
        if not home_raw and not away_raw:
            continue

        home, err = _validate_goals(home_raw)
        if err:
            errors.append(f"{m['match_id']}: Heimtore {err}")
            continue
        away, err = _validate_goals(away_raw)
        if err:
            errors.append(f"{m['match_id']}: Auswärtstore {err}")
            continue

        existing = tip_repo.get_user_tip(user, m["match_id"])
        is_risk = existing["is_risk_pick"] if existing else False
        tip_repo.save_tip(user, m["match_id"], home, away, is_risk)
        audit.tip_saved(user, m["match_id"], home, away, is_risk)
        saved += 1

    if errors:
        for e in errors:
            flash(e, "error")
    if saved:
        flash(f"{saved} Tipp(s) gespeichert.", "success")
    return redirect(url_for("main.matchday", matchday=matchday, saved="yes"))


@bp.post("/risk/<match_id>/toggle")
@login_required
def toggle_risk(match_id: str):
    """Toggle risk pick for a match (HTMX or form submit)."""
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    audit = current_app.audit
    user = session["username"]

    match = match_repo.find(match_id)
    if not match or match_repo.is_matchday_locked(match["matchday"]):
        flash("Hochrisikospiel kann nicht mehr geändert werden.", "error")
        return redirect(url_for("main.matchday", matchday=match["matchday"] if match else 1))

    tip = tip_repo.get_user_tip(user, match_id)
    if not tip:
        flash("Bitte erst einen Tipp abgeben.", "error")
        return redirect(url_for("main.matchday", matchday=match["matchday"]))

    matchday = match["matchday"]
    currently_risk = tip["is_risk_pick"]

    if not currently_risk:
        # Activating risk: unset existing risk pick for matchday
        old_risk = tip_repo.get_user_risk_pick_for_matchday(user, matchday, match_repo)
        if old_risk and old_risk != match_id:
            old_tip = tip_repo.get_user_tip(user, old_risk)
            old_match = match_repo.find(old_risk)
            if old_tip and old_match and not match_repo.is_matchday_locked(old_match["matchday"]):
                tip_repo.save_tip(user, old_risk, old_tip["home_goals_tip"], old_tip["away_goals_tip"], False)
                audit.risk_changed(user, old_risk, False)

    new_risk = not currently_risk
    tip_repo.save_tip(user, match_id, tip["home_goals_tip"], tip["away_goals_tip"], new_risk)
    audit.risk_changed(user, match_id, new_risk)

    status = "aktiviert" if new_risk else "deaktiviert"
    flash(f"Hochrisikospiel {status}.", "success")
    extra = {"saved": "risk"} if new_risk else {}
    return redirect(url_for("main.matchday", matchday=matchday, **extra))
