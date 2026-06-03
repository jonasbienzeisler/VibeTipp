from flask import Blueprint, jsonify, session, redirect, url_for, current_app, render_template_string
from markupsafe import escape
from app.scoring.engine import calculate_potential_rarity, get_tendency, Tendency, calculate_score
from app import config as app_config
from datetime import datetime, timezone

bp = Blueprint("api", __name__, url_prefix="/api")


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@bp.get("/rarity/<match_id>")
@login_required
def live_rarity(match_id: str):
    """Returns live rarity distribution and potential bonus for current user tip."""
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    snapshot_repo = current_app.snapshot_repo
    user = session["username"]

    match = match_repo.find(match_id)
    if not match:
        return jsonify({"error": "not found"}), 404

    locked = match_repo.is_locked(match)

    if locked and match["kickoff_at"]:
        distrib = snapshot_repo.get_or_create(match_id, match["kickoff_at"], tip_repo)
        frozen = True
    else:
        distrib = snapshot_repo.compute_live(match_id, tip_repo)
        frozen = False

    tip = tip_repo.get_user_tip(user, match_id)
    potential = 0.0
    rarity_share = None
    rarity_tendency = None
    if tip:
        potential = calculate_potential_rarity(tip["home_goals_tip"], tip["away_goals_tip"], distrib)
        if distrib.get("total_tips", 0) > 0:
            tip_t = get_tendency(tip["home_goals_tip"], tip["away_goals_tip"])
            rarity_tendency = tip_t.value
            if tip_t == Tendency.HOME:
                rarity_share = float(distrib.get("home_win_share", 0))
            elif tip_t == Tendency.DRAW:
                rarity_share = float(distrib.get("draw_share", 0))
            else:
                rarity_share = float(distrib.get("away_win_share", 0))

    total = distrib.get("total_tips", 0)
    return jsonify({
        "match_id": match_id,
        "home_win_share": distrib["home_win_share"],
        "draw_share": distrib["draw_share"],
        "away_win_share": distrib["away_win_share"],
        "total_tips": total,
        "home_win_pct": round(distrib["home_win_share"] * 100, 1),
        "draw_pct": round(distrib["draw_share"] * 100, 1),
        "away_win_pct": round(distrib["away_win_share"] * 100, 1),
        "rarity_factor": potential,       # factor 1.0–2.0 (2 - share)
        "frozen": frozen,
        "rarity_share": rarity_share,
        "rarity_tendency": rarity_tendency,
        "rarity_max": app_config.RARITY_MAX_POINTS,  # 2.0
    })


@bp.get("/busy")
def file_busy():
    """Check if any data files are currently locked by another writer."""
    from pathlib import Path
    data_dir = current_app.config["DATA_DIR"]
    lock_files = list(Path(data_dir).glob("*.lock"))
    busy = any(lf.exists() for lf in lock_files)
    return jsonify({"busy": busy})


