from pathlib import Path
from datetime import datetime, timezone
from filelock import FileLock


class PlayerResultsWriter:
    """Generates per-user plain-text result files in data/player_results/.

    Files are written after every result import or individual score entry and contain
    only data up to the last fully evaluated matchday, so other users can read them
    without seeing unevaluated tips.
    """

    def __init__(self, data_dir: Path):
        self._dir = data_dir / "player_results"
        self._dir.mkdir(exist_ok=True)

    def generate_for_user(
        self,
        username: str,
        display_name: str,
        match_repo,
        tip_repo,
        result_repo,
        snapshot_repo,
        adj_repo,
    ) -> None:
        from app.scoring.engine import calculate_score

        path = self._dir / f"{username}.txt"
        lock = FileLock(str(path) + ".lock")

        lines = []
        lines.append("=" * 68)
        lines.append("  VIBETIPP - ERGEBNISPROTOKOLL")
        lines.append("=" * 68)
        lines.append(f"  Spieler : {display_name} ({username})")
        lines.append(
            f"  Stand   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        lines.append(
            "  Hinweis : Nur abgeschlossene Spieltage. Nicht ausgewertete"
        )
        lines.append(
            "            Spiele werden nicht angezeigt (kein Spickzettel!)."
        )
        lines.append("=" * 68)
        lines.append("")

        grand_total = 0.0

        for md in match_repo.matchdays():
            matches = match_repo.by_matchday(md)
            has_evaluated = any(
                (r := result_repo.find(m["match_id"])) and r["status"] == "final"
                for m in matches
            )
            if not has_evaluated:
                continue

            lines.append(f"{'─' * 68}")
            lines.append(f"  SPIELTAG {md}")
            lines.append(f"{'─' * 68}")

            md_total = 0.0

            for m in matches:
                r = result_repo.find(m["match_id"])
                de_tag = "  [DE x2]" if m.get("is_germany_game") else ""
                header = f"  [{m['match_id']}] {m['home_team']} – {m['away_team']}{de_tag}"
                lines.append("")
                lines.append(header)

                if not r or r["status"] != "final":
                    lines.append("    Ergebnis : AUSSTEHEND")
                    lines.append("    Punkte   : –")
                    continue

                home_a, away_a = r["home_goals_actual"], r["away_goals_actual"]
                if home_a > away_a:
                    t_actual = "HEIMSIEG"
                elif home_a < away_a:
                    t_actual = "AUSWAERTSSIEG"
                else:
                    t_actual = "UNENTSCHIEDEN"
                lines.append(f"    Ergebnis : {home_a}:{away_a}  ({t_actual})")

                tip = tip_repo.get_user_tip(username, m["match_id"])
                if not tip:
                    lines.append("    Tipp     : NICHT GETIPPT (0 Pkt)")
                    continue

                home_t, away_t = tip["home_goals_tip"], tip["away_goals_tip"]
                if home_t > away_t:
                    t_tip = "HEIMSIEG"
                elif home_t < away_t:
                    t_tip = "AUSWAERTSSIEG"
                else:
                    t_tip = "UNENTSCHIEDEN"

                is_risk = tip["is_risk_pick"]
                snap = {}
                if m.get("kickoff_at"):
                    snap = snapshot_repo.get_or_create(
                        m["match_id"], m["kickoff_at"], tip_repo
                    )

                bd = calculate_score(
                    home_a, away_a, home_t, away_t,
                    is_risk, m["is_germany_game"], snap,
                )

                risk_tag = "  [HOCHRISIKO]" if is_risk else ""
                lines.append(f"    Tipp     : {home_t}:{away_t}  ({t_tip}){risk_tag}")
                lines.append(f"    {'─' * 50}")
                tend_ok = "✓ RICHTIG" if bd.tendency_correct else "✗ FALSCH "
                category_label = {
                    "exact":     "Exaktes Ergebnis (+4)",
                    "goal_diff": "Torunterschied   (+3)",
                    "tendency":  "Tendenz          (+2)",
                    "none":      "Keine            (+0)",
                }.get(bd.base_category, bd.base_category)
                lines.append(f"    Tendenz          : {tend_ok}")
                lines.append(f"    Kategorie        : {category_label:<28} +{bd.base_category_pts} Pkt")
                lines.append(f"    Gesamttore       : {'✓ Treffer' if bd.total_goals_pts else '✗ Verfehlt':<28} +{bd.total_goals_pts} Pkt")
                lines.append(f"    Pre-Rarity       : {bd.pre_rarity_pts:.1f} Pkt")
                lines.append(f"    Raritaetsfaktor  : x{bd.rarity_factor:.2f}")
                lines.append(f"    Basispunkte      : {bd.base_pts:.1f} Pkt")
                if m["is_germany_game"]:
                    lines.append(f"    Deutschland x2   : {bd.pts_after_germany:.1f} Pkt")
                if is_risk:
                    risk_labels = {
                        "double": "✓ VERDOPPELT (x2)",
                        "deduct": "✗ ABZUG (-10 Pkt)",
                        "none":   "–",
                    }
                    lines.append(f"    Hochrisiko       : {risk_labels.get(bd.risk_result, bd.risk_result)}")
                lines.append(f"    {'─' * 50}")
                lines.append(f"    FINALE PUNKTE    : {bd.final_pts:+.1f} Pkt")

                md_total += bd.final_pts

            lines.append("")
            lines.append(f"  SPIELTAG {md} GESAMT: {md_total:+.1f} Pkt")
            lines.append("")
            grand_total += md_total

        adj_total = adj_repo.get_user_delta(username)
        if adj_total != 0.0:
            lines.append(f"  Manuelle Anpassungen: {adj_total:+.1f} Pkt")
            grand_total += adj_total

        lines.append("=" * 68)
        lines.append(f"  GESAMTPUNKTE: {grand_total:+.1f} Pkt")
        lines.append("=" * 68)

        with lock:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def generate_all(
        self,
        user_repo,
        match_repo,
        tip_repo,
        result_repo,
        snapshot_repo,
        adj_repo,
    ) -> None:
        for user in user_repo.all():
            if user["active"]:
                self.generate_for_user(
                    user["username"],
                    user.get("display_name", user["username"]),
                    match_repo,
                    tip_repo,
                    result_repo,
                    snapshot_repo,
                    adj_repo,
                )

    def get_path(self, username: str) -> Path:
        return self._dir / f"{username}.txt"

    def exists(self, username: str) -> bool:
        return self.get_path(username).exists()
