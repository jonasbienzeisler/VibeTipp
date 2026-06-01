"""Shared test fixtures."""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from app import create_app
from app.auth.hashing import hash_password


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def app_with_data(tmp_dir):
    """Flask test app with pre-populated data."""
    future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    # Write users
    admin_hash = hash_password("admin123")
    user_hash = hash_password("user123")
    (tmp_dir / "users.txt").write_text(
        f"username;password_hash;role;display_name;active\n"
        f"admin;{admin_hash};admin;Admin;1\n"
        f"testuser;{user_hash};user;Test User;1\n"
        f"inactive;{user_hash};user;Inactive;0\n",
        encoding="utf-8"
    )

    # Write matches
    # M001/M002 on matchday 1 (future kickoffs → matchday 1 unlocked)
    # M003 on matchday 2 (past kickoff → matchday 2 locked)
    (tmp_dir / "matches.csv").write_text(
        "match_id;matchday;kickoff_at;home_team;away_team;is_germany_game\n"
        f"M001;1;{future};Deutschland;Frankreich;1\n"
        f"M002;1;{future};Spanien;Italien;0\n"
        f"M003;2;{past};England;Portugal;0\n",
        encoding="utf-8"
    )

    app = create_app(data_dir=tmp_dir, secret_key="test-secret")
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    yield app


@pytest.fixture
def client(app_with_data):
    return app_with_data.test_client()


@pytest.fixture
def logged_in_client(client):
    client.post("/login", data={"username": "testuser", "password": "user123"})
    return client


@pytest.fixture
def admin_client(client):
    client.post("/login", data={"username": "admin", "password": "admin123"})
    return client