_USER_TIPS_PANEL_TEMPLATE = """
<div class="user-tips-panel">
  <div class="utp-header">
    <span>{{ display_name | upper }} – ERGEBNISSE</span>
    <a href="/api/user/{{ username }}/results.txt" class="utp-dl-link" title="Als Textdatei herunterladen">⬇ TXT</a>
  </div>
  <div style="color:rgba(255,255,255,0.4);font-size:0.45rem;margin-bottom:0.6rem;">
    Nur ausgewertete Spieltage · Nicht ausgewertete Spiele werden nicht angezeigt
  </div>
  {% if not sections %}
  <div style="color:rgba(255,255,255,0.3);font-size:0.5rem;padding:0.5rem;">Noch keine ausgewerteten Spiele.</div>
  {% endif %}
  {% for section in sections %}
  <div class="utp-md-header">SPIELTAG {{ section.matchday }}</div>
  {% if section.games %}
  <table class="utp-table">
    <thead>
      <tr>
        <th style="text-align:left">SPIEL</th>
        <th>TIPP</th>
        <th>ERGEBNIS</th>
        <th title="Tendenz">T.</th>
        <th title="Exakt (effektiv)">EX.</th>
        <th title="Raritätsfaktor">×R</th>
        <th title="Hochrisiko">RISK</th>
        <th>PUNKTE</th>
      </tr>
    </thead>
    <tbody>
      {% for item in section.games %}
      <tr>
        <td class="utp-match">
          {{ item.home | upper }} – {{ item.away | upper }}
          {% if item.is_germany %}
          <span style="color:var(--gold);font-size:0.4rem">🇩🇪×2</span>
          {% endif %}
        </td>
        {% if item.tip %}
        <td class="utp-tip">{{ item.tip_home }}:{{ item.tip_away }}{% if item.is_risk %}<span style="color:var(--purple);margin-left:2px">!</span>{% endif %}</td>
        {% else %}
        <td class="utp-no-tip">–</td>
        {% endif %}
        {% if item.result_home is not none %}
        <td class="utp-result">{{ item.result_home }}:{{ item.result_away }}</td>
        {% else %}
        <td class="utp-no-tip">–</td>
        {% endif %}
        {% if item.bd %}
        <td style="font-size:0.42rem;color:{% if item.bd.tendency_correct %}var(--green){% else %}rgba(255,255,255,0.4){% endif %}">+{{ item.bd.tendency_pts }}</td>
        <td style="font-size:0.42rem;color:var(--cyan)">+{{ "%.1f"|format(item.bd.exactness_effective) }}</td>
        <td style="font-size:0.42rem;color:var(--amber)">×{{ "%.2f"|format(item.bd.rarity_factor) }}</td>
        <td style="font-size:0.42rem;">
          {% if item.bd.risk_result == 'double' %}<span style="color:var(--purple)">×2</span>
          {% elif item.bd.risk_result == 'deduct' %}<span style="color:var(--red)">ABZUG</span>
          {% elif item.bd.risk_result == 'neutral' %}<span style="color:rgba(255,255,255,0.4)">±0</span>
          {% else %}–{% endif %}
        </td>
        {% else %}
        <td>–</td><td>–</td><td>–</td><td>–</td>
        {% endif %}
        {% if item.pts is not none %}
          {% if item.pts > 0 %}
          <td class="utp-pts-pos">+{{ "%.1f"|format(item.pts) }}</td>
          {% elif item.pts < 0 %}
          <td class="utp-pts-neg">{{ "%.1f"|format(item.pts) }}</td>
          {% else %}
          <td class="utp-pts-zero">0</td>
          {% endif %}
        {% else %}
        <td class="utp-no-tip">–</td>
        {% endif %}
      </tr>
      {% endfor %}
      <tr class="utp-subtotal-row">
        <td colspan="7" style="text-align:right;font-size:0.45rem;color:rgba(255,255,255,0.5);">SPIELTAG {{ section.matchday }} GESAMT</td>
        {% set md_sum = namespace(v=0.0) %}
        {% for p in section.games %}{% if p.pts is not none %}{% set md_sum.v = md_sum.v + p.pts %}{% endif %}{% endfor %}
        {% if md_sum.v > 0 %}
        <td class="utp-pts-pos">+{{ "%.1f"|format(md_sum.v) }}</td>
        {% elif md_sum.v < 0 %}
        <td class="utp-pts-neg">{{ "%.1f"|format(md_sum.v) }}</td>
        {% else %}
        <td class="utp-pts-zero">0</td>
        {% endif %}
      </tr>
    </tbody>
  </table>
  {% else %}
  <div style="color:rgba(255,255,255,0.3);font-size:0.5rem;padding:0.3rem;">Keine ausgewerteten Spiele in diesem Spieltag.</div>
  {% endif %}
  {% endfor %}
</div>
"""


@bp.get("/user/<username>/tips-panel")

