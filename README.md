# VibeTipp

A private football betting-pool web app for small groups (10–50 players).
Players submit score predictions before each matchday; points are awarded based
on tendency, exactness, goal-specific bonuses, a rarity multiplier, and an
optional "high-risk" doubling pick per matchday.  
An admin manages results, user accounts, and can resolve bracket team names as
the tournament progresses.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Backend: Text-File Storage](#backend-text-file-storage)
3. [Requirements](#requirements)
4. [Installation (Docker)](#installation-docker)
5. [Environment Variables](#environment-variables)
6. [Ports & Network](#ports--network)
7. [HTTPS](#https)
8. [First-Run Setup Checklist](#first-run-setup-checklist)
9. [Updating](#updating)
10. [Data Backup](#data-backup)
11. [Security Features](#security-features)

---

## Architecture Overview

```
Browser ──HTTP──► Flask (Python 3.11)
                    │
                    ├── app/routes/       # Page routes (main, tips, admin, api)
                    ├── app/repositories/ # File-based data access layer
                    ├── app/scoring/      # Point-calculation engine
                    ├── app/auth/         # Argon2id auth + rate limiting
                    ├── app/static/       # CSS, JS, images (served by Flask)
                    └── app/templates/    # Jinja2 HTML templates
                    │
                    └── /data/            # Docker volume — all persistent state
```

- **No database.** All data lives in delimited text files on disk.
- **No message queue, cache, or external services.** Everything runs in a single
  process. Suitable for small groups; not designed for thousands of concurrent users.
- **Docker-based deployment** via `docker compose`.
- Frontend: server-rendered Jinja2 + minimal vanilla JS + HTMX for dynamic panels.

---

## Backend: Text-File Storage

All files live in the `/data` Docker volume (mapped to `DATA_DIR`).
They are semicolon-delimited CSV files (UTF-8) plus one plain-text log.

| File | Purpose |
|---|---|
| `users.txt` | User accounts — username, argon2id hash, role (`user`/`admin`), display name, active flag, paid flag |
| `matches.csv` | Tournament schedule — match ID, matchday, kickoff (ISO 8601 + TZ), home team, away team, Germany-game flag |
| `results.csv` | Match results entered by admin — match ID, home goals, away goals, status (`scheduled`/`final`) |
| `tips.csv` | Player predictions — tip ID, timestamp, username, match ID, home/away goals tipped, is-risk-pick flag |
| `rarity_snapshots.csv` | Frozen tip-distribution per match at kickoff — used for the rarity multiplier |
| `adjustments.csv` | Manual point corrections by admin — username, delta, note, timestamp |
| `audit.log` | Append-only plain-text log of admin actions (imports, score sets, user creates, adjustments) |
| `player_results/` | Auto-generated per-user point CSVs (rebuilt after every result import; safe to delete) |

**File locking:** All writes use `filelock` + atomic `os.replace()` to prevent
corruption under concurrent requests.

---

## Requirements

| Requirement | Minimum |
|---|---|
| Docker Engine | 24+ |
| Docker Compose | v2 (`docker compose`) |
| RAM | 128 MB (256 MB recommended) |
| Disk | 100 MB image + a few MB for data |
| OS | Linux host with Docker (tested Debian 12 / Ubuntu 22.04) |
| Network | Port 8081 reachable by players, or behind a reverse proxy |

---

## Installation (Docker)

### 1. Clone the repository

```bash
git clone <your-repo-url> vibetipp
cd vibetipp
```

### 2. Generate a secret key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output — you will need it in the next step.

### 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set `SECRET_KEY` to the value you just generated:

```env
SECRET_KEY=paste-your-generated-key-here
```

This key signs all session cookies. **It must be set before going live** — the
default value in `.env.example` is not safe for production.

### 4. Build and start

```bash
docker compose up -d --build
```

The app is now available at `http://<server-ip>:8081`.

> **Note:** The app serves plain HTTP. See [HTTPS](#https) if you need TLS.

### 5. Create the first admin user

```bash
docker exec -it vibetipp python -c "
from app import create_app
from app.auth.hashing import hash_password
app = create_app()
with app.app_context():
    app.user_repo.save({
        'username': 'admin',
        'password_hash': hash_password('CHANGE-THIS-PASSWORD'),
        'role': 'admin',
        'display_name': 'Admin',
        'active': True,
        'paid': True,
    })
    print('Admin user created.')
"
```

Log in at `http://<server-ip>:8081/login` with `admin` / `CHANGE-THIS-PASSWORD`
and change the password immediately via the admin panel.

### 6. Create player accounts

Use **Admin → Nutzer anlegen** in the web UI, or repeat the command above with
`role: 'user'`.

---

## Environment Variables

Set in `.env` (picked up automatically by `docker-compose.yml`).

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Flask session signing key. **Change this.** |
| `DATA_DIR` | `/data` | Persistent data directory inside container |
| `PORT` | `8081` | TCP port the app listens on |
| `SESSION_LIFETIME_HOURS` | `24` | Login session duration |
| `MAX_UPLOAD_SIZE_MB` | `1` | Max size of uploaded result files |
| `MAX_GOALS` | `30` | Validation cap on goals per team |
| `LOGIN_MAX_ATTEMPTS` | `10` | Failed logins before IP lockout |
| `LOGIN_LOCKOUT_MINUTES` | `15` | IP lockout duration |
| `PAYMENT_LINK` | `https://paypal.me/` | Payment link shown to unpaid users |

---

## Ports & Network

| Port | Protocol | Purpose |
|---|---|---|
| `8081` | HTTP/TCP | Web application (configurable via `PORT`) |

Open **port 8081 inbound** on the host firewall for players to reach the app.

The app binds to `0.0.0.0`. On public servers, restrict access via firewall or
put a reverse proxy in front.

---

## HTTPS

**The app serves plain HTTP by default.** For a private group on a trusted LAN
or VPN, this is acceptable. For public internet deployment, add TLS via a
reverse proxy — no code changes required.

### Option A — Caddy (automatic certificates, simplest)

Create `Caddyfile`:

```
yourdomain.com {
    reverse_proxy vibetipp:8081
}
```

Add to `docker-compose.yml`:

```yaml
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    depends_on:
      - vibetipp
```

Add `caddy_data:` under `volumes:` and **remove** the `ports:` mapping from the
`vibetipp` service. Caddy handles Let's Encrypt automatically.
Requires a public domain with DNS pointing to the server.

### Option B — Nginx

Standard `proxy_pass http://vibetipp:8081` with your own TLS certificate.

---

## First-Run Setup Checklist

- [ ] `SECRET_KEY` set to a random value in `.env`
- [ ] Admin user created
- [ ] Player accounts created (Admin panel → "Nutzer anlegen")
- [ ] Match schedule present in `data/matches.csv` (included in repo)
- [ ] Firewall: port 8081 open inbound for players
- [ ] (Optional) `PAYMENT_LINK` configured in `.env`

---

## Updating

```bash
git pull
docker compose up -d --build
```

Data is preserved in the Docker volume. No schema migrations are needed — CSV
headers are additive.

---

## Data Backup

The entire app state lives in the `vibetipp_data` Docker volume.

```bash
# Backup
docker run --rm \
  -v vibetipp_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/vibetipp-$(date +%Y%m%d).tar.gz -C /data .

# Restore
docker run --rm \
  -v vibetipp_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/vibetipp-YYYYMMDD.tar.gz -C /data
```

> The `player_results/` directory is fully derived and can be deleted at any
> time. It is rebuilt automatically on the next admin result import or
> "Punkte berechnen" action.

---

## Security Features

| Feature | Detail |
|---|---|
| **Password hashing** | Argon2id (`m=65536, t=2, p=2`) via `argon2-cffi` |
| **Timing-attack resistance** | Dummy `verify_password()` always runs, even for unknown usernames |
| **Rate limiting** | Per-source-IP in-memory counter; default 10 failed attempts → 15-min lockout (configurable) |
| **Session cookies** | `SameSite=Lax` (CSRF mitigation); `HttpOnly` implicit via Flask |
| **Role gates** | `admin` role required for all `/admin/*` routes |
| **Non-root container** | Docker image runs as unprivileged user `vibetipp` |
| **Upload size cap** | Result-file uploads limited to `MAX_UPLOAD_SIZE_MB` (default 1 MB) |
| **No SQL / no eval** | No injection surface; all storage is plain file I/O |
| **Secret key** | Flask session signed with `SECRET_KEY` env var — must be set before production |

> **Rate-limit note:** The IP lockout counter is in-memory and resets on container
> restart. This is intentional for low-traffic private deployments. For
> production hardening, add fail2ban at the host level.
