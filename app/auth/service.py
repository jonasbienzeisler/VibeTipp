import time
from collections import defaultdict
from threading import Lock
from app.auth.hashing import verify_password

# In-memory rate limiter (per-IP, resets on restart — fine for small institute)
_attempts: dict = defaultdict(list)  # ip -> [timestamp, ...]
_lock = Lock()


def check_rate_limit(ip: str, max_attempts: int, lockout_minutes: int) -> bool:
    """Returns True if the IP is allowed to attempt login."""
    now = time.time()
    window = lockout_minutes * 60
    with _lock:
        # Remove old entries
        _attempts[ip] = [t for t in _attempts[ip] if now - t < window]
        return len(_attempts[ip]) < max_attempts


def record_failed_attempt(ip: str) -> None:
    with _lock:
        _attempts[ip].append(time.time())


def authenticate(user_repo, username: str, password: str):
    """Returns user dict if valid, None otherwise. Never leaks whether user exists."""
    user = user_repo.find_by_username(username)
    if user is None or not user["active"]:
        # Still run a dummy verify to prevent timing attacks
        verify_password("$argon2id$v=19$m=65536,t=2,p=2$dummysalt12345678$dummyhashvalue123456789012345678901234", password)
        return None
    if not verify_password(user["password_hash"], password):
        return None
    return user
