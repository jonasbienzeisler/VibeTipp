from datetime import datetime, timezone
from pathlib import Path
from app.repositories.base import read_csv, ensure_csv_exists

HEADERS = ["match_id", "matchday", "kickoff_at", "home_team", "away_team", "is_germany_game"]


class MatchRepository:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "matches.csv"
        ensure_csv_exists(self._path, HEADERS)
        self._cache: list[dict] | None = None
        self._cache_mtime = None

    def _parse(self, row: dict) -> dict:
        try:
            kickoff = datetime.fromisoformat(row["kickoff_at"])
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            kickoff = None
        return {
            "match_id": row["match_id"],
            "matchday": int(row.get("matchday", 0)),
            "kickoff_at": kickoff,
            "kickoff_str": row.get("kickoff_at", ""),
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "is_germany_game": row.get("is_germany_game", "0") == "1",
        }

    def all(self) -> list[dict]:
        # matches.csv changes rarely (team-name edits / import). Cache the parsed +
        # sorted result and invalidate automatically when the file's mtime changes.
        # Safe because production runs a single process (Flask built-in server).
        try:
            mtime = self._path.stat().st_mtime_ns
        except OSError:
            mtime = None
        if self._cache is not None and self._cache_mtime == mtime:
            return self._cache
        rows = read_csv(self._path)
        matches = [self._parse(r) for r in rows if r.get("match_id")]
        matches.sort(key=lambda m: (m["matchday"], m["kickoff_at"] or datetime.max.replace(tzinfo=timezone.utc)))
        self._cache = matches
        self._cache_mtime = mtime
        return matches

    def find(self, match_id: str) -> dict | None:
        for m in self.all():
            if m["match_id"] == match_id:
                return m
        return None

    def matchdays(self) -> list[int]:
        return sorted({m["matchday"] for m in self.all()})

    def by_matchday(self, matchday: int) -> list[dict]:
        return [m for m in self.all() if m["matchday"] == matchday]

    def is_locked(self, match: dict) -> bool:
        """Per-match lock check (used for scoring/leaderboard)."""
        if not match["kickoff_at"]:
            return False
        return datetime.now(timezone.utc) >= match["kickoff_at"]

    def is_matchday_locked(self, matchday: int) -> bool:
        """Matchday is locked when the first kickoff of that matchday has passed."""
        matches = self.by_matchday(matchday)
        kickoffs = [m["kickoff_at"] for m in matches if m["kickoff_at"]]
        if not kickoffs:
            return False
        return datetime.now(timezone.utc) >= min(kickoffs)

    def current_matchday(self) -> int:
        """First unlocked matchday, or last matchday if all are locked."""
        matchdays = self.matchdays()
        for md in matchdays:
            if not self.is_matchday_locked(md):
                return md
        return matchdays[-1] if matchdays else 1

    def autofix_germany_flags(self) -> int:
        """Set is_germany_game=1 exactly when a team is 'Deutschland', else 0.

        Safe and fully derivable from team names. Returns the number of rows changed.
        """
        from app.repositories.base import read_csv, write_csv
        rows = read_csv(self._path)
        changed = 0
        for row in rows:
            want = "1" if "Deutschland" in (row.get("home_team", ""), row.get("away_team", "")) else "0"
            if row.get("is_germany_game", "0") != want:
                row["is_germany_game"] = want
                changed += 1
        if changed:
            write_csv(self._path, HEADERS, rows)
            self._cache = None
        return changed

    def update_team_names(self, match_id: str, home_team: str = None, away_team: str = None) -> None:
        """Update home_team and/or away_team for a match in matches.csv (atomic write)."""
        from app.repositories.base import read_csv, write_csv
        rows = read_csv(self._path)
        for row in rows:
            if row.get("match_id") == match_id:
                if home_team is not None:
                    row["home_team"] = home_team
                if away_team is not None:
                    row["away_team"] = away_team
                break
        write_csv(self._path, HEADERS, rows)
