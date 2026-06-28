"""Admin data-file editor: a safe, validated way to view and correct the raw
CSV data files from the admin panel.

Each editable file declares its expected header, human guidance, and a validator.
Validation runs BEFORE any write: errors block the save entirely, warnings are
shown but allow saving. Every successful save first makes a timestamped backup,
then writes atomically.

The health-check functions inspect the *current* data and surface problems
(wrong Germany flag, implausible kickoff dates, leftover placeholders, …) so the
admin sees what needs fixing without reading the CSV by hand.
"""
import re
import shutil
from datetime import datetime, timezone

from app.repositories.base import read_lines, atomic_write_text
from app.repositories.matches import HEADERS as MATCH_HEADERS
from app.repositories.results import HEADERS as RESULT_HEADERS, VALID_STATUSES
from app.repositories.adjustments import HEADERS as ADJ_HEADERS

DELIM = ";"

# Earliest plausible kickoff — the tournament's opening match. Anything before
# this is almost certainly a typo (the bug that broke the knockout stage).
TOURNAMENT_START = datetime(2026, 6, 11, tzinfo=timezone.utc)

GERMANY = "Deutschland"
# Names that mean "not yet resolved" — fine for future rounds, suspicious once a
# match is locked / played.
PLACEHOLDER_RE = re.compile(
    r"Sieger|Verlierer|Dritter|Zweiter|Erster|Gruppe|Platz|TBD|Halbfinale|16tel|AF\b|VF\b",
    re.IGNORECASE,
)


# ─────────────────────────── helpers ───────────────────────────

def _parse_kickoff(value: str):
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _split_rows(content: str, expected_headers: list[str]):
    """Split raw CSV text into (header_list, data_rows_as_dicts, structural_errors).

    Structural errors cover anything that would make the file unparseable or
    silently corrupt: missing/renamed header, wrong column count. These always
    block a save.
    """
    errors: list[str] = []
    lines = [ln for ln in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    # Drop trailing blank lines but keep internal structure for line numbers.
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        return [], [], ["Datei ist leer."]

    header = [h.strip() for h in lines[0].split(DELIM)]
    if header != expected_headers:
        errors.append(
            "Kopfzeile stimmt nicht. Erwartet exakt:\n"
            + DELIM.join(expected_headers)
            + "\nGefunden:\n" + lines[0]
        )
        # Without a correct header we cannot safely map columns.
        return header, [], errors

    rows = []
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split(DELIM)]
        if len(parts) != len(expected_headers):
            errors.append(
                f"Zeile {i}: {len(parts)} Spalten statt {len(expected_headers)} "
                f"(Trennzeichen ist »{DELIM}«)."
            )
            continue
        rows.append({"_line": i, **dict(zip(expected_headers, parts))})
    return header, rows, errors


def _check_duplicate_ids(rows, key, errors):
    seen = set()
    for r in rows:
        v = r.get(key, "")
        if v in seen:
            errors.append(f"Zeile {r['_line']}: doppelte {key} »{v}«.")
        seen.add(v)


# ─────────────────────────── validators ───────────────────────────
# Each returns (errors, warnings). Errors block the save; warnings do not.

