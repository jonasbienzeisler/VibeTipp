#!/usr/bin/env python3
"""CLI tool to create or update a VibeTipp user.

Usage:
    python scripts/create_user.py <username> <display_name> [--admin] [--inactive]
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth.hashing import hash_password
from app.repositories.users import UserRepository
from app import config


def main():
    parser = argparse.ArgumentParser(description="Create or update a VibeTipp user")
    parser.add_argument("username", help="Login username")
    parser.add_argument("display_name", help="Display name shown in rankings")
    parser.add_argument("--admin", action="store_true", help="Grant admin role")
    parser.add_argument("--inactive", action="store_true", help="Create as inactive")
    parser.add_argument("--data-dir", default=None, help="Path to data directory")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else config.DATA_DIR
    repo = UserRepository(data_dir)

    existing = repo.find_by_username(args.username)
    if existing:
        print(f"Nutzer '{args.username}' existiert bereits. Passwort und Daten werden aktualisiert.")

    while True:
        pw = getpass.getpass("Passwort: ")
        pw2 = getpass.getpass("Passwort bestätigen: ")
        if pw != pw2:
            print("Passwörter stimmen nicht überein. Erneut versuchen.")
            continue
        if len(pw) < 8:
            print("Passwort muss mindestens 8 Zeichen haben.")
            continue
        break

    pw_hash = hash_password(pw)
    user = {
        "username": args.username,
        "password_hash": pw_hash,
        "role": "admin" if args.admin else "user",
        "display_name": args.display_name,
        "active": not args.inactive,
    }
    repo.save(user)
    role = "Admin" if args.admin else "Nutzer"
    status = "inaktiv" if args.inactive else "aktiv"
    print(f"✓ {role} '{args.username}' ({args.display_name}) wurde angelegt/aktualisiert [{status}].")


if __name__ == "__main__":
    main()
