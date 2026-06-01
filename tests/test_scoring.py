"""Unit tests for the scoring engine."""
import pytest
from app.scoring.engine import (
    calculate_score, get_tendency, Tendency,
    calculate_potential_rarity, ScoreBreakdown
)


def score(ha, aa, ht, at, risk=False, germany=False, snap=None):
    return calculate_score(ha, aa, ht, at, risk, germany, snap)


SNAP_EVEN = {"home_win_share": 0.33, "draw_share": 0.34, "away_win_share": 0.33, "total_tips": 10}
SNAP_HOME80 = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
SNAP_NONE = {"total_tips": 0}


# ─── Tendency detection ───────────────────────────────────────

def test_tendency_home():
    assert get_tendency(2, 1) == Tendency.HOME

def test_tendency_draw():
    assert get_tendency(1, 1) == Tendency.DRAW

def test_tendency_away():
    assert get_tendency(0, 2) == Tendency.AWAY

def test_tendency_0_0():
    assert get_tendency(0, 0) == Tendency.DRAW


# ─── Tendency points ──────────────────────────────────────────

def test_correct_tendency_home():
    bd = score(2, 1, 1, 0)
    assert bd.tendency_correct is True
    assert bd.tendency_pts == 4

def test_wrong_tendency():
    bd = score(2, 1, 0, 1)
    assert bd.tendency_correct is False
    assert bd.tendency_pts == 0

def test_correct_tendency_draw():
    bd = score(1, 1, 0, 0)
    assert bd.tendency_correct is True
    assert bd.tendency_pts == 4

def test_correct_tendency_away():
    bd = score(0, 2, 1, 3)
    assert bd.tendency_correct is True
    assert bd.tendency_pts == 4

def test_wrong_tendency_draw_vs_home():
    bd = score(1, 1, 2, 1)
    assert bd.tendency_correct is False

def test_draw_result_draw_tip():
    bd = score(2, 2, 1, 1)
    assert bd.tendency_correct is True
    assert bd.tendency_pts == 4

def test_draw_correct_many_combos():
    bd = score(0, 0, 2, 2)
    assert bd.tendency_correct is True


# ─── Exact result ─────────────────────────────────────────────

def test_exact_result():
    bd = score(2, 1, 2, 1)
    assert bd.exact_result_pts == 5

def test_exact_result_draw():
    bd = score(1, 1, 1, 1)
    assert bd.exact_result_pts == 5

def test_not_exact_but_correct_diff():
    bd = score(3, 1, 2, 0)
    assert bd.exact_result_pts == 0
    assert bd.goal_diff_pts == 3

def test_correct_diff_not_awarded_if_exact():
    bd = score(2, 1, 2, 1)
    assert bd.goal_diff_pts == 0   # already exact → no double dip


# ─── Individual goal bonuses ──────────────────────────────────

def test_home_goals_exact():
    bd = score(3, 1, 3, 0)
    assert bd.home_goals_pts == 1

def test_away_goals_exact():
    bd = score(2, 1, 3, 1)
    assert bd.away_goals_pts == 1

def test_total_goals_exact():
    bd = score(3, 2, 2, 3)  # wrong tendency (3>2 vs 2<3)
    # tendency wrong, so check capped exactness
    # total: 5 vs 5 → +2, capped at 2
    assert bd.exactness_effective == 2

def test_total_goals_off_by_one():
    bd = score(3, 1, 2, 1)  # result 4 total, tip 3 total → off by 1
    assert bd.total_goals_pts == 1

def test_exact_result_also_gives_home_away_total_bonuses():
    bd = score(2, 1, 2, 1)
    # exact result (+5), home (+1), away (+1), total exact (+2)
    assert bd.exact_result_pts == 5
    assert bd.home_goals_pts == 1
    assert bd.away_goals_pts == 1
    assert bd.total_goals_pts == 2
    assert bd.exactness_effective == 9

def test_wrong_tendency_exactness_capped_at_2():
    bd = score(2, 1, 0, 1)  # home wins, tip away wins
    # away goals match (1=1) → +1
    # total: 3 vs 1 → no bonus
    raw = bd.home_goals_pts + bd.away_goals_pts + bd.total_goals_pts
    assert bd.exactness_effective == min(raw, 2)
    assert bd.exactness_effective <= 2


# ─── Goal-rich bonus ──────────────────────────────────────────

