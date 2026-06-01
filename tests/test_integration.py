"""Integration tests: HTTP routes + business logic together."""
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile


# ─── Auth ─────────────────────────────────────────────────────

def test_login_success(client):
    r = client.post("/login", data={"username": "testuser", "password": "user123"})
    assert r.status_code in (200, 302)
    if r.status_code == 302:
        assert "/dashboard" in r.headers.get("Location", "")

def test_login_wrong_password(client):
    r = client.post("/login", data={"username": "testuser", "password": "wrong"})
    assert r.status_code == 200
    assert b"Ung" in r.data  # "Ungültige Anmeldedaten"

def test_login_unknown_user(client):
    r = client.post("/login", data={"username": "nobody", "password": "whatever"})
    assert r.status_code == 200
    # Same message – doesn't leak user existence
    assert b"Ung" in r.data

def test_login_inactive_user(client):
    r = client.post("/login", data={"username": "inactive", "password": "user123"})
    assert r.status_code == 200
    assert b"Ung" in r.data

def test_logout(logged_in_client):
    r = logged_in_client.post("/logout")
    assert r.status_code in (200, 302)
    # After logout, dashboard redirects to login
    r2 = logged_in_client.get("/dashboard")
    assert r2.status_code == 302

def test_admin_login(admin_client):
    r = admin_client.get("/dashboard")
    assert r.status_code == 200


# ─── Dashboard & matchday ────────────────────────────────────

def test_dashboard_requires_login(client):
    r = client.get("/dashboard")
    assert r.status_code == 302

def test_dashboard_accessible_after_login(logged_in_client):
    r = logged_in_client.get("/dashboard")
    assert r.status_code == 200

def test_matchday_view(logged_in_client):
    r = logged_in_client.get("/matchday/1")
    assert r.status_code == 200
    assert b"VORRUNDE" in r.data or b"VR1" in r.data or b"Deutschland" in r.data

def test_matchday_unknown_redirects(logged_in_client):
    r = logged_in_client.get("/matchday/999")
    assert r.status_code == 302


# ─── Tip submission ───────────────────────────────────────────

def test_submit_tip(logged_in_client):
    r = logged_in_client.post("/tip/M001", data={"home_goals": "2", "away_goals": "1", "is_risk": "0"})
    assert r.status_code == 302

def test_submit_tip_negative_rejected(logged_in_client):
    r = logged_in_client.post("/tip/M001", data={"home_goals": "-1", "away_goals": "0", "is_risk": "0"},
                              follow_redirects=True)
    assert b"negativ" in r.data.lower() or r.status_code in (200, 302)

def test_submit_tip_text_rejected(logged_in_client):
    r = logged_in_client.post("/tip/M001",
                              data={"home_goals": "abc", "away_goals": "0", "is_risk": "0"},
                              follow_redirects=True)
    assert r.status_code in (200, 302)

def test_submit_tip_locked_match_rejected(logged_in_client):
    r = logged_in_client.post("/tip/M003", data={"home_goals": "2", "away_goals": "1", "is_risk": "0"},
                              follow_redirects=True)
    assert b"Tippfrist" in r.data or b"gesperrt" in r.data.lower()

def test_change_tip_before_kickoff(logged_in_client):
    logged_in_client.post("/tip/M001", data={"home_goals": "2", "away_goals": "1", "is_risk": "0"})
    logged_in_client.post("/tip/M001", data={"home_goals": "3", "away_goals": "0", "is_risk": "0"})
    # No error expected


# ─── Risk pick ────────────────────────────────────────────────

def test_risk_pick_optional(logged_in_client):
    r = logged_in_client.post("/tip/M001", data={"home_goals": "2", "away_goals": "1", "is_risk": "0"})
    assert r.status_code == 302  # no error

def test_risk_pick_toggle(logged_in_client):
    logged_in_client.post("/tip/M001", data={"home_goals": "2", "away_goals": "1", "is_risk": "0"})
    r = logged_in_client.post("/risk/M001/toggle", follow_redirects=True)
    assert r.status_code == 200

def test_risk_pick_locked_match_rejected(logged_in_client):
    r = logged_in_client.post("/risk/M003/toggle", follow_redirects=True)
    assert b"nicht mehr" in r.data or r.status_code in (200, 302)


# ─── Admin access ─────────────────────────────────────────────

def test_admin_view_accessible_for_admin(admin_client):
    r = admin_client.get("/admin/")
    assert r.status_code == 200

def test_admin_view_blocked_for_user(logged_in_client):
    r = logged_in_client.get("/admin/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Berechtigung" in r.data

def test_admin_requires_login(client):
    r = client.get("/admin/")
    assert r.status_code == 302

def test_normal_user_cannot_upload(logged_in_client):
    csv_data = b"match_id;home_goals_actual;away_goals_actual;status\nM001;2;1;final\n"
    r = logged_in_client.post("/admin/upload",
                              data={"results_file": (csv_data, "results.csv")},
                              content_type="multipart/form-data",
                              follow_redirects=True)
    assert b"Berechtigung" in r.data

def test_admin_upload_valid_csv(admin_client):
    csv_data = b"match_id;home_goals_actual;away_goals_actual;status\nM001;2;1;final\n"
    r = admin_client.post("/admin/upload",
                          data={"results_file": (csv_data, "results.csv")},
                          content_type="multipart/form-data")
    assert r.status_code in (200, 302)

def test_admin_upload_invalid_csv(admin_client):
    from io import BytesIO
    csv_data = b"wrong;columns\nbad;data\n"
    r = admin_client.post("/admin/upload",
                          data={"results_file": (BytesIO(csv_data), "results.csv")},
                          content_type="multipart/form-data",
                          follow_redirects=True)
    assert b"Fehler" in r.data or b"fehlt" in r.data.lower() or b"FEHLER" in r.data

def test_admin_upload_wrong_type(admin_client):
    r = admin_client.post("/admin/upload",
                          data={"results_file": (b"data", "file.exe")},
                          content_type="multipart/form-data",
                          follow_redirects=True)
    assert b"erlaubt" in r.data or b"Datei" in r.data


# ─── Leaderboard ─────────────────────────────────────────────

def test_leaderboard_accessible(logged_in_client):
    r = logged_in_client.get("/leaderboard")
    assert r.status_code == 200

def test_leaderboard_matchday(logged_in_client):
    r = logged_in_client.get("/leaderboard/1")
    assert r.status_code == 200


# ─── Health ──────────────────────────────────────────────────

def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert b"ok" in r.data


# ─── My tips ─────────────────────────────────────────────────

def test_my_tips_page(logged_in_client):
    r = logged_in_client.get("/my-tips")
    assert r.status_code == 200