def validate_matches(content: str):
    errors, warnings = [], []
    _, rows, structural = _split_rows(content, MATCH_HEADERS)
    errors.extend(structural)
    if structural:
        return errors, warnings

    _check_duplicate_ids(rows, "match_id", errors)
    for r in rows:
        ln = r["_line"]
        if not r["match_id"]:
            errors.append(f"Zeile {ln}: match_id fehlt.")
        if not r["matchday"].isdigit():
            errors.append(f"Zeile {ln}: matchday muss eine Zahl sein (war »{r['matchday']}«).")
        dt = _parse_kickoff(r["kickoff_at"])
        if dt is None:
            errors.append(
                f"Zeile {ln}: kickoff_at ungültig »{r['kickoff_at']}« "
                "(Format: 2026-07-04T22:00:00+02:00)."
            )
        elif dt < TOURNAMENT_START:
            warnings.append(
                f"{r['match_id']}: Anpfiff {r['kickoff_at']} liegt vor Turnierstart "
                "(11.06.2026) — vermutlich ein Tippfehler."
            )
        if r["is_germany_game"] not in ("0", "1"):
            errors.append(
                f"Zeile {ln}: is_germany_game muss 0 oder 1 sein (war »{r['is_germany_game']}«)."
            )
        if not r["home_team"] or not r["away_team"]:
            errors.append(f"Zeile {ln}: Team-Name fehlt.")
        # Germany flag consistency (warning — admin may have a reason).
        is_de_team = GERMANY in (r["home_team"], r["away_team"])
        if is_de_team and r["is_germany_game"] != "1":
            warnings.append(
                f"{r['match_id']}: Deutschland-Spiel, aber is_germany_game={r['is_germany_game']} "
                "(sollte 1 sein → doppelte Punkte)."
            )
        if not is_de_team and r["is_germany_game"] == "1":
            warnings.append(
                f"{r['match_id']}: als Deutschland-Spiel markiert, aber kein Team »Deutschland«."
            )
    return errors, warnings


def validate_results(content: str):
    errors, warnings = [], []
    _, rows, structural = _split_rows(content, RESULT_HEADERS)
    errors.extend(structural)
    if structural:
        return errors, warnings

    _check_duplicate_ids(rows, "match_id", errors)
    for r in rows:
        ln = r["_line"]
        if not r["match_id"]:
            errors.append(f"Zeile {ln}: match_id fehlt.")
        if r["status"] not in VALID_STATUSES:
            errors.append(
                f"Zeile {ln}: Status »{r['status']}« ungültig "
                f"(erlaubt: {', '.join(sorted(VALID_STATUSES))})."
            )
        if r["status"] == "final":
            for fld in ("home_goals_actual", "away_goals_actual"):
                val = r[fld]
                if not (val.isdigit() and 0 <= int(val) <= 50):
                    errors.append(f"Zeile {ln}: {fld} muss eine Ganzzahl 0–50 sein (war »{val}«).")
    return errors, warnings


def validate_generic(content: str, headers: list[str]):
    """Structural-only validation for files without domain rules."""
    _, _, errors = _split_rows(content, headers)
    return errors, []


# ─────────────────────────── file registry ───────────────────────────

EDITABLE_FILES = {
    "matches": {
        "filename": "matches.csv",
        "label": "Spielplan (matches.csv)",
        "headers": MATCH_HEADERS,
        "validator": validate_matches,
        "recompute": True,
        "guidance": [
            "Trennzeichen ist Semikolon ( ; ) — kein Komma, kein Tab.",
            "Kopfzeile NICHT verändern: " + DELIM.join(MATCH_HEADERS),
            "is_germany_game: 1 für Deutschland-Spiele (doppelte Punkte), sonst 0.",
            "kickoff_at im Format 2026-07-04T22:00:00+02:00 (ISO 8601 mit Zeitzone).",
            "match_id muss eindeutig sein (z. B. M075). Bestehende IDs nicht umbenennen.",
            "Spiele sperren automatisch beim Anpfiff — falsche Daten sperren/öffnen Spiele falsch.",
            "Vor dem Speichern wird automatisch eine Sicherung angelegt.",
        ],
    },
    "results": {
        "filename": "results.csv",
        "label": "Ergebnisse (results.csv)",
        "headers": RESULT_HEADERS,
        "validator": validate_results,
        "recompute": True,
        "guidance": [
            "Trennzeichen ist Semikolon ( ; ).",
            "Kopfzeile NICHT verändern: " + DELIM.join(RESULT_HEADERS),
            "status: scheduled, final, locked oder cancelled.",
            "Bei status=final müssen home/away_goals_actual ganze Zahlen 0–50 sein.",
            "match_id muss zu einem Spiel im Spielplan passen.",
        ],
    },
    "adjustments": {
        "filename": "adjustments.csv",
        "label": "Punkt-Korrekturen (adjustments.csv)",
        "headers": ADJ_HEADERS,
        "validator": lambda c: validate_generic(c, ADJ_HEADERS),
        "recompute": True,
        "guidance": [
            "Trennzeichen ist Semikolon ( ; ).",
            "Kopfzeile NICHT verändern: " + DELIM.join(ADJ_HEADERS),
            "delta: Punkte (auch negativ, z. B. -5). username muss existieren.",
        ],
    },
}


