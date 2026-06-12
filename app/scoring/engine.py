from dataclasses import dataclass
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
    tendency_correct: bool = False
    actual_tendency: str = ""
    tip_tendency: str = ""

    # Base category — mutually exclusive, highest wins
    # "exact" (+4) | "goal_diff" (+3) | "tendency" (+2) | "none" (0)
    base_category: str = "none"
    base_category_pts: int = 0

    # Additional bonus (independent of tendency correctness)
    total_goals_pts: int = 0     # +1 if total goals (home+away) match exactly

    # Rarity: multiplier applied to (base_category_pts + total_goals_pts)
    # 1.0 = no bonus, 2.0 = max; only when tendency is correct
    rarity_factor: float = 1.0
    pre_rarity_pts: float = 0.0  # base_category_pts + total_goals_pts
    base_pts: float = 0.0        # pre_rarity_pts * rarity_factor

    # Germany multiplier
    germany_multiplier: int = 1
    pts_after_germany: float = 0.0

    # Risk
    is_risk: bool = False
    risk_result: str = "none"    # "none" | "double" | "deduct"
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

    actual_diff = home_actual - away_actual
    tip_diff = home_tip - away_tip
    actual_total = home_actual + away_actual
    tip_total = home_tip + away_tip
    exact_result = (home_tip == home_actual) and (away_tip == away_actual)

    # --- Base category (mutually exclusive, highest wins) ---
    if bd.tendency_correct:
        if exact_result:
            bd.base_category = "exact"
            bd.base_category_pts = 4
        elif actual_diff != 0 and actual_diff == tip_diff:
            # goal_diff only meaningful when there is a clear winner (diff != 0)
            bd.base_category = "goal_diff"
            bd.base_category_pts = 3
        else:
            bd.base_category = "tendency"
            bd.base_category_pts = 2
    else:
        bd.base_category = "none"
        bd.base_category_pts = 0

    # --- Rarity factor (only when tendency is correct) ---
    bd.rarity_factor = 1.0
    if bd.tendency_correct and rarity_snapshot and rarity_snapshot.get("total_tips", 0) > 0:
        if tip_t == Tendency.HOME:
            share = float(rarity_snapshot.get("home_win_share", 0))
        elif tip_t == Tendency.DRAW:
            share = float(rarity_snapshot.get("draw_share", 0))
        else:
            share = float(rarity_snapshot.get("away_win_share", 0))
        bd.rarity_factor = round(2.0 - share, 2)

    # --- Pre-rarity and base points ---
    bd.pre_rarity_pts = float(bd.base_category_pts)
    bd.base_pts = round(bd.pre_rarity_pts * bd.rarity_factor, 1)

    # --- Germany multiplier ---
    bd.germany_multiplier = 2 if is_germany else 1
    bd.pts_after_germany = round(bd.base_pts * bd.germany_multiplier, 1)

    # --- Risk game ---
    if not is_risk:
        bd.risk_result = "none"
        bd.final_pts = bd.pts_after_germany
    elif bd.tendency_correct:
        bd.risk_result = "double"
        bd.final_pts = round(bd.pts_after_germany * 2, 1)
    else:
        bd.risk_result = "deduct"
        bd.final_pts = -20.0 if is_germany else -10.0

    bd.pre_rarity_pts = round(bd.pre_rarity_pts, 1)
    bd.final_pts = round(bd.final_pts, 1)

    return bd


def calculate_potential_rarity(tip_home: int, tip_away: int, live_distribution: dict) -> float:
    """Return the potential rarity factor (1.0=no bonus … 2.0=max) for live display."""
    total = live_distribution.get("total_tips", 0)
    if total == 0:
        return 1.0
    tip_t = get_tendency(tip_home, tip_away)
    if tip_t == Tendency.HOME:
        share = float(live_distribution.get("home_win_share", 0))
    elif tip_t == Tendency.DRAW:
        share = float(live_distribution.get("draw_share", 0))
    else:
        share = float(live_distribution.get("away_win_share", 0))
    return round(2.0 - share, 2)
