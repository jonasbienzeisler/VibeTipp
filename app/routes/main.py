from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, session, flash, request, current_app, jsonify
from app.scoring.engine import calculate_score, get_tendency, Tendency
from app import config as _cfg

bp = Blueprint("main", __name__)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def _build_leaderboard_data(username_filter=None, matchday_filter=None):
    """Build leaderboard entries for all (or filtered) users."""
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo

    users = [u for u in user_repo.all() if u["active"]]

    matches = match_repo.all() if not matchday_filter else match_repo.by_matchday(matchday_filter)
    results_by_id = {r["match_id"]: r for r in result_repo.all()}
    finished_matches = [
        m for m in matches
        if match_repo.is_locked(m) or results_by_id.get(m["match_id"], {}).get("status") == "final"
    ]

    # Pre-compute all score breakdowns to avoid double-fetching
    # score_cache[(username, match_id)] = (bd, tip)
    score_cache = {}
    for match in finished_matches:
        result = result_repo.find(match["match_id"])
        if not result or result["status"] != "final":
            continue
        snap = snapshot_repo.get_or_create(match["match_id"], match["kickoff_at"], tip_repo)
        for user in users:
            uname = user["username"]
            tip = tip_repo.get_user_tip(uname, match["match_id"])
            if not tip:
                continue
            bd = calculate_score(
                result["home_goals_actual"], result["away_goals_actual"],
                tip["home_goals_tip"], tip["away_goals_tip"],
                tip["is_risk_pick"], match["is_germany_game"], snap,
            )
            score_cache[(uname, match["match_id"])] = (bd, tip)

    # Per-game bonus: +1 to player(s) with correct tendency AND biggest tip goal diff
    # "Spieler mit richtiger Tendenz und größter Tordifferenz pro Spiel"
    bonus_counts = {u["username"]: 0 for u in users}
    for match in finished_matches:
        result = result_repo.find(match["match_id"])
        if not result or result["status"] != "final":
            continue
        candidates = []
        for user in users:
            uname = user["username"]
            entry = score_cache.get((uname, match["match_id"]))
            if not entry:
                continue
            bd, tip = entry
            if bd.tendency_correct:
                tip_gdiff = abs(tip["home_goals_tip"] - tip["away_goals_tip"])
                candidates.append((uname, tip_gdiff))
        if candidates:
            max_gdiff = max(c[1] for c in candidates)
            for uname, gdiff in candidates:
                if gdiff == max_gdiff:
                    bonus_counts[uname] += 1

    # Build entries
    entries = []
    for user in users:
        uname = user["username"]
        total_pts = 0.0
        exact_count = 0
        tendency_count = 0
        risk_ok = 0
        risk_fail = 0

        for match in finished_matches:
            entry = score_cache.get((uname, match["match_id"]))
            if not entry:
                continue
            bd, _ = entry
            total_pts += bd.final_pts
            if bd.tendency_correct:
                tendency_count += 1
            if bd.base_category == "exact":
                exact_count += 1
            if bd.risk_result == "double":
                risk_ok += 1
            elif bd.risk_result == "deduct":
                risk_fail += 1

        total_pts += current_app.adj_repo.get_user_delta(uname)
        bonus_pts = bonus_counts[uname]
        total_pts = round(total_pts + bonus_pts, 1)

        entries.append({
            "username": uname,
            "display_name": user["display_name"],
            "total_pts": total_pts,
            "tendency_count": tendency_count,
            "exact_count": exact_count,
            "risk_ok": risk_ok,
            "risk_fail": risk_fail,
            "tendency_bonus": bonus_pts > 0,
        })

    entries.sort(key=lambda e: (-e["total_pts"], -e["exact_count"], -e["tendency_count"]))
    for i, e in enumerate(entries, 1):
        e["rank"] = i

    return entries


