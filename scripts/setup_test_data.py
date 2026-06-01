"""
Setup test data: MD4 real teams, MD3+MD4 results, MD5 kickoffs shifted,
all 7 users tipped for MD5.
Run from project root: python scripts/setup_test_data.py
"""
import csv, uuid, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

# ── MD4: replace placeholder names with real teams ──────────────────────────
MD4_TEAMS = {
    "M073": ("Tschechien",  "Schweiz"),
    "M074": ("USA",         "Paraguay"),
    "M075": ("Deutschland", "Japan"),
    "M076": ("Brasilien",   "Schottland"),
    "M077": ("Argentinien", "Österreich"),
    "M078": ("Frankreich",  "Norwegen"),
    "M079": ("Mexiko",      "Katar"),
    "M080": ("England",     "DR Kongo"),
    "M081": ("Spanien",     "Algerien"),
    "M082": ("Niederlande", "Marokko"),
    "M083": ("Belgien",     "Iran"),
    "M084": ("Kolumbien",   "Schweden"),
    "M085": ("Kanada",      "Kroatien"),
    "M086": ("Portugal",    "Türkei"),
    "M087": ("Ecuador",     "Uruguay"),
    "M088": ("Südkorea",    "Neuseeland"),
}

# ── MD4: move M083-M088 kickoffs to past ────────────────────────────────────
MD4_KICKOFF_UPDATES = {
    "M083": "2026-05-31T21:00:00+02:00",
    "M084": "2026-06-01T01:00:00+02:00",
    "M085": "2026-06-01T03:00:00+02:00",
    "M086": "2026-06-01T04:00:00+02:00",
    "M087": "2026-06-01T05:00:00+02:00",
    "M088": "2026-06-01T06:00:00+02:00",
}

# ── MD5: shift kickoffs to tomorrow (June 2) ─────────────────────────────────
MD5_KICKOFFS = {
    "M089": "2026-06-02T19:00:00+02:00",
    "M090": "2026-06-02T23:00:00+02:00",
    "M091": "2026-06-03T19:00:00+02:00",
    "M092": "2026-06-03T23:00:00+02:00",
    "M093": "2026-06-04T19:00:00+02:00",
    "M094": "2026-06-04T23:00:00+02:00",
    "M095": "2026-06-05T19:00:00+02:00",
    "M096": "2026-06-05T23:00:00+02:00",
}

# ── Results to add ────────────────────────────────────────────────────────────
NEW_RESULTS = [
    # MD3 (M049-M072)
    ("M049", 2, 0), ("M050", 0, 2), ("M051", 1, 2), ("M052", 1, 0),
    ("M053", 2, 0), ("M054", 1, 2), ("M055", 0, 3), ("M056", 1, 0),
    ("M057", 2, 1), ("M058", 0, 2), ("M059", 1, 2), ("M060", 2, 1),
    ("M061", 0, 1), ("M062", 1, 0), ("M063", 0, 2), ("M064", 1, 2),
    ("M065", 0, 1), ("M066", 0, 3), ("M067", 0, 2), ("M068", 1, 0),
    ("M069", 1, 2), ("M070", 0, 3), ("M071", 1, 0), ("M072", 0, 2),
    # MD4 (M073-M088)
    # M073 Tschechien 1-2 Schweiz → Schweiz → "Sieger 1." = Schweiz (home M089)
    # M074 USA 2-1 Paraguay → USA → "Sieger 2." = USA (home M091)
    # M075 Deutschland 3-1 Japan → Deutschland → "Sieger 3." = Deutschland (home M090)
    # M076 Brasilien 2-0 Schottland → Brasilien → "Sieger 4." = Brasilien (away M089)
    # M077 Argentinien 1-0 Österreich → Argentinien → "Sieger 5." = Argentinien (away M091)
    # M078 Frankreich 2-1 Norwegen → Frankreich → "Sieger 6." = Frankreich (away M090)
    # M079 Mexiko 2-0 Katar → Mexiko → "Sieger 7." = Mexiko (home M092)
    # M080 England 3-1 DR Kongo → England → "Sieger 8." = England (away M092)
    # M081 Spanien 2-0 Algerien → Spanien → "Sieger 9." = Spanien (away M094)
    # M082 Niederlande 1-0 Marokko → Niederlande → "Sieger 10." = Niederlande (home M094)
    # M083 Belgien 2-1 Iran → Belgien → "Sieger 11." = Belgien (away M093)
    # M084 Kolumbien 1-0 Schweden → Kolumbien → "Sieger 12." = Kolumbien (home M093)
    # M085 Kanada 2-1 Kroatien → Kanada → "Sieger 13." = Kanada (home M096)
    # M086 Portugal 3-2 Türkei → Portugal → "Sieger 14." = Portugal (away M095)
    # M087 Ecuador 1-2 Uruguay → Uruguay → "Sieger 15." = Uruguay (home M095)
    # M088 Südkorea 2-0 Neuseeland → Südkorea → "Sieger 16." = Südkorea (away M096)
    ("M073", 1, 2), ("M074", 2, 1), ("M075", 3, 1), ("M076", 2, 0),
    ("M077", 1, 0), ("M078", 2, 1), ("M079", 2, 0), ("M080", 3, 1),
    ("M081", 2, 0), ("M082", 1, 0), ("M083", 2, 1), ("M084", 1, 0),
    ("M085", 2, 1), ("M086", 3, 2), ("M087", 1, 2), ("M088", 2, 0),
]

