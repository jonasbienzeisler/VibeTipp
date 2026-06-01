"""Unit tests for input validation logic."""
import pytest
from app.admin.importer import validate_result_row, parse_csv_upload


def make_row(match_id="M001", home="2", away="1", status="final"):
    return {"match_id": match_id, "home_goals_actual": home, "away_goals_actual": away, "status": status}


# ─── Goal validation ──────────────────────────────────────────

def test_valid_row_passes():
    assert validate_result_row(make_row(), 2) == []

def test_negative_home_goals_rejected():
    errors = validate_result_row(make_row(home="-1"), 2)
    assert any("negativ" in e for e in errors)

def test_negative_away_goals_rejected():
    errors = validate_result_row(make_row(away="-1"), 2)
    assert any("negativ" in e for e in errors)

def test_decimal_rejected():
    errors = validate_result_row(make_row(home="1.5"), 2)
    assert any("Ganzzahl" in e for e in errors)

def test_text_rejected():
    errors = validate_result_row(make_row(home="zwei"), 2)
    assert any("Ganzzahl" in e for e in errors)

def test_unrealistic_high_rejected():
    errors = validate_result_row(make_row(home="51"), 2)
    assert any("unrealistisch" in e for e in errors)

def test_zero_valid():
    assert validate_result_row(make_row(home="0", away="0"), 2) == []

def test_missing_match_id():
    errors = validate_result_row(make_row(match_id=""), 2)
    assert any("match_id" in e for e in errors)

def test_invalid_status():
    errors = validate_result_row(make_row(status="unknown"), 2)
    assert any("Status" in e for e in errors)

def test_valid_statuses():
    for s in ("scheduled", "final", "cancelled"):
        row = make_row(status=s)
        if s != "final":
            row["home_goals_actual"] = ""
            row["away_goals_actual"] = ""
        errors = validate_result_row(row, 2)
        assert errors == [], f"Status '{s}' should be valid but got: {errors}"


# ─── CSV upload parsing ───────────────────────────────────────

def test_valid_csv_parses():
    csv = b"match_id;home_goals_actual;away_goals_actual;status\nM001;2;1;final\nM002;0;0;final\n"
    rows, errors = parse_csv_upload(csv)
    assert errors == []
    assert len(rows) == 2
    assert rows[0]["match_id"] == "M001"

def test_missing_column_rejected():
    csv = b"match_id;home_goals_actual;status\nM001;2;final\n"
    rows, errors = parse_csv_upload(csv)
    assert any("away_goals_actual" in e for e in errors)

def test_empty_csv_rejected():
    rows, errors = parse_csv_upload(b"")
    assert errors

def test_invalid_encoding():
    # Feed truly invalid bytes
    rows, errors = parse_csv_upload(b"\xff\xfe" * 100)
    # Should not crash; may return error or empty rows
    assert isinstance(rows, list)
    assert isinstance(errors, list)

def test_header_only_no_rows():
    csv = b"match_id;home_goals_actual;away_goals_actual;status\n"
    rows, errors = parse_csv_upload(csv)
    assert errors == []
    assert rows == []
