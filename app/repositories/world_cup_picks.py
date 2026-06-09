from pathlib import Path
from datetime import datetime, timezone
from app.repositories.base import read_csv, write_csv, ensure_csv_exists

HEADERS = ["username", "team", "timestamp"]


class WorldCupPicksRepository:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "world_cup_picks.csv"
        ensure_csv_exists(self._path, HEADERS)

    def all(self) -> list[dict]:
        return read_csv(self._path)

    def get_pick(self, username: str) -> str | None:
        for row in self.all():
            if row["username"].lower() == username.lower():
                return row["team"]
        return None

    def save_pick(self, username: str, team: str) -> None:
        rows = self.all()
        rows = [r for r in rows if r["username"].lower() != username.lower()]
        rows.append({
            "username": username,
            "team": team,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        write_csv(self._path, HEADERS, rows)