def test_goalrich_bonus_basic():
    bd = score(4, 1, 3, 2)  # 5 actual, 5 tip → min(2,2,3)=2
    assert bd.goalrich_pts == 2

def test_goalrich_bonus_max():
    bd = score(5, 2, 4, 2)  # 7 actual, 6 tip → min(4,3,3)=3
    assert bd.goalrich_pts == 3

def test_goalrich_no_bonus_low_score():
    bd = score(1, 0, 2, 1)  # result only 1 goal
    assert bd.goalrich_pts == 0

def test_goalrich_no_bonus_wrong_tendency():
    bd = score(4, 0, 0, 4)  # 4 vs 4 goals but wrong tendency
    assert bd.goalrich_pts == 0

def test_goalrich_no_bonus_exact_3():
    bd = score(2, 1, 1, 2)  # wrong tendency
    assert bd.goalrich_pts == 0

def test_goalrich_threshold():
    bd = score(2, 2, 1, 1)  # total 4 vs 2 → actual > 3 but tip_total = 2 <= 3
    assert bd.goalrich_pts == 0


# ─── Rarity factor ────────────────────────────────────────────
# rarity_factor = 2 - share  (1.0 = no bonus, 2.0 = max)
# Applied as multiplier to pre_rarity_pts; only when tendency is correct

def test_rarity_factor_home_80pct():
    snap = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    bd = score(2, 1, 1, 0, snap=snap)  # home win correct
    assert bd.rarity_factor == pytest.approx(1.2, abs=0.01)

def test_rarity_factor_draw_10pct():
    snap = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    bd = score(1, 1, 0, 0, snap=snap)  # draw correct
    assert bd.rarity_factor == pytest.approx(1.9, abs=0.01)

def test_rarity_factor_away_10pct():
    snap = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    bd = score(0, 1, 0, 2, snap=snap)  # away win correct
    assert bd.rarity_factor == pytest.approx(1.9, abs=0.01)

def test_rarity_factor_neutral_when_wrong_tendency():
    snap = {"home_win_share": 0.10, "draw_share": 0.10, "away_win_share": 0.80, "total_tips": 10}
    bd = score(2, 1, 0, 1, snap=snap)  # home wins but tip away
    assert bd.rarity_factor == 1.0  # no rarity bonus for wrong tendency

def test_rarity_factor_neutral_no_tips():
    bd = score(2, 1, 1, 0, snap=SNAP_NONE)
    assert bd.rarity_factor == 1.0

def test_rarity_factor_neutral_none_snapshot():
    bd = score(2, 1, 1, 0, snap=None)
    assert bd.rarity_factor == 1.0

def test_rarity_factor_draw_gets_bonus():
    snap = {"home_win_share": 0.50, "draw_share": 0.10, "away_win_share": 0.40, "total_tips": 10}
    bd = score(0, 0, 1, 1, snap=snap)
    assert bd.rarity_factor == pytest.approx(1.9, abs=0.01)

def test_rarity_factor_applied_to_pre_rarity_pts():
    snap = {"home_win_share": 0.50, "draw_share": 0.10, "away_win_share": 0.40, "total_tips": 10}
    bd = score(1, 1, 0, 0, snap=snap)  # draw correct; diff same → +4+3=7 pre_rarity
    assert bd.pre_rarity_pts == pytest.approx(7.0, abs=0.1)
    assert bd.rarity_factor == pytest.approx(1.9, abs=0.01)
    assert bd.base_pts == pytest.approx(7.0 * 1.9, abs=0.1)


# ─── Germany bonus ────────────────────────────────────────────

def test_germany_doubles_points():
    bd_plain = score(2, 1, 1, 0)
    bd_ger = score(2, 1, 1, 0, germany=True)
    assert bd_ger.pts_after_germany == bd_plain.base_pts * 2

def test_germany_multiplier_1_by_default():
    bd = score(2, 1, 1, 0)
    assert bd.germany_multiplier == 1


# ─── Risk game ────────────────────────────────────────────────

def test_risk_optional_no_effect():
    bd_no_risk = score(2, 1, 1, 0)
    bd_no_risk_explicit = score(2, 1, 1, 0, risk=False)
    assert bd_no_risk.final_pts == bd_no_risk_explicit.final_pts
    assert bd_no_risk.risk_result == "none"