@bp.route("/dashboard")
@login_required
def dashboard():
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    user = session["username"]
    now = datetime.now(timezone.utc)

    matchdays = match_repo.matchdays()
    upcoming = []
    missing_count = 0

    for md in matchdays:
        if match_repo.is_matchday_locked(md):
            continue
        matches = match_repo.by_matchday(md)
        for m in matches:
            tip = tip_repo.get_user_tip(user, m["match_id"])
            if not tip:
                missing_count += 1
        if not upcoming:
            upcoming = matches

    # Next unlocked match (first match of first unlocked matchday)
    next_match = None
    for md in matchdays:
        if not match_repo.is_matchday_locked(md):
            for m in match_repo.by_matchday(md):
                if m["kickoff_at"]:
                    next_match = m
                    break
            break

    # Current rank
    lb = _build_leaderboard_data()
    my_rank = next((e["rank"] for e in lb if e["username"] == user), None)
    my_pts = next((e["total_pts"] for e in lb if e["username"] == user), 0.0)
    # is_last: True if user shares the same points as the last-place user
    is_last = False
    if lb:
        min_pts = min(e["total_pts"] for e in lb)
        if my_pts <= min_pts:
            is_last = True

    # Risk pick status for next open matchday
    risk_matchday = None
    risk_match_id = None
    if next_match:
        risk_matchday = next_match["matchday"]
        risk_match_id = tip_repo.get_user_risk_pick_for_matchday(user, risk_matchday, match_repo)

    soon_matches = []
    from datetime import timedelta
    for md in matchdays:
        if match_repo.is_matchday_locked(md):
            continue
        for m in match_repo.by_matchday(md):
            if m["kickoff_at"]:
                diff = m["kickoff_at"] - now
                if timedelta(0) < diff <= timedelta(hours=6):
                    tip = tip_repo.get_user_tip(user, m["match_id"])
                    soon_matches.append({"match": m, "has_tip": tip is not None})

    user_data = current_app.user_repo.find_by_username(user) or {}
    sav_confirmed = (
        user_data.get("sav_doc_id") == _cfg.SAV_DOC_ID and
        user_data.get("sav_doc_version") == _cfg.SAV_DOC_VERSION and
        bool(user_data.get("sav_confirmed_at"))
    )

    md1_kickoffs = [m["kickoff_at"] for m in match_repo.by_matchday(1) if m["kickoff_at"]]
    wc_deadline = max(md1_kickoffs) if md1_kickoffs else None
    wc_locked = bool(wc_deadline and datetime.now(timezone.utc) >= wc_deadline)
    wc_pick = current_app.wc_pick_repo.get_pick(user)

    return render_template("dashboard.html",
        missing_count=missing_count,
        next_match=next_match,
        my_rank=my_rank,
        my_pts=my_pts,
        is_last=is_last,
        risk_matchday=risk_matchday,
        risk_match_id=risk_match_id,
        soon_matches=soon_matches,
        matchdays=matchdays,
        now=now,
        sav_confirmed=sav_confirmed,
        wc_pick=wc_pick,
        wc_locked=wc_locked,
        wc_deadline=wc_deadline,
        wc_team_flags=_WC_TEAM_FLAGS,
    )


@bp.post("/training/confirm")
@login_required
def confirm_training():
    username = session["username"]
    user_repo = current_app.user_repo
    user_data = user_repo.find_by_username(username)
    if not user_data:
        return jsonify({"error": "not found"}), 404
    user_data["sav_doc_id"] = _cfg.SAV_DOC_ID
    user_data["sav_doc_version"] = _cfg.SAV_DOC_VERSION
    user_data["sav_confirmed_at"] = datetime.now(timezone.utc).isoformat()
    user_repo.save(user_data)
    return jsonify({"ok": True})


