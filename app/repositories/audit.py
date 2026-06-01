from datetime import datetime, timezone
from pathlib import Path
from app.repositories.base import append_line


class AuditLog:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "audit.log"

    def log(self, event: str, username: str | None = None, details: str = "", ip: str = "") -> None:
        ts = datetime.now(timezone.utc).isoformat()
        user_part = f" user={username}" if username else ""
        ip_part = f" ip={ip}" if ip else ""
        detail_part = f" {details}" if details else ""
        append_line(self._path, f"[{ts}] {event}{user_part}{ip_part}{detail_part}")

    def login_ok(self, username: str, ip: str) -> None:
        self.log("LOGIN_OK", username, ip=ip)

    def login_fail(self, username: str, ip: str) -> None:
        self.log("LOGIN_FAIL", username, ip=ip)

    def logout(self, username: str, ip: str) -> None:
        self.log("LOGOUT", username, ip=ip)

    def tip_saved(self, username: str, match_id: str, home: int, away: int, risk: bool) -> None:
        self.log("TIP_SAVED", username, f"match={match_id} {home}:{away} risk={int(risk)}")

    def risk_changed(self, username: str, match_id: str, active: bool) -> None:
        self.log("RISK_CHANGED", username, f"match={match_id} active={int(active)}")

    def result_upload(self, username: str, filename: str) -> None:
        self.log("RESULT_UPLOAD", username, f"file={filename}")

    def result_import(self, username: str, count: int) -> None:
        self.log("RESULT_IMPORT", username, f"rows={count}")

    def import_failed(self, username: str, reason: str) -> None:
        self.log("IMPORT_FAILED", username, f"reason={reason}")

    def admin_action(self, username: str, action: str) -> None:
        self.log("ADMIN_ACTION", username, f"action={action}")
