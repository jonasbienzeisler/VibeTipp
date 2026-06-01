"""Unit tests for file repositories."""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from app.repositories.users import UserRepository
from app.repositories.matches import MatchRepository
from app.repositories.tips import TipRepository
from app.repositories.results import ResultRepository
from app.repositories.snapshots import SnapshotRepository
from app.auth.hashing import hash_password, verify_password


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ─── Users ────────────────────────────────────────────────────

def test_users_empty_on_new_file(tmp_dir):
    repo = UserRepository(tmp_dir)
    assert repo.all() == []

def test_save_and_find_user(tmp_dir):
    repo = UserRepository(tmp_dir)
    pw_hash = hash_password("secret123")
    repo.save({"username": "alice", "password_hash": pw_hash, "role": "user", "display_name": "Alice", "active": True})
    user = repo.find_by_username("alice")
    assert user is not None
    assert user["display_name"] == "Alice"
    assert user["role"] == "user"
    assert user["active"] is True

def test_find_by_username_case_insensitive(tmp_dir):
    repo = UserRepository(tmp_dir)
    repo.save({"username": "Bob", "password_hash": "x", "role": "user", "display_name": "Bob", "active": True})
    assert repo.find_by_username("bob") is not None
    assert repo.find_by_username("BOB") is not None

def test_inactive_user_readable(tmp_dir):
    repo = UserRepository(tmp_dir)
    repo.save({"username": "inactive", "password_hash": "x", "role": "user", "display_name": "Inactive", "active": False})
    user = repo.find_by_username("inactive")
    assert user is not None
    assert user["active"] is False

def test_admin_role(tmp_dir):
    repo = UserRepository(tmp_dir)
    repo.save({"username": "admin", "password_hash": "x", "role": "admin", "display_name": "Admin", "active": True})
    user = repo.find_by_username("admin")
    assert user["role"] == "admin"

def test_update_user(tmp_dir):
    repo = UserRepository(tmp_dir)
    repo.save({"username": "charlie", "password_hash": "x", "role": "user", "display_name": "Charlie", "active": True})
    repo.save({"username": "charlie", "password_hash": "y", "role": "admin", "display_name": "Charlie A", "active": True})
    user = repo.find_by_username("charlie")
    assert user["role"] == "admin"
    assert len(repo.all()) == 1  # no duplicates

def test_password_hash_not_plaintext(tmp_dir):
    repo = UserRepository(tmp_dir)
    repo.save({"username": "secure", "password_hash": hash_password("mypassword"), "role": "user", "display_name": "S", "active": True})
    user = repo.find_by_username("secure")
    assert user["password_hash"] != "mypassword"
    assert verify_password(user["password_hash"], "mypassword") is True


# ─── Matches ──────────────────────────────────────────────────

def test_matches_from_csv(tmp_dir):
    csv = ("match_id;matchday;kickoff_at;home_team;away_team;is_germany_game\n"
           "M001;1;2026-06-15T21:00:00+02:00;Deutschland;Frankreich;1\n"
           "M002;1;2026-06-16T15:00:00+02:00;Spanien;Italien;0\n")
    (tmp_dir / "matches.csv").write_text(csv, encoding="utf-8")
    repo = MatchRepository(tmp_dir)
    matches = repo.all()
    assert len(matches) == 2
    m = repo.find("M001")
    assert m is not None
    assert m["home_team"] == "Deutschland"
    assert m["is_germany_game"] is True

def test_match_not_germany(tmp_dir):
    csv = "match_id;matchday;kickoff_at;home_team;away_team;is_germany_game\nM001;1;2026-06-15T21:00:00+02:00;Spanien;Italien;0\n"
    (tmp_dir / "matches.csv").write_text(csv, encoding="utf-8")
    repo = MatchRepository(tmp_dir)
    assert repo.find("M001")["is_germany_game"] is False

def test_match_sort_by_kickoff(tmp_dir):
    csv = ("match_id;matchday;kickoff_at;home_team;away_team;is_germany_game\n"
           "M002;1;2026-06-16T21:00:00+02:00;Spanien;Italien;0\n"
           "M001;1;2026-06-15T21:00:00+02:00;Deutschland;Frankreich;1\n")
    (tmp_dir / "matches.csv").write_text(csv, encoding="utf-8")
    repo = MatchRepository(tmp_dir)
    matches = repo.all()
    assert matches[0]["match_id"] == "M001"

def test_is_locked_past_kickoff(tmp_dir):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    csv = f"match_id;matchday;kickoff_at;home_team;away_team;is_germany_game\nM001;1;{past};A;B;0\n"
    (tmp_dir / "matches.csv").write_text(csv, encoding="utf-8")
    repo = MatchRepository(tmp_dir)
    m = repo.find("M001")
    assert repo.is_locked(m) is True

def test_is_locked_future_kickoff(tmp_dir):
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    csv = f"match_id;matchday;kickoff_at;home_team;away_team;is_germany_game\nM001;1;{future};A;B;0\n"
    (tmp_dir / "matches.csv").write_text(csv, encoding="utf-8")
    repo = MatchRepository(tmp_dir)
    m = repo.find("M001")
    assert repo.is_locked(m) is False


