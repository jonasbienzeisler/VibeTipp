from datetime import datetime, timezone
from pathlib import Path
from filelock import FileLock
from app.repositories.base import read_csv, ensure_csv_exists, atomic_write_text
import uuid

HEADERS = ["tip_id", "timestamp", "username", "match_id", "home_goals_tip", "away_goals_tip", "is_risk_pick"]


class TipRepository:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "tips.csv"
        self._lock = FileLock(str(self._path) + ".lock")
        ensure_csv_exists(self._path, HEADERS)

    def _parse(self, row: dict) -> dict | None:
        try:
            return {
                "tip_id": row["tip_id"],
                "timestamp": datetime.fromisoformat(row["timestamp"]),
                "username": row["username"],
                "match_id": row["match_id"],
                "home_goals_tip": int(row["home_goals_tip"]),
                "away_goals_tip": int(row["away_goals_tip"]),
                "is_risk_pick": row.get("is_risk_pick", "0") == "1",
            }
        except (ValueError, KeyError):
            return None

    def _all_raw(self) -> list[dict]:
        """All tip records including superseded ones."""
        rows = read_csv(self._path)
        result = []
        for r in rows:
            parsed = self._parse(r)
            if parsed:
                result.append(parsed)
        return sorted(result, key=lambda t: t["timestamp"])

    def effective_tips_for_match(self, match_id: str) -> list[dict]:
        """Last tip per user for a given match (current effective tips)."""
        all_tips = [t for t in self._all_raw() if t["match_id"] == match_id]
        user_latest: dict[str, dict] = {}
        for tip in all_tips:
            user_latest[tip["username"]] = tip
        return list(user_latest.values())

    def effective_tips_for_match_before(self, match_id: str, cutoff: datetime) -> list[dict]:
        """Last tip per user for a match, only considering tips submitted before cutoff."""
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        all_tips = [t for t in self._all_raw() if t["match_id"] == match_id]
        before_cutoff = []
        for t in all_tips:
            ts = t["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts <= cutoff:
                before_cutoff.append(t)
        user_latest: dict[str, dict] = {}
        for tip in before_cutoff:
            user_latest[tip["username"]] = tip
        return list(user_latest.values())

    def get_user_tip(self, username: str, match_id: str) -> dict | None:
        """Get the current effective tip for a user/match."""
        all_tips = [t for t in self._all_raw()
                    if t["match_id"] == match_id and t["username"] == username]
        if not all_tips:
            return None
        return all_tips[-1]

    def get_user_risk_pick_for_matchday(self, username: str, matchday: int, match_repo) -> str | None:
        """Returns match_id of current risk pick for user in this matchday, or None."""
        matches = match_repo.by_matchday(matchday)
        match_ids = {m["match_id"] for m in matches}
        for tip in reversed(self._all_raw()):
            if tip["username"] == username and tip["match_id"] in match_ids and tip["is_risk_pick"]:
                # Verify it's still the effective tip
                effective = self.get_user_tip(username, tip["match_id"])
                if effective and effective["is_risk_pick"]:
                    return tip["match_id"]
        return None

    def save_tip(self, username: str, match_id: str, home: int, away: int, is_risk: bool) -> dict:
        """Append a tip row and return it."""
        tip = {
            "tip_id": "T" + uuid.uuid4().hex[:8].upper(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "username": username,
            "match_id": match_id,
            "home_goals_tip": home,
            "away_goals_tip": away,
            "is_risk_pick": is_risk,
        }
        line = ";".join([
            tip["tip_id"],
            tip["timestamp"],
            tip["username"],
            tip["match_id"],
            str(tip["home_goals_tip"]),
            str(tip["away_goals_tip"]),
            "1" if tip["is_risk_pick"] else "0",
        ])
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return tip

    def all_effective_tips(self) -> list[dict]:
        """All current effective tips (last per user/match)."""
        all_tips = self._all_raw()
        seen: dict[tuple, dict] = {}
        for tip in all_tips:
            seen[(tip["username"], tip["match_id"])] = tip
        return list(seen.values())
