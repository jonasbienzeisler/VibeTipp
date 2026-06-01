from datetime import datetime, timezone
from pathlib import Path
from app.repositories.base import read_csv, write_csv, ensure_csv_exists

HEADERS = ["match_id", "frozen_at", "home_win_share", "draw_share", "away_win_share", "total_tips"]


class SnapshotRepository:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "rarity_snapshots.csv"
        ensure_csv_exists(self._path, HEADERS)

    def _parse(self, row: dict) -> dict | None:
        try:
            return {
                "match_id": row["match_id"],
                "frozen_at": row.get("frozen_at", ""),
                "home_win_share": float(row.get("home_win_share", 0)),
                "draw_share": float(row.get("draw_share", 0)),
                "away_win_share": float(row.get("away_win_share", 0)),
                "total_tips": int(row.get("total_tips", 0)),
            }
        except (ValueError, KeyError):
            return None

    def get(self, match_id: str) -> dict | None:
        for row in read_csv(self._path):
            if row.get("match_id") == match_id:
                return self._parse(row)
        return None

    def save(self, snapshot: dict) -> None:
        existing = {r["match_id"]: r for r in (self._parse(row) for row in read_csv(self._path)) if r}
        existing[snapshot["match_id"]] = snapshot
        write_csv(self._path, HEADERS, list(existing.values()))

    def get_or_create(self, match_id: str, kickoff_at: datetime, tip_repo) -> dict:
        """Get existing snapshot or create from tips before kickoff."""
        snap = self.get(match_id)
        if snap:
            return snap

        tips = tip_repo.effective_tips_for_match_before(match_id, kickoff_at)
        total = len(tips)

        if total == 0:
            snap = {
                "match_id": match_id,
                "frozen_at": kickoff_at.isoformat(),
                "home_win_share": 0.0,
                "draw_share": 0.0,
                "away_win_share": 0.0,
                "total_tips": 0,
            }
        else:
            from app.scoring.engine import get_tendency, Tendency
            home_c = sum(1 for t in tips if get_tendency(t["home_goals_tip"], t["away_goals_tip"]) == Tendency.HOME)
            draw_c = sum(1 for t in tips if get_tendency(t["home_goals_tip"], t["away_goals_tip"]) == Tendency.DRAW)
            away_c = sum(1 for t in tips if get_tendency(t["home_goals_tip"], t["away_goals_tip"]) == Tendency.AWAY)
            snap = {
                "match_id": match_id,
                "frozen_at": kickoff_at.isoformat(),
                "home_win_share": round(home_c / total, 4),
                "draw_share": round(draw_c / total, 4),
                "away_win_share": round(away_c / total, 4),
                "total_tips": total,
            }

        self.save(snap)
        return snap

    def compute_live(self, match_id: str, tip_repo) -> dict:
        """Compute live rarity distribution from current tips (before kickoff)."""
        tips = tip_repo.effective_tips_for_match(match_id)
        total = len(tips)
        if total == 0:
            return {"home_win_share": 0.0, "draw_share": 0.0, "away_win_share": 0.0, "total_tips": 0}

        from app.scoring.engine import get_tendency, Tendency
        home_c = sum(1 for t in tips if get_tendency(t["home_goals_tip"], t["away_goals_tip"]) == Tendency.HOME)
        draw_c = sum(1 for t in tips if get_tendency(t["home_goals_tip"], t["away_goals_tip"]) == Tendency.DRAW)
        away_c = sum(1 for t in tips if get_tendency(t["home_goals_tip"], t["away_goals_tip"]) == Tendency.AWAY)
        return {
            "home_win_share": round(home_c / total, 4),
            "draw_share": round(draw_c / total, 4),
            "away_win_share": round(away_c / total, 4),
            "total_tips": total,
        }