def test_risk_correct_winner_doubles():
    bd_no_risk = score(2, 1, 1, 0)
    bd_risk = score(2, 1, 1, 0, risk=True)
    assert bd_risk.final_pts == bd_no_risk.pts_after_germany * 2
    assert bd_risk.risk_result == "double"

def test_risk_wrong_winner_deducts():
    bd = score(2, 1, 0, 1, risk=True)  # home wins, tip away
    assert bd.final_pts < 0
    assert bd.risk_result == "deduct"

def test_risk_wrong_winner_minimum_deduct():
    # Even if base points are tiny, minimum deduct is 2
    bd = score(1, 0, 0, 2, risk=True)  # home win, tip away → 0 base points
    assert bd.final_pts == -2.0

def test_risk_tip_draw_no_effect():
    bd_no_risk = score(2, 1, 0, 0, risk=False)  # result home win, tip draw
    bd_risk = score(2, 1, 0, 0, risk=True)
    assert bd_risk.final_pts == bd_no_risk.final_pts
    assert bd_risk.risk_result == "neutral"

def test_risk_actual_draw_no_effect():
    bd_no_risk = score(1, 1, 2, 1, risk=False)  # result draw, tip home win
    bd_risk = score(1, 1, 2, 1, risk=True)
    assert bd_risk.final_pts == bd_no_risk.final_pts
    assert bd_risk.risk_result == "neutral"

def test_risk_actual_draw_with_correct_tip_draw_no_effect():
    bd_no_risk = score(1, 1, 0, 0, risk=False)
    bd_risk = score(1, 1, 0, 0, risk=True)
    assert bd_risk.final_pts == bd_no_risk.final_pts
    assert bd_risk.risk_result == "neutral"


# ─── Combined Germany + Risk ──────────────────────────────────

def test_germany_risk_correct_quadruples():
    bd = score(2, 1, 1, 0, risk=True, germany=True)
    bd_plain = score(2, 1, 1, 0)
    assert bd.final_pts == bd_plain.base_pts * 4

def test_germany_risk_wrong_deduct_doubled():
    bd = score(2, 1, 0, 1, risk=True, germany=True)
    bd_no_risk = score(2, 1, 0, 1, germany=True)
    expected = -1 * max(bd_no_risk.pts_after_germany, 2)
    assert bd.final_pts == expected

def test_germany_risk_draw_no_risk_effect_but_germany_applies():
    bd_no_risk = score(1, 1, 0, 0, germany=True)
    bd_risk = score(1, 1, 0, 0, risk=True, germany=True)
    # Draw result → no risk effect, but Germany bonus still applies
    assert bd_risk.final_pts == bd_no_risk.final_pts
    assert bd_risk.germany_multiplier == 2


# ─── Example from spec ────────────────────────────────────────

def test_spec_example():
    # "Dein Tipp: 2:1, Ergebnis: 3:1"
    # Tendency: home win correct (+4)
    # goal_diff: tip_diff=1, actual_diff=2 → no
    # away exact (+1); total off by 1 (3 vs 4, +1)
    # pre_rarity = 4 + 0 + 0 + 1 + 1 = 6
    # rarity_factor = 2 - 0.60 = 1.40
    # base = 6 * 1.40 = 8.4
    # germany * 2 = 16.8; risk double * 2 = 33.6
    snap = {"home_win_share": 0.60, "draw_share": 0.20, "away_win_share": 0.20, "total_tips": 5}
    bd = score(3, 1, 2, 1, risk=True, germany=True, snap=snap)
    assert bd.tendency_pts == 4
    assert bd.goal_diff_pts == 0
    assert bd.away_goals_pts == 1
    assert bd.total_goals_pts == 1
    assert bd.rarity_factor == pytest.approx(1.40, abs=0.01)
    assert bd.pre_rarity_pts == pytest.approx(6.0, abs=0.05)
    assert bd.base_pts == pytest.approx(8.4, abs=0.1)
    assert bd.risk_result == "double"
    assert bd.final_pts == pytest.approx(33.6, abs=0.2)


# ─── Potential rarity ─────────────────────────────────────────

def test_potential_rarity_factor_live():
    distrib = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    val = calculate_potential_rarity(1, 0, distrib)  # home win tip
    assert val == pytest.approx(1.2, abs=0.01)  # 2 - 0.80 = 1.2

def test_potential_rarity_neutral_no_tips():
    val = calculate_potential_rarity(1, 0, {"total_tips": 0})
    assert val == 1.0  # neutral factor when no data
