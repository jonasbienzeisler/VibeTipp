import csv
import io
import shutil
from datetime import datetime, timezone
from pathlib import Path
from app.repositories.results import VALID_STATUSES


def parse_csv_upload(file_content: bytes) -> tuple[list[dict], list[str]]:
    """Parse uploaded CSV bytes. Returns (rows, errors)."""
    try:
        text = file_content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = file_content.decode("latin-1")
        except UnicodeDecodeError:
            return [], ["Datei konnte nicht dekodiert werden (kein UTF-8 oder Latin-1)"]

    errors = []
    rows = []
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    required_fields = {"match_id", "home_goals_actual", "away_goals_actual", "status"}

    if not reader.fieldnames:
        return [], ["CSV-Datei hat keine Kopfzeile"]

    actual_fields = {f.strip() for f in (reader.fieldnames or [])}
    missing = required_fields - actual_fields
    if missing:
        return [], [f"Fehlende Spalten: {', '.join(sorted(missing))}"]

    for i, raw_row in enumerate(reader, start=2):
        row = {k.strip(): (v.strip() if v else "") for k, v in raw_row.items()}
        row_errors = validate_result_row(row, i)
        if row_errors:
            errors.extend(row_errors)
        else:
            rows.append({
                "match_id": row["match_id"],
                "home_goals_actual": row["home_goals_actual"],
                "away_goals_actual": row["away_goals_actual"],
                "status": row["status"],
            })

    return rows, errors


def validate_result_row(row: dict, line_num: int) -> list[str]:
    errors = []
    prefix = f"Zeile {line_num}: "
    if not row.get("match_id"):
        errors.append(prefix + "match_id fehlt")
    status = row.get("status", "")
    if status not in VALID_STATUSES:
        errors.append(prefix + f"Ungültiger Status '{status}'")
    if status == "final":
        for field in ("home_goals_actual", "away_goals_actual"):
            val = row.get(field, "")
            try:
                n = int(val)
                if n < 0:
                    errors.append(prefix + f"{field} darf nicht negativ sein")
                if n > 50:
                    errors.append(prefix + f"{field} unrealistisch hoch ({n})")
            except (ValueError, TypeError):
                errors.append(prefix + f"{field} muss eine Ganzzahl sein (war: '{val}')")
    return errors


def backup_results(data_dir: Path) -> Path | None:
    """Backup current results.csv before import. Returns backup path."""
    src = data_dir / "results.csv"
    if not src.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = data_dir / f"results_backup_{ts}.csv"
    shutil.copy2(str(src), str(backup))
    return backup


def validate_match_ids(rows: list[dict], match_repo) -> list[str]:
    """Validate that all match_ids in rows exist in match_repo."""
    errors = []
    known_ids = {m["match_id"] for m in match_repo.all()}
    for row in rows:
        if row["match_id"] not in known_ids:
            errors.append(f"Unbekannte match_id: {row['match_id']}")
    return errors