@login_required
def user_tips_panel(username: str):
    """Returns an HTML partial showing evaluated results for a given user.
    Available to ALL logged-in users. Only shows matches with final results
    to prevent peeking at unevaluated games.
    """
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo

    user = user_repo.find_by_username(username)
    if not user:
        return "<div class='user-tips-panel' style='color:var(--red)'>Nutzer nicht gefunden.</div>", 404

    display_name = user.get("display_name", username)
    matchdays = match_repo.matchdays()
    sections = []

    for md in matchdays:
        matches = match_repo.by_matchday(md)
        # Only include matches with a final result – never show unevaluated tips.
        evaluated = [m for m in matches if
                     (r := result_repo.find(m["match_id"])) and r["status"] == "final"]
        if not evaluated:
            continue
        items = []
        for m in evaluated:
            tip = tip_repo.get_user_tip(username, m["match_id"])
            result = result_repo.find(m["match_id"])
            pts = None
            bd = None
            if tip and m.get("kickoff_at"):
                snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
                bd = calculate_score(
                    result["home_goals_actual"], result["away_goals_actual"],
                    tip["home_goals_tip"], tip["away_goals_tip"],
                    tip["is_risk_pick"], m["is_germany_game"], snap,
                )
                pts = bd.final_pts
            items.append({
                "home": m["home_team"],
                "away": m["away_team"],
                "is_germany": m["is_germany_game"],
                "tip": tip,
                "is_risk": tip["is_risk_pick"] if tip else False,
                "tip_home": tip["home_goals_tip"] if tip else None,
                "tip_away": tip["away_goals_tip"] if tip else None,
                "result_home": result["home_goals_actual"],
                "result_away": result["away_goals_actual"],
                "bd": bd,
                "pts": pts,
            })
        sections.append({"matchday": md, "games": items})

    html = current_app.jinja_env.from_string(_USER_TIPS_PANEL_TEMPLATE).render(
        display_name=escape(display_name),
        username=escape(username),
        sections=sections,
    )
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@bp.get("/user/<username>/results.txt")
@login_required
def user_results_txt(username: str):
    """Serve the pre-generated per-user result txt file."""
    from flask import Response
    writer = current_app.player_results_writer
    user_repo = current_app.user_repo
    user = user_repo.find_by_username(username)
    if not user:
        return Response("Nutzer nicht gefunden.", status=404, mimetype="text/plain")

    if not writer.exists(username):
        # Generate on-demand if file doesn't exist yet
        writer.generate_for_user(
            username, user.get("display_name", username),
            current_app.match_repo, current_app.tip_repo,
            current_app.result_repo, current_app.snapshot_repo,
            current_app.adj_repo,
        )

    if not writer.exists(username):
        return Response("Noch keine Ergebnisse verfügbar.", status=404, mimetype="text/plain")

    content = writer.get_path(username).read_text(encoding="utf-8")
    return Response(
        content,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{username}_ergebnisse.txt"'},
    )


@bp.get("/matchday/<int:matchday>/status")
@login_required
def matchday_status(matchday: int):
    """Quick status for dashboard countdowns."""
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    user = session["username"]
    now = datetime.now(timezone.utc)

    matches = match_repo.by_matchday(matchday)
    result = []
    for m in matches:
        tip = tip_repo.get_user_tip(user, m["match_id"])
        locked = match_repo.is_locked(m)
        seconds_to_kickoff = None
        if m["kickoff_at"] and not locked:
            diff = (m["kickoff_at"] - now).total_seconds()
            seconds_to_kickoff = max(0, int(diff))
        result.append({
            "match_id": m["match_id"],
            "locked": locked,
            "has_tip": tip is not None,
            "seconds_to_kickoff": seconds_to_kickoff,
        })
    return jsonify(result)


def _rank_img(rank, total):
    if rank == 1: return "first.png"
    if rank == 2: return "second.png"
    if rank == 3: return "third.png"
    if rank == total: return "last.png"
    return "ok.png"


_MD_OVERVIEW_TEMPLATE = """
<div class="md-overview-panel">
  <div class="md-ov-title">SPIELTAG {{ matchday }} &#8211; TIPPS-ÜBERSICHT</div>

  {% if ranking %}
  <div class="md-ov-ranking">
    {% for e in ranking %}
    <div class="md-ov-rank-row{% if e.username == current_user %} md-ov-me{% endif %}">
      <img src="/static/{{ e.rank_img }}" class="md-ov-rank-img" alt="">
      <span class="md-ov-rank-name">{{ e.display_name | upper }}</span>
      <span class="md-ov-rank-pts{% if e.total_pts < 0 %} neg{% endif %}">
        {% if e.total_pts > 0 %}+{% endif %}{{ "%.1f"|format(e.total_pts) }}
      </span>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if locked_matches %}
  <div class="md-ov-section-label">TIPPS UND PUNKTE JE SPIEL</div>
  <div class="md-ov-table-wrap">
    <table class="md-ov-table">
      <thead>
        <tr>
          <th>SPIELER</th>
          {% for m in locked_matches %}
          <th title="{{ m.home_team | upper }} &#8211; {{ m.away_team | upper }}">
            {{ m.match_id }}{% if m.is_germany_game %} 🇩🇪{% endif %}
          </th>
          {% endfor %}
        </tr>
        <tr class="md-ov-result-row">
          <td>ERGEBNIS</td>
          {% for m in locked_matches %}
            {% set r = results.get(m.match_id) %}
            <td>{% if r and r.status == 'final' %}{{ r.home_goals_actual }}:{{ r.away_goals_actual }}{% else %}<span style="color:rgba(255,255,255,0.25)">&#8211;</span>{% endif %}</td>
          {% endfor %}
        </tr>
      </thead>
      <tbody>
        {% for e in ranking %}
        <tr{% if e.username == current_user %} class="md-ov-me-row"{% endif %}>
          <td>{{ e.display_name | upper }}</td>
          {% for m in locked_matches %}
            {% set tip = tips.get(e.username, {}).get(m.match_id) %}
            {% set pts = match_pts.get(e.username, {}).get(m.match_id) %}
            <td class="md-ov-tip-cell">
              {% if tip %}
                <div style="color:var(--gold)">{{ tip.home_goals_tip }}:{{ tip.away_goals_tip }}{% if tip.is_risk_pick %}<span style="color:var(--purple)">!</span>{% endif %}</div>
                {% if pts is not none %}<div style="font-size:0.33rem;{% if pts > 0 %}color:var(--green){% elif pts < 0 %}color:var(--red){% else %}color:rgba(255,255,255,0.35){% endif %}">{% if pts > 0 %}+{% endif %}{{ "%.1f"|format(pts) }}</div>{% endif %}
              {% else %}<span style="color:rgba(255,255,255,0.2)">&#8211;</span>{% endif %}
            </td>
          {% endfor %}
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div style="color:rgba(255,255,255,0.4);font-size:0.45rem;padding:1rem;text-align:center;">
    Noch keine Spiele gestartet.
  </div>
  {% endif %}
</div>
"""


