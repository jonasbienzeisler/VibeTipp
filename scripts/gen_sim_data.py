#!/usr/bin/env python3
"""Generate simulation data for local testing — end of matchday 1."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth.hashing import hash_password

SIM_DIR = Path(__file__).parent.parent / "sim" / "data"
SIM_DIR.mkdir(parents=True, exist_ok=True)

USERS = [
    ("jb_admin", "admin", "Jonas B."),
    ("felix_k",   "user",  "Felix K."),
    ("sarah_m",   "user",  "Sarah M."),
    ("thomas_b",  "user",  "Thomas B."),
    ("julia_h",   "user",  "Julia H."),
    ("markus_l",  "user",  "Markus L."),
    ("anna_w",    "user",  "Anna W."),
    ("david_s",   "user",  "David S."),
    ("lisa_n",    "user",  "Lisa N."),
    ("michael_r", "user",  "Michael R."),
    ("emma_v",    "user",  "Emma V."),
    ("christian_f","user", "Christian F."),
    ("hannah_g",  "user",  "Hannah G."),
    ("jan_d",     "user",  "Jan D."),
    ("nina_p",    "user",  "Nina P."),
    ("stefan_o",  "user",  "Stefan O."),
    ("leonie_z",  "user",  "Leonie Z."),
    ("tobias_e",  "user",  "Tobias E."),
    ("kerstin_q", "user",  "Kerstin Q."),
    ("sebastian_u","user", "Sebastian U."),
    ("katharina_i","user", "Katharina I."),
    ("florian_y", "user",  "Florian Y."),
    ("clara_x",   "user",  "Clara X."),
    ("philipp_j", "user",  "Philipp J."),
    ("marie_c",   "user",  "Marie C."),
]

PASSWORD = "test123"

# MD1 matches: (match_id, actual_home, actual_away)
RESULTS = [
    ("M001", 2, 0),  # Mexiko 2:0 Südafrika
    ("M002", 2, 1),  # Südkorea 2:1 Tschechien
    ("M003", 1, 1),  # Kanada 1:1 Bosnien
    ("M004", 4, 1),  # USA 4:1 Paraguay
    ("M005", 1, 1),  # Katar 1:1 Schweiz
    ("M006", 1, 1),  # Brasilien 1:1 Marokko
    ("M007", 0, 1),  # Haiti 0:1 Schottland
    ("M008", 2, 0),  # Australien 2:0 Türkei
    ("M009", 7, 1),  # Deutschland 7:1 Curaçao  (Germany game)
    ("M010", 2, 2),  # Niederlande 2:2 Japan
    ("M011", 1, 0),  # Elfenbeinküste 1:0 Ecuador
    ("M012", 5, 1),  # Schweden 5:1 Tunesien
    ("M013", 0, 0),  # Spanien 0:0 Kap Verde
    ("M014", 1, 1),  # Belgien 1:1 Ägypten
    ("M015", 1, 1),  # Saudi-Arabien 1:1 Uruguay
    ("M016", 2, 2),  # Iran 2:2 Neuseeland
    ("M017", 3, 1),  # Frankreich 3:1 Senegal
    ("M018", 1, 4),  # Irak 1:4 Norwegen
    ("M019", 3, 0),  # Argentinien 3:0 Algerien
    ("M020", 3, 1),  # Österreich 3:1 Jordanien
    ("M021", 1, 1),  # Portugal 1:1 DR Kongo
    ("M022", 4, 2),  # England 4:2 Kroatien
    ("M023", 1, 0),  # Ghana 1:0 Panama
    ("M024", 1, 3),  # Usbekistan 1:3 Kolumbien
]


def tendency(h, a):
    if h > a: return "home"
    if h == a: return "draw"
    return "away"


def gen_tip(match_id, actual_h, actual_a, user_idx, match_idx):
    """Generate a varied but deterministic tip."""
    rng = random.Random(user_idx * 997 + match_idx * 31 + hash(match_id) % 1000)
    actual_t = tendency(actual_h, actual_a)

    # Correct-tendency probability varies by user (55–72%)
    correct_chance = 0.55 + (user_idx % 6) * 0.03

    if rng.random() < correct_chance:
        tip_t = actual_t
    else:
        alts = [t for t in ["home", "draw", "away"] if t != actual_t]
        tip_t = rng.choice(alts)

    if tip_t == "home":
        h = rng.randint(1, 4)
        a = rng.randint(0, h - 1)
    elif tip_t == "draw":
        h = rng.randint(0, 3)
        a = h
    else:
        a = rng.randint(1, 3)
        h = rng.randint(0, a - 1)

    return h, a


# ── users.txt ────────────────────────────────────────────────────────────────
print("Generating users …")
pw_hash = hash_password(PASSWORD)
header = "username;password_hash;role;display_name;active;paid;sav_doc_id;sav_doc_version;sav_confirmed_at"
lines = [header]
for uname, role, display in USERS:
    lines.append(f"{uname};{pw_hash};{role};{display};1;1;;;")
(SIM_DIR / "users.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"  {len(USERS)} users written")

# ── matches.csv — copy from testing/data ─────────────────────────────────────
import shutil
testing_matches = Path(__file__).parent.parent / "testing" / "data" / "matches.csv"
shutil.copy(testing_matches, SIM_DIR / "matches.csv")
print("  matches.csv copied from testing/data")

# ── results.csv — only MD1, all final ────────────────────────────────────────
result_lines = ["match_id;home_goals_actual;away_goals_actual;status"]
for mid, h, a in RESULTS:
    result_lines.append(f"{mid};{h};{a};final")
(SIM_DIR / "results.csv").write_text("\n".join(result_lines) + "\n", encoding="utf-8")
print(f"  {len(RESULTS)} results written")

# ── tips.csv — 25 users × 24 matches, one risk pick per user ─────────────────
print("Generating tips …")
tip_lines = ["tip_id;timestamp;username;match_id;home_goals_tip;away_goals_tip;is_risk_pick"]
tip_counter = 1

# Each user gets exactly one risk pick — cycle through matches
for u_idx, (uname, _, _) in enumerate(USERS):
    risk_match = RESULTS[u_idx % len(RESULTS)][0]
    ts = "2026-05-11T07:00:00+00:00"
    for m_idx, (mid, ah, aa) in enumerate(RESULTS):
        h, a = gen_tip(mid, ah, aa, u_idx, m_idx)
        is_risk = "1" if mid == risk_match else "0"
        tip_id = f"SIM{tip_counter:05X}"
        tip_lines.append(f"{tip_id};{ts};{uname};{mid};{h};{a};{is_risk}")
        tip_counter += 1

(SIM_DIR / "tips.csv").write_text("\n".join(tip_lines) + "\n", encoding="utf-8")
print(f"  {tip_counter - 1} tips written")

# ── empty supporting files ────────────────────────────────────────────────────
(SIM_DIR / "adjustments.csv").write_text("username;delta;note;created_at\n", encoding="utf-8")
(SIM_DIR / "rarity_snapshots.csv").write_text(
    "match_id;frozen_at;home_win_share;draw_share;away_win_share;total_tips\n", encoding="utf-8"
)
(SIM_DIR / "world_cup_picks.csv").write_text("username;team\n", encoding="utf-8")

print(f"\nDone — sim data at: {SIM_DIR}")
print(f"Start with: DATA_DIR=sim/data python main.py")
