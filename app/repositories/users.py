from pathlib import Path
from app.repositories.base import read_lines, atomic_write_text
from filelock import FileLock

HEADERS = "username;password_hash;role;display_name;active;paid"


class UserRepository:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "users.txt"
        self._lock = FileLock(str(self._path) + ".lock")

    def _parse_line(self, line: str) -> dict | None:
        parts = line.split(";")
        if len(parts) < 5:
            return None
        return {
            "username": parts[0].strip(),
            "password_hash": parts[1].strip(),
            "role": parts[2].strip(),
            "display_name": parts[3].strip(),
            "active": parts[4].strip() == "1",
            "paid": parts[5].strip() == "1" if len(parts) > 5 else False,
        }

    def all(self) -> list[dict]:
        lines = read_lines(self._path)
        result = []
        for line in lines:
            if line.startswith("username;") or line.startswith("#"):
                continue
            user = self._parse_line(line)
            if user:
                result.append(user)
        return result

    def find_by_username(self, username: str) -> dict | None:
        for user in self.all():
            if user["username"].lower() == username.lower():
                return user
        return None

    def save(self, user: dict) -> None:
        """Insert or update a user."""
        with self._lock:
            lines = read_lines(self._path)
            header_written = any(l.startswith("username;") for l in lines)

            new_line = ";".join([
                user["username"],
                user["password_hash"],
                user.get("role", "user"),
                user.get("display_name", user["username"]),
                "1" if user.get("active", True) else "0",
                "1" if user.get("paid", False) else "0",
            ])

            # Replace existing or append
            updated = False
            out_lines = []
            for line in lines:
                if line.startswith("username;"):
                    out_lines.append(HEADERS)
                    continue
                u = self._parse_line(line)
                if u and u["username"].lower() == user["username"].lower():
                    out_lines.append(new_line)
                    updated = True
                else:
                    out_lines.append(line)

            if not header_written:
                out_lines.insert(0, HEADERS)
            if not updated:
                out_lines.append(new_line)

            atomic_write_text(self._path, "\n".join(out_lines) + "\n")
