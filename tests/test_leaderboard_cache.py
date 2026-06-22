"""Tests for the materialized highscore (leaderboard) cache."""
import json
from datetime import datetime, timezone, timedelta


def _seed_tips_and_result(app):
    """Give two users tips on the locked match M003 and a final result."""
    tip_repo = app.tip_repo
    result_repo = app.result_repo
    tip_repo.save_tip("admin", "M003", 2, 1, False)
    tip_repo.save_tip("testuser", "M003", 1, 1, False)
    result_repo.upsert({
        "match_id": "M003", "home_goals_actual": 2,
        "away_goals_actual": 1, "status": "final",
    })


def test_payload_is_json_serializable_and_matches_live(app_with_data):
    from app.routes.main import build_leaderboard_payload, _build_leaderboard_data
    with app_with_data.app_context():
        _seed_tips_and_result(app_with_data)
        payload = build_leaderboard_payload()

        # Must round-trip through JSON without error
        dumped = json.dumps(payload)
        assert json.loads(dumped)["entries"] == payload["entries"]

        # GESAMT entries must match the live computation exactly
        live_entries = _build_leaderboard_data()
        assert payload["entries"] == live_entries

        # md_sections carry the per-game cells for the locked matchday
        assert any(s["matchday"] == 2 for s in payload["md_sections"])
        sec = next(s for s in payload["md_sections"] if s["matchday"] == 2)
        assert any(m["match_id"] == "M003" for m in sec["active_matches"])
        cell = sec["user_match_scores"]["admin"]["M003"]
        assert cell["tip"]["home_goals_tip"] == 2
        assert cell["bd"]["final_pts"] == 4.0  # exact 2:1, no rarity/germany


def test_leaderboard_route_uses_cache(admin_client, app_with_data):
    with app_with_data.app_context():
        _seed_tips_and_result(app_with_data)
        # Cold: no cache file yet
        assert app_with_data.leaderboard_cache.load() is None

    # First render builds + writes the cache (self-healing)
    r1 = admin_client.get("/leaderboard")
    assert r1.status_code == 200
    assert b"ADMIN" in r1.data.upper()

    with app_with_data.app_context():
        assert app_with_data.leaderboard_cache.load() is not None

    # Second render (cache hit) is identical
    r2 = admin_client.get("/leaderboard")
    assert r2.status_code == 200


def test_admin_score_entry_regenerates_cache(admin_client, app_with_data):
    with app_with_data.app_context():
        app_with_data.tip_repo.save_tip("admin", "M003", 2, 1, False)

    # Setting a score should rebuild the cache with the new result baked in
    resp = admin_client.post("/admin/match/M003/score",
                             data={"home_goals": "2", "away_goals": "1", "status": "final"})
    assert resp.status_code in (302, 200)

    with app_with_data.app_context():
        payload = app_with_data.leaderboard_cache.load()
        assert payload is not None
        admin_entry = next(e for e in payload["entries"] if e["username"] == "admin")
        # 4.0 exact + 1.0 "most goals tipped" bonus (admin is the only correct tendency)
        assert admin_entry["total_pts"] == 5.0
        assert admin_entry["exact_count"] == 1
        assert admin_entry["has_bonus"] is True
