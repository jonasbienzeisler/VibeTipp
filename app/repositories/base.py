import os
import tempfile
from pathlib import Path
from filelock import FileLock


def atomic_write_text(path: Path, content: str) -> None:
    """Write content to path atomically (temp file + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_line(path: Path, line: str) -> None:
    """Append a line to a file with file locking."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock")
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")


def read_lines(path: Path) -> list[str]:
    """Read all non-empty lines from a file."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f if line.strip()]


def read_csv(path: Path, delimiter: str = ";") -> list[dict]:
    """Read CSV with header row into list of dicts."""
    lines = read_lines(path)
    if not lines:
        return []
    headers = [h.strip() for h in lines[0].split(delimiter)]
    rows = []
    for line in lines[1:]:
        if line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(delimiter)]
        if len(parts) < len(headers):
            parts += [""] * (len(headers) - len(parts))
        rows.append(dict(zip(headers, parts)))
    return rows


def write_csv(path: Path, headers: list[str], rows: list[dict], delimiter: str = ";") -> None:
    """Write CSV file atomically with file locking."""
    lock = FileLock(str(path) + ".lock")
    with lock:
        lines = [delimiter.join(headers)]
        for row in rows:
            lines.append(delimiter.join(str(row.get(h, "")) for h in headers))
        atomic_write_text(path, "\n".join(lines) + "\n")


def ensure_csv_exists(path: Path, headers: list[str], delimiter: str = ";") -> None:
    """Create CSV with headers if file doesn't exist."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, delimiter.join(headers) + "\n")
