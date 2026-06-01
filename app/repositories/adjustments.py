from pathlib import Path
from datetime import datetime, timezone
from app.repositories.base import read_csv, write_csv, ensure_csv_exists

HEADERS = ["username", "delta", "note", "created_at"]


class AdjustmentsRepository:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "adjustments.csv"
        ensure_csv_exists(self._path, HEADERS)

    def all(self) -> list[dict]:
        rows = read_csv(self._path)
        result = []
        for row in rows:
            try:
                result.append({
                    "username": row["username"],
                    "delta": float(row["delta"]),
                    "note": row.get("note", ""),
                    "created_at": row.get("created_at", ""),
                })
            except (ValueError, KeyError):
                pass
        return result

    def get_user_delta(self, username: str) -> float:
        return sum(r["delta"] for r in self.all() if r["username"].lower() == username.lower())

    def add(self, username: str, delta: float, note: str = "") -> None:
        rows = self.all()
        rows.append({
            "username": username,
            "delta": delta,
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        write_csv(self._path, HEADERS, rows)
