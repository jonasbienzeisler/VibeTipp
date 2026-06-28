"""Tests for the admin data-file editor: validation, safe save, health checks."""
from app.admin import data_editor as de

MH = "match_id;matchday;kickoff_at;home_team;away_team;is_germany_game"
RH = "match_id;home_goals_actual;away_goals_actual;status"


def _matches(*rows):
    return MH + "\n" + "\n".join(rows) + "\n"


# ─────────────────────────── matches validation ───────────────────────────

def test_valid_matches_passes():
    content = _matches("M001;1;2026-07-04T22:00:00+02:00;Deutschland;Japan;1")
    errors, warnings = de.validate_matches(content)
    assert errors == []


def test_renamed_header_is_error():
    content = "match_id;matchday;kickoff;home_team;away_team;is_germany_game\nM001;1;2026-07-04T22:00:00+02:00;A;B;0\n"
    errors, _ = de.validate_matches(content)
    assert errors and "Kopfzeile" in errors[0]


def test_wrong_column_count_is_error():
    content = _matches("M001;1;2026-07-04T22:00:00+02:00;A;B")  # missing flag column
    errors, _ = de.validate_matches(content)
    assert any("Spalten" in e for e in errors)


def test_bad_date_is_error():
    content = _matches("M001;1;not-a-date;A;B;0")
    errors, _ = de.validate_matches(content)
    assert any("kickoff_at" in e for e in errors)


def test_bad_germany_flag_is_error():
    content = _matches("M001;1;2026-07-04T22:00:00+02:00;A;B;5")
    errors, _ = de.validate_matches(content)
    assert any("is_germany_game" in e for e in errors)


def test_duplicate_match_id_is_error():
    content = _matches(
        "M001;1;2026-07-04T22:00:00+02:00;A;B;0",
        "M001;1;2026-07-05T22:00:00+02:00;C;D;0",
    )
    errors, _ = de.validate_matches(content)
    assert any("doppelte" in e for e in errors)


def test_germany_flag_mismatch_is_warning_not_error():
    content = _matches("M001;1;2026-07-04T22:00:00+02:00;Deutschland;Japan;0")
    errors, warnings = de.validate_matches(content)
    assert errors == []
    assert any("Deutschland-Spiel" in w for w in warnings)


def test_early_date_is_warning():
    content = _matches("M001;1;2026-05-31T21:00:00+02:00;A;B;0")
    errors, warnings = de.validate_matches(content)
    assert errors == []
    assert any("Turnierstart" in w for w in warnings)


# ─────────────────────────── results validation ───────────────────────────

def test_valid_results_passes():
    content = RH + "\nM001;2;1;final\n"
    errors, _ = de.validate_results(content)
    assert errors == []


def test_bad_status_is_error():
    content = RH + "\nM001;2;1;bogus\n"
    errors, _ = de.validate_results(content)
    assert any("Status" in e for e in errors)


def test_non_int_goals_on_final_is_error():
    content = RH + "\nM001;x;1;final\n"
    errors, _ = de.validate_results(content)
    assert any("home_goals_actual" in e for e in errors)


# ─────────────────────────── safe save ───────────────────────────

def test_save_rejects_invalid_without_writing(tmp_path):
    (tmp_path / "matches.csv").write_text(_matches("M001;1;2026-07-04T22:00:00+02:00;A;B;0"), encoding="utf-8")
    ok, errors, _, backup = de.save_file_content(tmp_path, "matches", "GARBAGE\n")
    assert ok is False
    assert errors
    assert backup is None
    # original untouched
    assert "M001" in (tmp_path / "matches.csv").read_text(encoding="utf-8")


def test_save_writes_and_backs_up(tmp_path):
    orig = _matches("M001;1;2026-07-04T22:00:00+02:00;A;B;0")
    (tmp_path / "matches.csv").write_text(orig, encoding="utf-8")
    new = _matches("M001;1;2026-07-04T22:00:00+02:00;Deutschland;Japan;1")
    ok, errors, warnings, backup = de.save_file_content(tmp_path, "matches", new)
    assert ok is True
    assert backup is not None
    assert (tmp_path / backup).exists()
    assert "Deutschland" in (tmp_path / "matches.csv").read_text(encoding="utf-8")


# ─────────────────────────── health checks & autofix (via app) ───────────────────────────

def test_health_flags_germany_and_writes_via_autofix(app_with_data, tmp_dir):
    # Rewrite a Deutschland match with the flag wrongly set to 0.
    (tmp_dir / "matches.csv").write_text(
        _matches(
            "M001;1;2026-07-04T22:00:00+02:00;Deutschland;Frankreich;0",
            "M002;1;2026-07-05T22:00:00+02:00;Spanien;Italien;0",
        ),
        encoding="utf-8",
    )
    mr, rr = app_with_data.match_repo, app_with_data.result_repo
    mr._cache = None
    issues = de.run_health_checks(mr, rr)
    assert any(i["code"] == "germany_flag_missing" for i in issues)

    changed = mr.autofix_germany_flags()
    assert changed == 1
    assert mr.find("M001")["is_germany_game"] is True
    assert mr.find("M002")["is_germany_game"] is False


# ─────────────────────────── routes ───────────────────────────

def test_raw_requires_admin(logged_in_client):
    r = logged_in_client.get("/admin/data/matches/raw")
    # non-admin is redirected away from admin routes
    assert r.status_code in (302, 403)


def test_raw_returns_content_and_guidance(admin_client):
    r = admin_client.get("/admin/data/matches/raw")
    assert r.status_code == 200
    j = r.get_json()
    assert j["filename"] == "matches.csv"
    assert len(j["guidance"]) > 0
    assert "match_id" in j["content"]


def test_save_invalid_returns_422(admin_client):
    r = admin_client.post("/admin/data/matches", data={"content": "BAD\n"})
    assert r.status_code == 422
    assert r.get_json()["ok"] is False


def test_unknown_file_404(admin_client):
    assert admin_client.get("/admin/data/nope/raw").status_code == 404
