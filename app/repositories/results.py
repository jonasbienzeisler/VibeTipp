from pathlib import Path
from app.repositories.base import read_csv, write_csv, ensure_csv_exists

HEADERS = ["match_id", "home_goals_actual", "away_goals_actual", "status"]
VALID_STATUSES = {"scheduled", "locked", "final", "cancelled"}


class ResultRepository:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "results.csv"
        ensure_csv_exists(self._path, HEADERS)

    def _parse(self, row: dict) -> dict | None:
        try:
            return {
                "match_id": row["match_id"],
                "home_goals_actual": int(row["home_goals_actual"]) if row.get("home_goals_actual") else None,
                "away_goals_actual": int(row["away_goals_actual"]) if row.get("away_goals_actual") else None,
                "status": row.get("status", "scheduled"),
            }
        except (ValueError, KeyError):
            return None

    def all(self) -> list[dict]:
        return [r for r in (self._parse(row) for row in read_csv(self._path)) if r]

    def all_by_id(self) -> dict[str, dict]:
        """Read results.csv once; return {match_id: result}. Use for bulk lookups."""
        return {r["match_id"]: r for r in self.all()}

    def find(self, match_id: str) -> dict | None:
        for r in self.all():
            if r["match_id"] == match_id:
                return r
        return None

    def upsert(self, result: dict) -> None:
        existing = self.all()
        updated = False
        new_rows = []
        for r in existing:
            if r["match_id"] == result["match_id"]:
                new_rows.append(result)
                updated = True
            else:
                new_rows.append(r)
        if not updated:
            new_rows.append(result)
        write_csv(self._path, HEADERS, new_rows)

    def import_results(self, results: list[dict]) -> None:
        """Replace all results with a new set."""
        existing = {r["match_id"]: r for r in self.all()}
        for r in results:
            existing[r["match_id"]] = r
        write_csv(self._path, HEADERS, list(existing.values()))

    def validate_row(self, row: dict) -> list[str]:
        """Returns list of error messages for a result row."""
        errors = []
        if not row.get("match_id"):
            errors.append("match_id fehlt")
        if row.get("status") not in VALID_STATUSES:
            errors.append(f"Ungültiger Status '{row.get('status')}' (erlaubt: {', '.join(VALID_STATUSES)})")
        if row.get("status") == "final":
            for field in ("home_goals_actual", "away_goals_actual"):
                val = row.get(field, "")
                try:
                    n = int(val)
                    if n < 0:
                        errors.append(f"{field} darf nicht negativ sein")
                except (ValueError, TypeError):
                    errors.append(f"{field} muss eine Ganzzahl sein")
        return errors