def get_file_meta(key: str):
    return EDITABLE_FILES.get(key)


def read_file_content(data_dir, key: str) -> str:
    meta = EDITABLE_FILES[key]
    path = data_dir / meta["filename"]
    if not path.exists():
        return DELIM.join(meta["headers"]) + "\n"
    return "\n".join(read_lines(path)) + "\n"


def validate_content(key: str, content: str):
    meta = EDITABLE_FILES[key]
    return meta["validator"](content)


def save_file_content(data_dir, key: str, content: str):
    """Validate, back up, then write atomically.

    Returns (ok, errors, warnings, backup_name). On validation errors nothing is
    written.
    """
    meta = EDITABLE_FILES[key]
    errors, warnings = validate_content(key, content)
    if errors:
        return False, errors, warnings, None

    path = data_dir / meta["filename"]
    backup_name = None
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.stem}_backup_{ts}{path.suffix}"
        shutil.copy2(str(path), str(data_dir / backup_name))

    normalized = "\n".join(
        ln.rstrip() for ln in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip("\n") + "\n"
    atomic_write_text(path, normalized)
    return True, [], warnings, backup_name


# ─────────────────────────── health checks ───────────────────────────

def run_health_checks(match_repo, result_repo) -> list[dict]:
    """Inspect current data and return a list of issues.

    Each issue: {severity: 'error'|'warning'|'info', file, code, message}.
    Used to render the warning banner on the admin index.
    """
    issues: list[dict] = []
    matches = match_repo.all()

    seen_ids = set()
    for m in matches:
        mid = m["match_id"]
        if mid in seen_ids:
            issues.append({"severity": "error", "file": "matches", "code": "dup_id",
                           "message": f"{mid}: doppelte match_id."})
        seen_ids.add(mid)

        home, away = m["home_team"], m["away_team"]
        is_de = GERMANY in (home, away)
        if is_de and not m["is_germany_game"]:
            issues.append({"severity": "warning", "file": "matches", "code": "germany_flag_missing",
                           "message": f"{mid} {home}–{away}: Deutschland-Spiel ohne "
                                      "doppelte Punkte (is_germany_game=0)."})
        if not is_de and m["is_germany_game"]:
            issues.append({"severity": "warning", "file": "matches", "code": "germany_flag_extra",
                           "message": f"{mid} {home}–{away}: als Deutschland-Spiel markiert, "
                                      "obwohl kein Team »Deutschland«."})

        kickoff = m["kickoff_at"]
        if kickoff is None:
            issues.append({"severity": "error", "file": "matches", "code": "bad_date",
                           "message": f"{mid}: kickoff_at fehlt oder ungültig."})
        elif kickoff < TOURNAMENT_START:
            issues.append({"severity": "warning", "file": "matches", "code": "early_date",
                           "message": f"{mid} {home}–{away}: Anpfiff "
                                      f"{m['kickoff_str']} liegt vor Turnierstart — "
                                      "vermutlich falsches Datum."})

        # Placeholder team name on a match that is already locked → it should have
        # been resolved to real teams by now.
        if match_repo.is_locked(m) and (PLACEHOLDER_RE.search(home) or PLACEHOLDER_RE.search(away)):
            issues.append({"severity": "info", "file": "matches", "code": "placeholder_locked",
                           "message": f"{mid}: gesperrt, aber Team noch Platzhalter "
                                      f"»{home} – {away}«."})

    return issues
