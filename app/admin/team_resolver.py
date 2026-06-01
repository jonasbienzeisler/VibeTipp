import re
from typing import Optional

# Pattern → (matchday of source round, "winner" or "loser")
_PATTERNS = [
    (re.compile(r"^Sieger (\d+)\. 16tel-Finale$"), 4, "winner"),
    (re.compile(r"^Sieger (\d+)\. AF$"), 5, "winner"),
    (re.compile(r"^Sieger VF (\d+)$"), 6, "winner"),
    (re.compile(r"^Sieger Halbfinale (\d+)$"), 7, "winner"),
    (re.compile(r"^Verlierer Halbfinale (\d+)$"), 7, "loser"),
]


def _sorted_by_id(match_repo, matchday: int) -> list[dict]:
    return sorted(match_repo.by_matchday(matchday), key=lambda m: m["match_id"])


def _parse_team_name(name: str, match_repo) -> tuple[Optional[str], Optional[str]]:
    """Return (source_match_id, outcome) if name is a placeholder, else (None, None)."""
    name = name.strip()
    for pattern, matchday, outcome in _PATTERNS:
        m = pattern.match(name)
        if m:
            n = int(m.group(1))
            matches = _sorted_by_id(match_repo, matchday)
            if 1 <= n <= len(matches):
                return matches[n - 1]["match_id"], outcome
            return None, None
    return None, None


def _resolve_team(match_id: str, outcome: str, match_repo, results: dict) -> Optional[str]:
    r = results.get(match_id)
    if not r or r["status"] != "final":
        return None
    h, a = r.get("home_goals_actual"), r.get("away_goals_actual")
    if h is None or a is None:
        return None
    src = match_repo.find(match_id)
    if not src:
        return None
    if h > a:
        return src["home_team"] if outcome == "winner" else src["away_team"]
    if a > h:
        return src["away_team"] if outcome == "winner" else src["home_team"]
    return None  # draw — can't determine winner


def get_resolution_preview(match_repo, result_repo) -> list[dict]:
    """
    Returns items for matches with placeholder team names.
    Each item has: match_id, matchday, home_current, away_current,
                   home_resolved, away_resolved, resolvable.
    """
    results = {r["match_id"]: r for r in result_repo.all()}
    preview = []

    for match in match_repo.all():
        home, away = match["home_team"], match["away_team"]
        home_src, home_out = _parse_team_name(home, match_repo)
        away_src, away_out = _parse_team_name(away, match_repo)

        if home_src is None and away_src is None:
            continue

        home_res = _resolve_team(home_src, home_out, match_repo, results) if home_src else home
        away_res = _resolve_team(away_src, away_out, match_repo, results) if away_src else away

        preview.append({
            "match_id": match["match_id"],
            "matchday": match["matchday"],
            "home_current": home,
            "away_current": away,
            "home_resolved": home_res,
            "away_resolved": away_res,
            "resolvable": home_res is not None and away_res is not None,
        })

    return preview


def apply_resolutions(preview: list[dict], match_repo) -> int:
    """Apply all resolvable updates. Returns count of updated matches."""
    count = 0
    for item in preview:
        if item["resolvable"]:
            match_repo.update_team_names(item["match_id"], item["home_resolved"], item["away_resolved"])
            count += 1
    return count
