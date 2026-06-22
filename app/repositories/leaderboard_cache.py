import json
from pathlib import Path
from app.repositories.base import atomic_write_text


class LeaderboardCache:
    """Materialized highscore payload.

    The full leaderboard (GESAMT table + per-matchday point tables) is expensive
    to compute from the raw CSVs on every page load. Instead we precompute it once
    whenever points can change (admin score entry, import, manual adjustment, WM
    awards, or the explicit "Punkte berechnen" button) and serialize the result to
    a single JSON file. The highscore view then just loads this file.

    The file is fully derived from the CSVs and can be deleted at any time — the
    route regenerates it on a cache miss (self-healing cold start).
    """

    def __init__(self, data_dir: Path):
        self._path = data_dir / "leaderboard_cache.json"

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None

    def save(self, payload: dict) -> None:
        atomic_write_text(self._path, json.dumps(payload, ensure_ascii=False))

    def regenerate(self) -> dict:
        """Recompute the payload from current data and persist it. Must run inside
        a Flask app context (uses current_app repositories)."""
        from app.routes.main import build_leaderboard_payload
        payload = build_leaderboard_payload()
        self.save(payload)
        return payload
