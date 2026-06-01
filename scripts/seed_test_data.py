"""
Seed script: adds 5 test users + matchday-1 tips for all of them.
Run once from the project root: python scripts/seed_test_data.py
"""
import sys
import random
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.config import DATA_DIR
from app.auth.hashing import hash_password
from app.repositories.users import UserRepository
from app.repositories.matches import MatchRepository
from app.repositories.tips import TipRepository

user_repo = UserRepository(DATA_DIR)
match_repo = MatchRepository(DATA_DIR)
tip_repo = TipRepository(DATA_DIR)

TEST_USERS = [
    {"username": "max_mueller",   "display_name": "Max Müller",   "password": "Test1234!"},
    {"username": "anna_schmidt",  "display_name": "Anna Schmidt",  "password": "Test1234!"},
    {"username": "ben_fischer",   "display_name": "Ben Fischer",   "password": "Test1234!"},
    {"username": "lisa_bauer",    "display_name": "Lisa Bauer",    "password": "Test1234!"},
    {"username": "kai_wolf",      "display_name": "Kai Wolf",      "password": "Test1234!"},
]

# Matchday-1 tips: different predictions per user to generate varied rarity shares
# Format: (home_goals, away_goals)
TIPS_BY_USER = {
    "max_mueller":  [(2,1),(1,0),(2,0),(2,1),(1,1),(0,1),(2,1),(0,0),(3,0),(1,0),(2,0),(1,2)],
    "anna_schmidt": [(1,1),(0,1),(1,0),(1,0),(0,2),(1,2),(1,0),(1,1),(2,1),(0,1),(1,1),(0,1)],
    "ben_fischer":  [(2,0),(2,1),(1,1),(3,1),(1,0),(2,0),(0,0),(0,2),(2,0),(2,0),(0,0),(2,1)],
    "lisa_bauer":   [(0,2),(1,0),(0,1),(0,2),(2,0),(1,0),(1,2),(1,0),(1,0),(1,1),(0,1),(1,0)],
    "kai_wolf":     [(1,0),(0,0),(2,1),(1,1),(0,1),(0,0),(2,0),(0,1),(2,2),(0,2),(1,0),(0,2)],
}

RISK_PICKS = {
    "max_mueller": "M009",   # Germany game – risky!
    "anna_schmidt": "M001",
    "ben_fischer": "M006",
    "lisa_bauer": "M003",
    "kai_wolf": "M009",
}

md1_matches = match_repo.by_matchday(1)
print(f"Found {len(md1_matches)} matches in matchday 1")

created = 0
for u in TEST_USERS:
    if user_repo.find_by_username(u["username"]):
        print(f"  SKIP (exists): {u['username']}")
        continue
    user_repo.save({
        "username": u["username"],
        "password_hash": hash_password(u["password"]),
        "role": "user",
        "display_name": u["display_name"],
        "active": True,
        "paid": False,
    })
    print(f"  Created user: {u['username']}")
    created += 1

print(f"\nCreated {created} new users")
print("Adding tips for matchday 1...")

tips_added = 0
for u in TEST_USERS:
    username = u["username"]
    user_tips = TIPS_BY_USER.get(username, [])
    risk_match = RISK_PICKS.get(username)
    for i, match in enumerate(md1_matches):
        mid = match["match_id"]
        if i < len(user_tips):
            h, a = user_tips[i]
        else:
            h, a = random.randint(0, 3), random.randint(0, 3)

        existing = tip_repo.get_user_tip(username, mid)
        if existing:
            continue

        tip_repo.save_tip(username, mid, h, a, mid == risk_match)
        tips_added += 1

print(f"Added {tips_added} tips")
print("\nDone! Test users: password is 'Test1234!' for all")