@bp.post("/world-cup-pick")
@login_required
def save_world_cup_pick():
    user = session["username"]
    md1_kickoffs = [m["kickoff_at"] for m in current_app.match_repo.by_matchday(1) if m["kickoff_at"]]
    if md1_kickoffs and datetime.now(timezone.utc) >= max(md1_kickoffs):
        flash("Das letzte Spiel von Spieltag 1 hat begonnen – WM-Sieger-Tipp ist gesperrt.", "error")
        return redirect(url_for("main.dashboard"))
    team = request.form.get("team", "").strip()
    if team not in _WC_TEAM_FLAGS:
        flash("Ungültige Teamauswahl.", "error")
        return redirect(url_for("main.dashboard"))
    current_app.wc_pick_repo.save_pick(user, team)
    flash(f"WM-Sieger-Tipp gesetzt: {_WC_TEAM_FLAGS[team]} {team}", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/matchday/<int:matchday>")
@login_required
def matchday(matchday: int):
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo
    user = session["username"]
    now = datetime.now(timezone.utc)

    matches = match_repo.by_matchday(matchday)
    if not matches:
        return redirect(url_for("main.dashboard"))

    risk_match_id = tip_repo.get_user_risk_pick_for_matchday(user, matchday, match_repo)

    matchday_locked = match_repo.is_matchday_locked(matchday)

    items = []
    for m in matches:
        locked = matchday_locked or match_repo.is_locked(m)
        tip = tip_repo.get_user_tip(user, m["match_id"])
        result = result_repo.find(m["match_id"])

        # Rarity distribution
        if locked and m["kickoff_at"]:
            distrib = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
        else:
            distrib = snapshot_repo.compute_live(m["match_id"], tip_repo)

        # Score breakdown (if result available)
        score_bd = None
        if result and result["status"] == "final" and tip:
            snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
            score_bd = calculate_score(
                result["home_goals_actual"], result["away_goals_actual"],
                tip["home_goals_tip"], tip["away_goals_tip"],
                tip["is_risk_pick"], m["is_germany_game"], snap,
            )

        # Potential rarity bonus (for live display)
        from app.scoring.engine import calculate_potential_rarity
        potential_rarity = 0.0
        if tip and not locked:
            potential_rarity = calculate_potential_rarity(
                tip["home_goals_tip"], tip["away_goals_tip"], distrib
            )

        # Status label
        if result and result["status"] == "final":
            status = "evaluated"
        elif locked:
            status = "locked"
        elif tip:
            status = "tipped"
        else:
            status = "open"

        items.append({
            "match": m,
            "tip": tip,
            "result": result,
            "score_bd": score_bd,
            "distrib": distrib,
            "potential_rarity": potential_rarity,
            "locked": locked or (result is not None and result["status"] == "final"),
            "status": status,
            "is_risk": m["match_id"] == risk_match_id,
        })

    # Per-user per-game scores table (all started/finished matches)
    # Tips are revealed once a game is locked (kickoff past); scores only after result is final.
    active_matches = [m for m in matches if match_repo.is_locked(m)]
    users = [u for u in user_repo.all() if u["active"]]
    user_match_scores = {}
    for u in users:
        uname = u["username"]
        user_match_scores[uname] = {}
        for m in active_matches:
            utip = tip_repo.get_user_tip(uname, m["match_id"])
            result = result_repo.find(m["match_id"])
            bd = None
            if result and result["status"] == "final" and utip:
                snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
                bd = calculate_score(
                    result["home_goals_actual"], result["away_goals_actual"],
                    utip["home_goals_tip"], utip["away_goals_tip"],
                    utip["is_risk_pick"], m["is_germany_game"], snap,
                )
            user_match_scores[uname][m["match_id"]] = {"tip": utip, "bd": bd}

    # Build entries list (display_name + total pts for this matchday) for the table header
    md_entries = _build_leaderboard_data(matchday_filter=matchday)

    matchdays = match_repo.matchdays()
    return render_template("matchday.html",
        matchday=matchday,
        items=items,
        matchdays=matchdays,
        risk_match_id=risk_match_id,
        now=now,
        active_matches=active_matches,
        user_match_scores=user_match_scores,
        md_entries=md_entries,
    )


def _get_last_evaluated_md():
    """Return the last matchday that has at least one final result."""
    match_repo = current_app.match_repo
    result_repo = current_app.result_repo
    for md in reversed(match_repo.matchdays()):
        matches = match_repo.by_matchday(md)
        if any(
            (r := result_repo.find(m["match_id"])) and r["status"] == "final"
            for m in matches
        ):
            return md
    return None


def _build_md_score_section(md, match_repo, tip_repo, result_repo, snapshot_repo, user_repo):
    """Build the data dict for one matchday's PUNKTE JE SPIELER table."""
    md_matches = match_repo.by_matchday(md)
    results_by_id = {r["match_id"]: r for r in result_repo.all()}
    active = [
        m for m in md_matches
        if match_repo.is_locked(m) or results_by_id.get(m["match_id"], {}).get("status") == "final"
    ]
    if not active:
        return None
    users = [u for u in user_repo.all() if u["active"]]
    md_entries = _build_leaderboard_data(matchday_filter=md)
    user_match_scores = {}
    for u in users:
        uname = u["username"]
        user_match_scores[uname] = {}
        for m in active:
            utip = tip_repo.get_user_tip(uname, m["match_id"])
            result = result_repo.find(m["match_id"])
            bd = None
            if result and result["status"] == "final" and utip and m["kickoff_at"]:
                snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
                bd = calculate_score(
                    result["home_goals_actual"], result["away_goals_actual"],
                    utip["home_goals_tip"], utip["away_goals_tip"],
                    utip["is_risk_pick"], m["is_germany_game"], snap,
                )
            user_match_scores[uname][m["match_id"]] = {"tip": utip, "bd": bd}
    return {"matchday": md, "active_matches": active, "user_match_scores": user_match_scores, "md_entries": md_entries}


@bp.route("/leaderboard")
@login_required
def leaderboard():
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo
    entries = _build_leaderboard_data()
    matchdays = match_repo.matchdays()
    last_evaluated_md = _get_last_evaluated_md()
    md_score_sections = [
        sec for md in matchdays
        for sec in [_build_md_score_section(md, match_repo, tip_repo, result_repo, snapshot_repo, user_repo)]
        if sec
    ]
    return render_template("leaderboard.html", entries=entries, matchdays=matchdays,
                           current_matchday=None, last_evaluated_md=last_evaluated_md,
                           md_score_sections=md_score_sections)


@bp.route("/leaderboard/<int:matchday>")
@login_required
def leaderboard_matchday(matchday: int):
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo
    entries = _build_leaderboard_data(matchday_filter=matchday)
    matchdays = match_repo.matchdays()
    last_evaluated_md = _get_last_evaluated_md()
    sec = _build_md_score_section(matchday, match_repo, tip_repo, result_repo, snapshot_repo, user_repo)
    md_score_sections = [sec] if sec else []
    return render_template("leaderboard.html", entries=entries, matchdays=matchdays,
                           current_matchday=matchday, last_evaluated_md=last_evaluated_md,
                           md_score_sections=md_score_sections)


@bp.route("/my-tips")
@login_required
def my_tips():
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user = session["username"]

    matchdays = match_repo.matchdays()
    sections = []
    for md in matchdays:
        matches = match_repo.by_matchday(md)
        items = []
        md_locked = match_repo.is_matchday_locked(md)
        for m in matches:
            locked = md_locked
            tip = tip_repo.get_user_tip(user, m["match_id"])
            result = result_repo.find(m["match_id"])
            score_bd = None
            if result and result["status"] == "final" and tip and m["kickoff_at"]:
                snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
                score_bd = calculate_score(
                    result["home_goals_actual"], result["away_goals_actual"],
                    tip["home_goals_tip"], tip["away_goals_tip"],
                    tip["is_risk_pick"], m["is_germany_game"], snap,
                )
            items.append({"match": m, "tip": tip, "result": result, "score_bd": score_bd, "locked": locked})
        sections.append({"matchday": md, "items": items})

    return render_template("my_tips.html", sections=sections, matchdays=matchdays)


@bp.route("/tip-detail/<match_id>")
@login_required
def tip_detail(match_id: str):
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo
    user = session["username"]

    match = match_repo.find(match_id)
    if not match:
        return redirect(url_for("main.dashboard"))

    tip = tip_repo.get_user_tip(user, match_id)
    result = result_repo.find(match_id)
    score_bd = None
    snap = None
    other_tips = []

    if result and result["status"] == "final" and match["kickoff_at"]:
        snap = snapshot_repo.get_or_create(match_id, match["kickoff_at"], tip_repo)
        if tip:
            score_bd = calculate_score(
                result["home_goals_actual"], result["away_goals_actual"],
                tip["home_goals_tip"], tip["away_goals_tip"],
                tip["is_risk_pick"], match["is_germany_game"], snap,
            )
        for ou in [u for u in user_repo.all() if u["active"] and u["username"] != user]:
            other_tip = tip_repo.get_user_tip(ou["username"], match_id)
            other_bd = None
            if other_tip:
                other_bd = calculate_score(
                    result["home_goals_actual"], result["away_goals_actual"],
                    other_tip["home_goals_tip"], other_tip["away_goals_tip"],
                    other_tip["is_risk_pick"], match["is_germany_game"], snap,
                )
            other_tips.append({
                "display_name": ou.get("display_name", ou["username"]),
                "tip": other_tip,
                "bd": other_bd,
            })
        other_tips.sort(key=lambda x: -(x["bd"].final_pts if x["bd"] else 0))

    matchdays = match_repo.matchdays()
    return render_template("tip_detail.html",
        match=match,
        tip=tip,
        result=result,
        score_bd=score_bd,
        snap=snap,
        matchdays=matchdays,
        other_tips=other_tips,
    )


_WC_TEAM_FLAGS = {
    "Mexiko": "🇲🇽",
    "Südafrika": "🇿🇦",
    "Südkorea": "🇰🇷",
    "Tschechien": "🇨🇿",
    "Kanada": "🇨🇦",
    "Bosnien und Herzegowina": "🇧🇦",
    "Schweiz": "🇨🇭",
    "Katar": "🇶🇦",
    "Brasilien": "🇧🇷",
    "Marokko": "🇲🇦",
    "Schottland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Haiti": "🇭🇹",
    "USA": "🇺🇸",
    "Paraguay": "🇵🇾",
    "Australien": "🇦🇺",
    "Türkei": "🇹🇷",
    "Deutschland": "🇩🇪",
    "Ecuador": "🇪🇨",
    "Elfenbeinküste": "🇨🇮",
    "Curaçao": "🇨🇼",
    "Niederlande": "🇳🇱",
    "Japan": "🇯🇵",
    "Schweden": "🇸🇪",
    "Tunesien": "🇹🇳",
    "Belgien": "🇧🇪",
    "Iran": "🇮🇷",
    "Ägypten": "🇪🇬",
    "Neuseeland": "🇳🇿",
    "Spanien": "🇪🇸",
    "Kap Verde": "🇨🇻",
    "Saudi-Arabien": "🇸🇦",
    "Uruguay": "🇺🇾",
    "Frankreich": "🇫🇷",
    "Senegal": "🇸🇳",
    "Irak": "🇮🇶",
    "Norwegen": "🇳🇴",
    "Argentinien": "🇦🇷",
    "Algerien": "🇩🇿",
    "Österreich": "🇦🇹",
    "Jordanien": "🇯🇴",
    "Portugal": "🇵🇹",
    "Kolumbien": "🇨🇴",
    "Usbekistan": "🇺🇿",
    "DR Kongo": "🇨🇩",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Kroatien": "🇭🇷",
    "Panama": "🇵🇦",
    "Ghana": "🇬🇭",
}

_WM_GROUPS = {
    "A": ["Mexiko", "Südafrika", "Südkorea", "Tschechien"],
    "B": ["Kanada", "Bosnien und Herzegowina", "Schweiz", "Katar"],
    "C": ["Brasilien", "Marokko", "Schottland", "Haiti"],
    "D": ["USA", "Paraguay", "Australien", "Türkei"],
    "E": ["Deutschland", "Ecuador", "Elfenbeinküste", "Curaçao"],
    "F": ["Niederlande", "Japan", "Schweden", "Tunesien"],
    "G": ["Belgien", "Iran", "Ägypten", "Neuseeland"],
    "H": ["Spanien", "Kap Verde", "Saudi-Arabien", "Uruguay"],
    "I": ["Frankreich", "Senegal", "Irak", "Norwegen"],
    "J": ["Argentinien", "Algerien", "Österreich", "Jordanien"],
    "K": ["Portugal", "Kolumbien", "Usbekistan", "DR Kongo"],
    "L": ["England", "Kroatien", "Panama", "Ghana"],
}


@bp.route("/turnierplan")
@login_required
def turnierplan():
    match_repo = current_app.match_repo
    result_repo = current_app.result_repo
    matchdays = match_repo.matchdays()

    # Build group standings from group stage matches (matchdays 1-3)
    group_standings = {}
    for letter, teams in _WM_GROUPS.items():
        standing = {t: {"team": t, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for t in teams}
        group_standings[letter] = standing

    group_matches = {}
    for letter in _WM_GROUPS:
        group_matches[letter] = []

    # Collect group stage results (matchdays 1-3)
    for md in [1, 2, 3]:
        for m in match_repo.by_matchday(md):
            result = result_repo.find(m["match_id"])
            # Determine group by checking which group contains both teams
            home, away = m["home_team"], m["away_team"]
            grp = None
            for letter, teams in _WM_GROUPS.items():
                if home in teams and away in teams:
                    grp = letter
                    break
            if grp:
                group_matches[grp].append({"match": m, "result": result})
                if result and result["status"] == "final":
                    hg, ag = result["home_goals_actual"], result["away_goals_actual"]
                    if home in group_standings[grp]:
                        group_standings[grp][home]["p"] += 1
                        group_standings[grp][home]["gf"] += hg
                        group_standings[grp][home]["ga"] += ag
                    if away in group_standings[grp]:
                        group_standings[grp][away]["p"] += 1
                        group_standings[grp][away]["gf"] += ag
                        group_standings[grp][away]["ga"] += hg
                    if hg > ag:
                        if home in group_standings[grp]:
                            group_standings[grp][home]["w"] += 1
                            group_standings[grp][home]["pts"] += 3
                        if away in group_standings[grp]:
                            group_standings[grp][away]["l"] += 1
                    elif hg < ag:
                        if away in group_standings[grp]:
                            group_standings[grp][away]["w"] += 1
                            group_standings[grp][away]["pts"] += 3
                        if home in group_standings[grp]:
                            group_standings[grp][home]["l"] += 1
                    else:
                        for t in [home, away]:
                            if t in group_standings[grp]:
                                group_standings[grp][t]["d"] += 1
                                group_standings[grp][t]["pts"] += 1

    # Sort each group
    sorted_groups = {}
    for letter, standing in group_standings.items():
        rows = sorted(standing.values(),
                      key=lambda r: (-r["pts"], -(r["gf"] - r["ga"]), -r["gf"]))
        sorted_groups[letter] = rows

    # Knockout matches
    knockout = {}
    for md, label in [(4, "16EL"), (5, "AF"), (6, "VF"), (7, "HF"), (8, "P3"), (9, "F")]:
        matches = match_repo.by_matchday(md)
        items = []
        for m in matches:
            result = result_repo.find(m["match_id"])
            items.append({"match": m, "result": result})
        if items:
            knockout[label] = items

    return render_template("turnierplan.html",
        matchdays=matchdays,
        groups=_WM_GROUPS,
        sorted_groups=sorted_groups,
        group_matches=group_matches,
        knockout=knockout,
    )


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_repo = current_app.user_repo
    username = session["username"]
    user = user_repo.find_by_username(username)

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        if not display_name:
            flash("Anzeigename darf nicht leer sein.", "error")
        elif len(display_name) > 50:
            flash("Anzeigename zu lang (max. 50 Zeichen).", "error")
        elif ";" in display_name:
            flash("Anzeigename darf kein Semikolon enthalten.", "error")
        else:
            user_repo.save({**user, "display_name": display_name})
            session["display_name"] = display_name
            flash("Anzeigename gespeichert.", "success")
            return redirect(url_for("main.profile"))

    from app import config as _cfg
    return render_template("profile.html", user=user, payment_link=_cfg.PAYMENT_LINK)


@bp.route("/wrap-up")
@login_required
def wrap_up():
    """Last completed matchday wrap-up: scores + winner highlight."""
    match_repo = current_app.match_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    tip_repo = current_app.tip_repo
    user_repo = current_app.user_repo

    # Find the last matchday that has at least one final result
    last_evaluated_md = None
    for md in reversed(match_repo.matchdays()):
        matches = match_repo.by_matchday(md)
        if any(
            (r := result_repo.find(m["match_id"])) and r["status"] == "final"
            for m in matches
        ):
            last_evaluated_md = md
            break

    if last_evaluated_md is None:
        flash("Noch keine ausgewerteten Spieltage.", "info")
        return redirect(url_for("main.leaderboard"))

    # Build per-user scores for that matchday
    entries = _build_leaderboard_data(matchday_filter=last_evaluated_md)

    # Build match results for that matchday
    matches = match_repo.by_matchday(last_evaluated_md)
    now = datetime.now(timezone.utc)
    active_matches = [m for m in matches if match_repo.is_locked(m)]
    match_items = []
    for m in matches:
        result = result_repo.find(m["match_id"])
        match_items.append({"match": m, "result": result})

    # Build per-user per-match score breakdown for started matches
    # Tips visible once game started; scores only after result is final.
    users = [u for u in user_repo.all() if u["active"]]
    user_match_scores = {}
    for user in users:
        uname = user["username"]
        user_match_scores[uname] = {}
        for m in active_matches:
            tip = tip_repo.get_user_tip(uname, m["match_id"])
            result = result_repo.find(m["match_id"])
            bd = None
            if result and result["status"] == "final" and tip:
                snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
                bd = calculate_score(
                    result["home_goals_actual"], result["away_goals_actual"],
                    tip["home_goals_tip"], tip["away_goals_tip"],
                    tip["is_risk_pick"], m["is_germany_game"], snap,
                )
            user_match_scores[uname][m["match_id"]] = {"tip": tip, "bd": bd}

    matchdays = match_repo.matchdays()
    return render_template("wrap_up.html",
        matchday=last_evaluated_md,
        entries=entries,
        match_items=match_items,
        matchdays=matchdays,
        user_match_scores=user_match_scores,
        active_matches=active_matches,
    )


@bp.route("/health")
def health():
    return {"status": "ok"}, 200