# ─── Tips ─────────────────────────────────────────────────────

def test_save_and_retrieve_tip(tmp_dir):
    repo = TipRepository(tmp_dir)
    repo.save_tip("alice", "M001", 2, 1, False)
    tip = repo.get_user_tip("alice", "M001")
    assert tip is not None
    assert tip["home_goals_tip"] == 2
    assert tip["away_goals_tip"] == 1
    assert tip["is_risk_pick"] is False

def test_last_tip_wins(tmp_dir):
    repo = TipRepository(tmp_dir)
    repo.save_tip("alice", "M001", 2, 1, False)
    repo.save_tip("alice", "M001", 3, 0, False)
    tip = repo.get_user_tip("alice", "M001")
    assert tip["home_goals_tip"] == 3

def test_risk_pick_saved(tmp_dir):
    repo = TipRepository(tmp_dir)
    repo.save_tip("alice", "M001", 2, 1, True)
    tip = repo.get_user_tip("alice", "M001")
    assert tip["is_risk_pick"] is True

def test_multiple_users_different_tips(tmp_dir):
    repo = TipRepository(tmp_dir)
    repo.save_tip("alice", "M001", 2, 1, False)
    repo.save_tip("bob", "M001", 0, 2, False)
    alice_tip = repo.get_user_tip("alice", "M001")
    bob_tip = repo.get_user_tip("bob", "M001")
    assert alice_tip["home_goals_tip"] == 2
    assert bob_tip["home_goals_tip"] == 0

def test_effective_tips_for_match(tmp_dir):
    repo = TipRepository(tmp_dir)
    repo.save_tip("alice", "M001", 2, 1, False)
    repo.save_tip("bob", "M001", 1, 1, False)
    repo.save_tip("alice", "M001", 3, 0, False)  # supersedes
    tips = repo.effective_tips_for_match("M001")
    assert len(tips) == 2  # alice and bob, alice's latest

def test_tips_before_cutoff(tmp_dir):
    repo = TipRepository(tmp_dir)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    repo.save_tip("alice", "M001", 2, 1, False)
    # All tips are after a very old cutoff
    very_old = datetime.now(timezone.utc) - timedelta(days=365)
    tips = repo.effective_tips_for_match_before("M001", very_old)
    assert tips == []

def test_no_tip_returns_none(tmp_dir):
    repo = TipRepository(tmp_dir)
    assert repo.get_user_tip("nobody", "M001") is None


# ─── Results ──────────────────────────────────────────────────

def test_result_upsert_and_find(tmp_dir):
    repo = ResultRepository(tmp_dir)
    repo.upsert({"match_id": "M001", "home_goals_actual": 2, "away_goals_actual": 1, "status": "final"})
    r = repo.find("M001")
    assert r is not None
    assert r["home_goals_actual"] == 2

def test_result_update(tmp_dir):
    repo = ResultRepository(tmp_dir)
    repo.upsert({"match_id": "M001", "home_goals_actual": 2, "away_goals_actual": 1, "status": "final"})
    repo.upsert({"match_id": "M001", "home_goals_actual": 3, "away_goals_actual": 1, "status": "final"})
    assert repo.find("M001")["home_goals_actual"] == 3

def test_import_results_replaces(tmp_dir):
    repo = ResultRepository(tmp_dir)
    repo.upsert({"match_id": "M001", "home_goals_actual": 1, "away_goals_actual": 0, "status": "final"})
    repo.import_results([
        {"match_id": "M001", "home_goals_actual": 2, "away_goals_actual": 1, "status": "final"},
        {"match_id": "M002", "home_goals_actual": 0, "away_goals_actual": 0, "status": "final"},
    ])
    assert repo.find("M001")["home_goals_actual"] == 2
    assert repo.find("M002") is not None


# ─── Snapshots ────────────────────────────────────────────────

def test_snapshot_save_and_get(tmp_dir):
    repo = SnapshotRepository(tmp_dir)
    snap = {
        "match_id": "M001", "frozen_at": "2026-06-15T21:00:00+00:00",
        "home_win_share": 0.7, "draw_share": 0.2, "away_win_share": 0.1, "total_tips": 10,
    }
    repo.save(snap)
    retrieved = repo.get("M001")
    assert retrieved is not None
    assert retrieved["home_win_share"] == pytest.approx(0.7)

def test_snapshot_none_for_missing(tmp_dir):
    repo = SnapshotRepository(tmp_dir)
    assert repo.get("M999") is None

def test_snapshot_atomic_update(tmp_dir):
    repo = SnapshotRepository(tmp_dir)
    for share in [0.5, 0.7, 0.6]:
        repo.save({"match_id": "M001", "frozen_at": "x", "home_win_share": share,
                   "draw_share": 0.2, "away_win_share": 0.1, "total_tips": 5})
    assert repo.get("M001")["home_win_share"] == pytest.approx(0.6)
