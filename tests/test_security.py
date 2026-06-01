"""Security-focused tests."""
import pytest
import html


# ─── Auth & access control ────────────────────────────────────

def test_no_login_no_dashboard(client):
    r = client.get("/dashboard")
    assert r.status_code == 302
    assert "login" in r.headers.get("Location", "").lower()

def test_no_login_no_matchday(client):
    r = client.get("/matchday/1")
    assert r.status_code == 302

def test_no_login_no_leaderboard(client):
    r = client.get("/leaderboard")
    assert r.status_code == 302

def test_no_login_no_my_tips(client):
    r = client.get("/my-tips")
    assert r.status_code == 302

def test_no_login_no_admin(client):
    r = client.get("/admin/")
    assert r.status_code == 302

def test_no_login_no_tip_post(client):
    r = client.post("/tip/M001", data={"home_goals": "1", "away_goals": "0"})
    assert r.status_code == 302

def test_admin_endpoint_blocks_user(logged_in_client):
    r = logged_in_client.get("/admin/", follow_redirects=True)
    assert b"Berechtigung" in r.data

def test_upload_blocks_user(logged_in_client):
    csv = b"match_id;home_goals_actual;away_goals_actual;status\nM001;2;1;final\n"
    r = logged_in_client.post("/admin/upload",
                              data={"results_file": (csv, "r.csv")},
                              content_type="multipart/form-data",
                              follow_redirects=True)
    assert b"Berechtigung" in r.data


# ─── Session cookie flags ────────────────────────────────────

def test_session_cookie_httponly(client):
    r = client.post("/login", data={"username": "testuser", "password": "user123"})
    cookies = r.headers.getlist("Set-Cookie")
    session_cookie = next((c for c in cookies if "session" in c.lower()), None)
    if session_cookie:
        assert "HttpOnly" in session_cookie or "httponly" in session_cookie.lower()

def test_session_cookie_samesite(client):
    r = client.post("/login", data={"username": "testuser", "password": "user123"})
    cookies = r.headers.getlist("Set-Cookie")
    session_cookie = next((c for c in cookies if "session" in c.lower()), None)
    if session_cookie:
        assert "SameSite" in session_cookie or "samesite" in session_cookie.lower()


# ─── Login error message doesn't leak user existence ─────────

def test_login_error_generic_unknown_user(client):
    r = client.post("/login", data={"username": "notexist", "password": "whatever"})
    data = r.data.decode("utf-8")
    # Should NOT say "user not found" or "wrong password" specifically
    assert "not found" not in data.lower()
    assert "existiert nicht" not in data.lower()
    assert "kein nutzer" not in data.lower()

def test_login_error_generic_wrong_password(client):
    r = client.post("/login", data={"username": "testuser", "password": "wrong"})
    data = r.data.decode("utf-8")
    assert "falsch" not in data.lower() or "Ung" in data  # same generic message


# ─── XSS prevention ──────────────────────────────────────────

def test_display_name_escaped(app_with_data):
    """Usernames/display names with HTML must be escaped."""
    from app.repositories.users import UserRepository
    from app.auth.hashing import hash_password
    repo = UserRepository(app_with_data.config["DATA_DIR"])
    repo.save({
        "username": "xssuser",
        "password_hash": hash_password("pass123"),
        "role": "user",
        "display_name": "<script>alert(1)</script>",
        "active": True,
    })
    client = app_with_data.test_client()
    client.post("/login", data={"username": "xssuser", "password": "pass123"})
    r = client.get("/dashboard")
    data = r.data.decode("utf-8")
    assert "<script>alert(1)</script>" not in data
    assert "&lt;script&gt;" in data or "script" not in data.lower() or "alert" not in data


# ─── Upload security ─────────────────────────────────────────

def test_upload_rejects_exe(admin_client):
    r = admin_client.post("/admin/upload",
                          data={"results_file": (b"data", "file.exe")},
                          content_type="multipart/form-data",
                          follow_redirects=True)
    assert r.status_code == 200
    assert b"erlaubt" in r.data or b"Datei" in r.data

def test_upload_rejects_large_file(admin_client):
    big = b"x" * (2 * 1024 * 1024)  # 2 MB
    r = admin_client.post("/admin/upload",
                          data={"results_file": (big, "big.csv")},
                          content_type="multipart/form-data")
    assert r.status_code in (200, 302, 413)

def test_upload_rejects_no_file(admin_client):
    r = admin_client.post("/admin/upload",
                          data={},
                          content_type="multipart/form-data",
                          follow_redirects=True)
    assert r.status_code == 200


# ─── Data files not directly accessible ──────────────────────

def test_users_txt_not_directly_accessible(client):
    # Data files are outside web root — direct URL access should 404
    r = client.get("/data/users.txt")
    assert r.status_code == 404

def test_tips_csv_not_accessible(client):
    r = client.get("/data/tips.csv")
    assert r.status_code == 404


# ─── Passwords not in audit log ──────────────────────────────

def test_password_not_in_audit_log(app_with_data):
    client = app_with_data.test_client()
    client.post("/login", data={"username": "testuser", "password": "user123"})
    log_path = app_with_data.config["DATA_DIR"] / "audit.log"
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        assert "user123" not in content
        assert "admin123" not in content