# MD5 matches and who to tip as (home, away) per user for variety
# M089: Schweiz vs Brasilien   M090: Deutschland vs Frankreich
# M091: USA vs Argentinien     M092: Mexiko vs England
# M093: Kolumbien vs Belgien   M094: Niederlande vs Spanien
# M095: Uruguay vs Portugal    M096: Kanada vs Südkorea
MD5_MATCH_IDS = ["M089", "M090", "M091", "M092", "M093", "M094", "M095", "M096"]

USERS = ["admin", "max_mueller", "anna_schmidt", "ben_fischer", "lisa_bauer", "kai_wolf", "jonsi"]

# Different tip scores per user for variety (home:away)
USER_TIPS = {
    "admin":       [(1,1),(2,1),(1,0),(2,1),(1,0),(2,1),(1,2),(2,0)],
    "max_mueller": [(2,0),(1,2),(2,1),(1,1),(0,1),(1,0),(2,1),(1,2)],
    "anna_schmidt":[(0,2),(0,1),(1,1),(2,0),(2,1),(0,2),(1,0),(0,1)],
    "ben_fischer": [(1,0),(3,1),(0,1),(1,2),(1,1),(2,0),(0,2),(2,1)],
    "lisa_bauer":  [(2,1),(1,0),(2,2),(0,1),(1,2),(1,1),(2,0),(1,0)],
    "kai_wolf":    [(0,1),(2,0),(1,2),(2,1),(0,0),(3,1),(1,1),(0,2)],
    "jonsi":       [(1,2),(1,1),(0,2),(1,0),(2,0),(0,1),(0,1),(3,2)],
}

# Each user uses their first MD5 match as risk pick
RISK_MATCH = {u: "M089" for u in USERS}
# admin's risk pick is already set in the file; let's keep M089 for everyone
# admin tips M089 as 1:1 (non-zero chance of picking themselves risk)

def read_csv_raw(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))

def write_csv_raw(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        w.writeheader()
        w.writerows(rows)

def update_matches():
    path = DATA / "matches.csv"
    rows = read_csv_raw(path)
    for row in rows:
        mid = row["match_id"]
        if mid in MD4_TEAMS:
            row["home_team"], row["away_team"] = MD4_TEAMS[mid]
        if mid in MD4_KICKOFF_UPDATES:
            row["kickoff_at"] = MD4_KICKOFF_UPDATES[mid]
        if mid in MD5_KICKOFFS:
            row["kickoff_at"] = MD5_KICKOFFS[mid]
    write_csv_raw(path, rows, ["match_id","matchday","kickoff_at","home_team","away_team","is_germany_game"])
    print(f"matches.csv updated")

def update_results():
    path = DATA / "results.csv"
    existing = {r["match_id"] for r in read_csv_raw(path)}
    rows = read_csv_raw(path)
    added = 0
    for mid, h, a in NEW_RESULTS:
        if mid not in existing:
            rows.append({"match_id": mid, "home_goals_actual": h, "away_goals_actual": a, "status": "final"})
            added += 1
    write_csv_raw(path, rows, ["match_id","home_goals_actual","away_goals_actual","status"])
    print(f"results.csv: {added} results added")

def update_tips():
    path = DATA / "tips.csv"
    rows = read_csv_raw(path)
    # Build set of (username, match_id) that already exist
    existing = {(r["username"], r["match_id"]) for r in rows}

    now_ts = datetime.now(timezone.utc).isoformat()
    added = 0
    tip_counter = max((int(r["tip_id"][1:], 16) for r in rows if r.get("tip_id")), default=0)

    for user in USERS:
        tips = USER_TIPS[user]
        for i, mid in enumerate(MD5_MATCH_IDS):
            if (user, mid) in existing:
                continue
            tip_counter += 1
            h, a = tips[i]
            is_risk = 1 if mid == RISK_MATCH[user] else 0
            tip_id = f"T{tip_counter:08X}"
            rows.append({
                "tip_id": tip_id,
                "timestamp": now_ts,
                "username": user,
                "match_id": mid,
                "home_goals_tip": h,
                "away_goals_tip": a,
                "is_risk_pick": is_risk,
            })
            added += 1

    write_csv_raw(path, rows, ["tip_id","timestamp","username","match_id","home_goals_tip","away_goals_tip","is_risk_pick"])
    print(f"tips.csv: {added} tips added")

if __name__ == "__main__":
    update_matches()
    update_results()
    update_tips()
    print("Done. Run admin → PUNKTE BERECHNEN after this.")