_USER_MATCHDAY_DETAIL_TEMPLATE = """
<div class="user-tips-panel">
  <div class="utp-header">
    <span>{{ display_name | upper }} &#8211; SPIELTAG {{ matchday }}</span>
  </div>
  {% if items %}
  <table class="utp-table">
    <thead>
      <tr>
        <th style="text-align:left">SPIEL</th>
        <th>TIPP</th>
        <th>ERG.</th>
        <th>RISK</th>
        <th>PTS</th>
      </tr>
    </thead>
    <tbody>
      {% for item in items %}
      <tr>
        <td class="utp-match">
          {{ item.home | upper }} &#8211; {{ item.away | upper }}
          {% if item.is_germany %}<span style="color:var(--gold);font-size:0.38rem"> &#127465;&#127466;&#215;2</span>{% endif %}
        </td>
        {% if item.tip %}<td class="utp-tip">{{ item.tip_home }}:{{ item.tip_away }}</td>
        {% else %}<td class="utp-no-tip">&#8211;</td>{% endif %}
        {% if item.result_home is not none %}<td class="utp-result">{{ item.result_home }}:{{ item.result_away }}</td>
        {% else %}<td class="utp-no-tip" style="font-size:0.35rem">OFFEN</td>{% endif %}
        <td>{% if item.is_risk %}<span style="color:var(--purple)">!</span>{% else %}<span style="color:rgba(255,255,255,0.25)">&#8211;</span>{% endif %}</td>
        {% if item.pts is not none %}
          {% if item.pts > 0 %}<td class="utp-pts-pos">+{{ "%.1f"|format(item.pts) }}</td>
          {% elif item.pts < 0 %}<td class="utp-pts-neg">{{ "%.1f"|format(item.pts) }}</td>
          {% else %}<td class="utp-pts-zero">0</td>{% endif %}
        {% else %}<td class="utp-no-tip">&#8211;</td>{% endif %}
      </tr>
      {% endfor %}
      <tr class="utp-subtotal-row">
        <td colspan="4" style="text-align:right;color:rgba(255,255,255,0.5);font-size:0.4rem">GESAMT SPIELTAG {{ matchday }}</td>
        {% if total_pts > 0 %}<td class="utp-pts-pos">+{{ "%.1f"|format(total_pts) }}</td>
        {% elif total_pts < 0 %}<td class="utp-pts-neg">{{ "%.1f"|format(total_pts) }}</td>
        {% else %}<td class="utp-pts-zero">0</td>{% endif %}
      </tr>
    </tbody>
  </table>
  {% else %}
  <div style="color:rgba(255,255,255,0.4);font-size:0.45rem;padding:0.8rem 0">
    Noch keine gesperrten Spiele in diesem Spieltag.
  </div>
  {% endif %}
</div>
"""


