from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from app.config import RARITY_MAX_POINTS


class Tendency(str, Enum):
    HOME = "home"
    DRAW = "draw"
    AWAY = "away"


def get_tendency(home: int, away: int) -> Tendency:
    if home > away:
        return Tendency.HOME
    elif home == away:
        return Tendency.DRAW
    else:
        return Tendency.AWAY


@dataclass
class ScoreBreakdown:
    # Tendency
    tendency_pts: int = 0
    tendency_correct: bool = False
    actual_tendency: str = ""
    tip_tendency: str = ""

    # Exactness components (raw values)
    exact_result_pts: int = 0    # +5
    goal_diff_pts: int = 0       # +3 (only if not exact)
    home_goals_pts: int = 0      # +1
    away_goals_pts: int = 0      # +1
    total_goals_pts: int = 0     # +2 exact, +1 off by 1
    exactness_effective: float = 0.0  # capped at 2 if wrong tendency

    # Extras
    goalrich_pts: int = 0

    # Rarity: multiplicative factor applied to (tendency + exactness + goalrich)
    # 1.0 = no bonus (everyone agrees), 2.0 = max bonus (only you chose this)
    # Formula: 2 - share, where share = fraction who picked same tendency
    # Only applied when tendency is correct and snapshot data is available
    rarity_factor: float = 1.0
    pre_rarity_pts: float = 0.0  # points before rarity factor

    # Derived
    base_pts: float = 0.0        # = pre_rarity_pts * rarity_factor
    germany_multiplier: int = 1
    pts_after_germany: float = 0.0

    # Risk
    is_risk: bool = False
    risk_result: str = "none"   # "none" | "double" | "deduct" | "neutral"
    final_pts: float = 0.0

    # Raw inputs (for display)
    tip_home: int = 0
    tip_away: int = 0
    actual_home: int = 0
    actual_away: int = 0


def calculate_score(
    home_actual: int,
    away_actual: int,
    home_tip: int,
    away_tip: int,
    is_risk: bool,
    is_germany: bool,
    rarity_snapshot: Optional[dict],
) -> ScoreBreakdown:
    bd = ScoreBreakdown()
    bd.tip_home = home_tip
    bd.tip_away = away_tip
    bd.actual_home = home_actual
    bd.actual_away = away_actual
    bd.is_risk = is_risk

    actual_t = get_tendency(home_actual, away_actual)
    tip_t = get_tendency(home_tip, away_tip)
    bd.actual_tendency = actual_t.value
    bd.tip_tendency = tip_t.value
    bd.tendency_correct = actual_t == tip_t

    # --- Tendency points ---
    bd.tendency_pts = 4 if bd.tendency_correct else 0

    # --- Exactness ---
    exact_home = home_tip == home_actual
    exact_away = away_tip == away_actual
    exact_result = exact_home and exact_away
    actual_diff = home_actual - away_actual
    tip_diff = home_tip - away_tip
    actual_total = home_actual + away_actual
    tip_total = home_tip + away_tip

    if bd.tendency_correct:
        if exact_result:
            bd.exact_result_pts = 5
        elif actual_diff == tip_diff:
            bd.goal_diff_pts = 3

        bd.home_goals_pts = 1 if exact_home else 0
        bd.away_goals_pts = 1 if exact_away else 0

        if actual_total == tip_total:
            bd.total_goals_pts = 2
        elif abs(actual_total - tip_total) == 1:
            bd.total_goals_pts = 1

        bd.exactness_effective = (
            bd.exact_result_pts + bd.goal_diff_pts
            + bd.home_goals_pts + bd.away_goals_pts
            + bd.total_goals_pts
        )
    else:
        # Store raw values for display, but cap total contribution
        bd.home_goals_pts = 1 if exact_home else 0
        bd.away_goals_pts = 1 if exact_away else 0
        if actual_total == tip_total:
            bd.total_goals_pts = 2
        elif abs(actual_total - tip_total) == 1:
            bd.total_goals_pts = 1

        raw = bd.home_goals_pts + bd.away_goals_pts + bd.total_goals_pts
        bd.exactness_effective = min(float(raw), 2.0)

    # --- Goal-rich bonus ---
    if bd.tendency_correct and actual_total > 3 and tip_total > 3:
        bd.goalrich_pts = min(actual_total - 3, tip_total - 3, 3)

    # --- Rarity factor (multiplicative) ---
    # rarity_factor = 2 - share  (ranges 1.0 to 2.0)
    # Only awarded when tendency is correct and snapshot data exists
    bd.rarity_factor = 1.0
    if bd.tendency_correct and rarity_snapshot and rarity_snapshot.get("total_tips", 0) > 0:
        if tip_t == Tendency.HOME:
            share = float(rarity_snapshot.get("home_win_share", 0))
        elif tip_t == Tendency.DRAW:
            share = float(rarity_snapshot.get("draw_share", 0))
        else:
            share = float(rarity_snapshot.get("away_win_share", 0))
        bd.rarity_factor = round(2.0 - share, 2)

    # --- Base points ---
    bd.pre_rarity_pts = bd.tendency_pts + bd.exactness_effective + bd.goalrich_pts
    bd.base_pts = round(bd.pre_rarity_pts * bd.rarity_factor, 1)

    # --- Germany multiplier ---
    bd.germany_multiplier = 2 if is_germany else 1
    bd.pts_after_germany = bd.base_pts * bd.germany_multiplier

    # --- Risk game ---
    pts_without_risk = bd.pts_after_germany

    if not is_risk:
        bd.risk_result = "none"
        bd.final_pts = pts_without_risk
    else:
        draw_tip = tip_t == Tendency.DRAW
        draw_result = actual_t == Tendency.DRAW

        if draw_tip or draw_result:
            bd.risk_result = "neutral"
            bd.final_pts = pts_without_risk
        elif tip_t == actual_t:
            bd.risk_result = "double"
            bd.final_pts = pts_without_risk * 2
        else:
            bd.risk_result = "deduct"
            bd.final_pts = -1.0 * max(pts_without_risk, 2.0)

    # Round to 1 decimal
    bd.final_pts = round(bd.final_pts, 1)
    bd.base_pts = round(bd.base_pts, 1)
    bd.pts_after_germany = round(bd.pts_after_germany, 1)
    bd.pre_rarity_pts = round(bd.pre_rarity_pts, 1)

    return bd


def calculate_potential_rarity(tip_home: int, tip_away: int, live_distribution: dict) -> float:
    """Return the potential rarity factor (1.0=no bonus … 2.0=max) for live display."""
    total = live_distribution.get("total_tips", 0)
    if total == 0:
        return 1.0  # neutral – no data yet
    tip_t = get_tendency(tip_home, tip_away)
    if tip_t == Tendency.HOME:
        share = float(live_distribution.get("home_win_share", 0))
    elif tip_t == Tendency.DRAW:
        share = float(live_distribution.get("draw_share", 0))
    else:
        share = float(live_distribution.get("away_win_share", 0))
    return round(2.0 - share, 2)
