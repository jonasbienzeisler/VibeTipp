# VibeTipp – Setup Guide

Get VibeTipp running from scratch using the pre-built image from GitHub.
No Python, no build step — just clone the repo, set a secret key, and start.

All user data (tips, results, users) lives in a named Docker/Podman volume
and survives container restarts and updates.

---

## Prerequisites

Install one of these (both work on Linux, WSL, and most servers):

- **Docker** + **Docker Compose** v2 (`docker compose`, not `docker-compose`)
- **Podman** + **podman-compose** — `pip install podman-compose`

---

## 1 – Clone the repo

```bash
git clone https://github.com/JonasBienzeisler/VibeTipp.git
cd VibeTipp
```

---

## 2 – Create your .env file

```bash
# generate a secret key
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Create a file called `.env` in the repo root with this content,
replacing the SECRET_KEY value with the output from above:

```
SECRET_KEY=paste-your-generated-key-here
PORT=8081
```

---

## 3 – Start the container

**Docker:**
```bash
docker compose pull
docker compose up -d
```

**Podman:**
```bash
podman-compose pull
podman-compose up -d
```

Check it started cleanly:
```bash
docker compose logs -f
# or: podman-compose logs -f
```

The app is now running at **http://localhost:8081**

---

## 4 – Create the admin user

```bash
docker exec -it VibeTipp python scripts/create_user.py admin "Admin" --admin
# or: podman exec -it VibeTipp python scripts/create_user.py admin "Admin" --admin
```

You will be prompted to enter and confirm a password (min. 8 characters).

---

## 5 – Verify everything is in place

```bash
docker exec VibeTipp ls -la /data
# or: podman exec VibeTipp ls -la /data
```

Expected:
```
matches.csv           ← seeded from the image on first start
tips.csv              ← auto-created (empty)
results.csv           ← auto-created (empty)
rarity_snapshots.csv  ← auto-created (empty)
adjustments.csv       ← auto-created (empty)
users.txt             ← written when you ran step 4
player_results/       ← directory, auto-created
```

Log in at **http://localhost:8081** with the admin credentials from step 4.

---

## Adding more users

```bash
# regular user
docker exec -it VibeTipp python scripts/create_user.py <username> "<Display Name>"

# admin user
docker exec -it VibeTipp python scripts/create_user.py <username> "<Display Name>" --admin
```

Users can also be created and managed through the admin panel in the web UI.

---

## Updating to a new version

```bash
docker compose pull
docker compose up -d
```

The volume is untouched. Takes ~5 seconds of downtime.

---

## WSL notes

- **Docker Desktop with WSL2 integration**: run all commands inside WSL — the socket is exposed there automatically.
- **Native Docker inside WSL**: start the daemon first with `sudo service docker start`.
- Port 8081 is accessible from Windows at `http://localhost:8081` — no extra config needed.
- Data lives inside WSL in the named volume, not on the Windows filesystem. Always inspect with `docker exec VibeTipp ls /data`, not by browsing `C:\`.

---

## Troubleshooting

**I only see `matches.csv` when I browse `~/VibeTipp/data` on the host.**
That is the git repo folder on disk, not the volume. Runtime data is stored
inside the named volume. Check with `docker exec VibeTipp ls /data`.

**The container exits immediately.**
```bash
docker logs VibeTipp
```
Most likely `SECRET_KEY` is missing from `.env`.

**Permission errors in logs (rootless Podman).**
```bash
podman unshare chown -R 999:999 \
  $(podman volume inspect vibetipp_data --format '{{.Mountpoint}}')
```

**Port 8081 is already in use.**
Edit `docker-compose.yml` and change the host port:
```yaml
ports:
  - "9000:8081"   # host:container
```