@bp.get("/matchday/<int:matchday>/overview")
@login_required
def matchday_overview(matchday: int):
    """HTML partial: all users' tips for locked matches of a matchday."""
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo
    current_user = session["username"]

    matches = match_repo.by_matchday(matchday)
    if not matches:
        return "<div class='md-overview-panel' style='color:var(--red);padding:1rem'>Spieltag nicht gefunden.</div>", 404

    locked_matches = [m for m in matches if match_repo.is_locked(m)]
    users = [u for u in user_repo.all() if u["active"]]

    results = {}
    for m in locked_matches:
        r = result_repo.find(m["match_id"])
        if r:
            results[m["match_id"]] = r

    tips = {}
    match_pts = {}
    for u in users:
        uname = u["username"]
        tips[uname] = {}
        match_pts[uname] = {}
        for m in locked_matches:
            tip = tip_repo.get_user_tip(uname, m["match_id"])
            tips[uname][m["match_id"]] = tip
            r = results.get(m["match_id"])
            if tip and r and r["status"] == "final" and m.get("kickoff_at"):
                snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
                bd = calculate_score(
                    r["home_goals_actual"], r["away_goals_actual"],
                    tip["home_goals_tip"], tip["away_goals_tip"],
                    tip["is_risk_pick"], m["is_germany_game"], snap,
                )
                match_pts[uname][m["match_id"]] = bd.final_pts

    # Build matchday ranking inline (avoids cross-module import)
    ranking = []
    for u in users:
        uname = u["username"]
        total = sum(match_pts.get(uname, {}).values()) if match_pts.get(uname) else 0.0
        ranking.append({
            "username": uname,
            "display_name": u.get("display_name", uname),
            "total_pts": total,
        })
    ranking.sort(key=lambda e: -e["total_pts"])
    n = len(ranking)
    for i, e in enumerate(ranking, 1):
        e["rank"] = i
        e["rank_img"] = _rank_img(i, n)

    safe_ranking = [{**e, "display_name": escape(e["display_name"])} for e in ranking]
    html = current_app.jinja_env.from_string(_MD_OVERVIEW_TEMPLATE).render(
        matchday=matchday,
        locked_matches=locked_matches,
        ranking=safe_ranking,
        results=results,
        tips=tips,
        match_pts=match_pts,
        current_user=current_user,
    )
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@bp.get("/user/<username>/matchday/<int:matchday>/detail")
@login_required
def user_matchday_detail(username: str, matchday: int):
    """Per-user per-matchday tip breakdown HTML partial."""
    match_repo = current_app.match_repo
    tip_repo = current_app.tip_repo
    result_repo = current_app.result_repo
    snapshot_repo = current_app.snapshot_repo
    user_repo = current_app.user_repo
    is_admin = session.get("role") == "admin"

    user = user_repo.find_by_username(username)
    if not user:
        return "<div class='user-tips-panel' style='color:var(--red)'>Nutzer nicht gefunden.</div>", 404

    display_name = user.get("display_name", username)
    matches = match_repo.by_matchday(matchday)
    if not matches:
        return "<div class='user-tips-panel' style='color:rgba(255,255,255,0.4)'>Spieltag nicht gefunden.</div>", 404

    # Admin sees all; regular users only see locked matches (after kickoff)
    visible = matches if is_admin else [m for m in matches if match_repo.is_locked(m)]

    items = []
    total_pts = 0.0
    for m in visible:
        tip = tip_repo.get_user_tip(username, m["match_id"])
        result = result_repo.find(m["match_id"])
        pts = None
        if tip and result and result["status"] == "final" and m.get("kickoff_at"):
            snap = snapshot_repo.get_or_create(m["match_id"], m["kickoff_at"], tip_repo)
            bd = calculate_score(
                result["home_goals_actual"], result["away_goals_actual"],
                tip["home_goals_tip"], tip["away_goals_tip"],
                tip["is_risk_pick"], m["is_germany_game"], snap,
            )
            pts = bd.final_pts
            total_pts += pts
        items.append({
            "home": m["home_team"],
            "away": m["away_team"],
            "is_germany": m["is_germany_game"],
            "tip": tip,
            "is_risk": tip["is_risk_pick"] if tip else False,
            "tip_home": tip["home_goals_tip"] if tip else None,
            "tip_away": tip["away_goals_tip"] if tip else None,
            "result_home": result["home_goals_actual"] if result and result["status"] == "final" else None,
            "result_away": result["away_goals_actual"] if result and result["status"] == "final" else None,
            "pts": pts,
        })

    html = current_app.jinja_env.from_string(_USER_MATCHDAY_DETAIL_TEMPLATE).render(
        display_name=escape(display_name),
        username=escape(username),
        matchday=matchday,
        items=items,
        total_pts=total_pts,
    )
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}
