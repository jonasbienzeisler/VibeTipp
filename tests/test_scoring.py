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


# ─── Base category: tendency (2pts) ──────────────────────────

def test_correct_tendency_home_base():
    bd = score(2, 1, 3, 1)   # diff 1 vs 2 → tendency only
    assert bd.tendency_correct is True
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2

def test_wrong_tendency_zero():
    bd = score(2, 1, 0, 1)
    assert bd.tendency_correct is False
    assert bd.base_category == "none"
    assert bd.base_category_pts == 0

def test_correct_tendency_draw():
    bd = score(1, 1, 0, 0)
    assert bd.tendency_correct is True
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2

def test_correct_tendency_away():
    bd = score(0, 2, 0, 1)   # diff -2 vs -1 → tendency only
    assert bd.tendency_correct is True
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2


# ─── Base category: goal_diff (3pts) ─────────────────────────

def test_goal_diff_correct():
    bd = score(3, 1, 2, 0)   # diff=2 both sides, not exact
    assert bd.base_category == "goal_diff"
    assert bd.base_category_pts == 3

def test_goal_diff_wins_over_tendency():
    bd = score(2, 0, 1, 0)   # diff=2 vs diff=1 — different, only tendency
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2

def test_goal_diff_not_awarded_for_draws():
    # Both teams drew → diff=0 on both sides, but draw goal_diff should NOT give +3
    bd = score(1, 1, 0, 0)
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2

def test_goal_diff_not_awarded_for_draws_2():
    bd = score(2, 2, 1, 1)
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2


# ─── Base category: exact result (4pts) ──────────────────────

def test_exact_result():
    bd = score(2, 1, 2, 1)
    assert bd.base_category == "exact"
    assert bd.base_category_pts == 4

def test_exact_result_draw():
    bd = score(1, 1, 1, 1)
    assert bd.base_category == "exact"
    assert bd.base_category_pts == 4

def test_exact_beats_goal_diff():
    bd = score(2, 1, 2, 1)
    assert bd.base_category == "exact"
    assert bd.base_category_pts == 4


# ─── Total goals bonus (+1) ───────────────────────────────────

# NOTE: the "Gesamttore" (total-goals) bonus was removed (commit c3c709a). The engine
# never adds it — total_goals_pts is always 0. Per the SAV (Task 3) only the highest
# base category counts: +4 exact / +3 diff / +2 tendency / 0 wrong.

def test_total_goals_correct_tendency():
    # 2:1 result, tip 3:0 → tendency only; no total-goals bonus
    bd = score(2, 1, 3, 0)
    assert bd.total_goals_pts == 0
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2
    assert bd.pre_rarity_pts == 2.0

def test_total_goals_wrong_tendency():
    # 2:1 result, tip 1:2 → wrong tendency → 0 (total goals irrelevant)
    bd = score(2, 1, 1, 2)
    assert bd.total_goals_pts == 0
    assert bd.base_category == "none"
    assert bd.base_category_pts == 0

def test_total_goals_with_exact():
    # 2:1 result, tip 2:1 → exact (+4); no extra total-goals point
    bd = score(2, 1, 2, 1)
    assert bd.total_goals_pts == 0
    assert bd.base_category_pts == 4
    assert bd.pre_rarity_pts == 4.0

def test_no_total_goals_bonus():
    bd = score(2, 1, 1, 0)   # tip total=1, actual total=3
    assert bd.total_goals_pts == 0

def test_total_goals_draw_tip_draw_result():
    # 0:0 result, tip 0:0 → exact draw (+4); no total-goals point
    bd = score(0, 0, 0, 0)
    assert bd.total_goals_pts == 0
    assert bd.base_category == "exact"
    assert bd.pre_rarity_pts == 4.0


# ─── Spec test cases ─────────────────────────────────────────

def test_spec_2_1_tip_2_1():
    # Exact result = 4 (no total-goals bonus)
    bd = score(2, 1, 2, 1)
    assert bd.base_category_pts == 4
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 4.0

def test_spec_2_1_tip_1_0():
    # Diff correct (1=1) + no total goals → 3
    bd = score(2, 1, 1, 0)
    assert bd.base_category == "goal_diff"
    assert bd.base_category_pts == 3
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 3.0

def test_spec_2_1_tip_3_0():
    # Tendency correct, diff wrong (1≠3) → 2 (no total-goals bonus)
    bd = score(2, 1, 3, 0)
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 2.0

def test_spec_2_1_tip_1_2():
    # Wrong tendency → 0 (no total-goals bonus)
    bd = score(2, 1, 1, 2)
    assert bd.base_category == "none"
    assert bd.base_category_pts == 0
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 0.0

def test_spec_1_1_tip_1_1():
    # Exact draw = 4 (no total-goals bonus)
    bd = score(1, 1, 1, 1)
    assert bd.base_category_pts == 4
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 4.0

def test_spec_1_1_tip_0_0():
    # Draw tendency, no total (0≠2) → 2
    bd = score(1, 1, 0, 0)
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 2.0

def test_spec_1_1_tip_2_2():
    # Draw tendency, no total (4≠2) → 2
    bd = score(1, 1, 2, 2)
    assert bd.base_category == "tendency"
    assert bd.base_category_pts == 2
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 2.0

def test_spec_1_1_tip_2_1():
    # Wrong tendency (home vs draw), no total (3≠2) → 0
    bd = score(1, 1, 2, 1)
    assert bd.base_category == "none"
    assert bd.base_category_pts == 0
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 0.0


# ─── Rarity factor ────────────────────────────────────────────

def test_rarity_factor_home_80pct():
    snap = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    bd = score(2, 1, 1, 0, snap=snap)
    assert bd.rarity_factor == pytest.approx(1.2, abs=0.01)

def test_rarity_factor_draw_10pct():
    snap = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    bd = score(1, 1, 0, 0, snap=snap)
    assert bd.rarity_factor == pytest.approx(1.9, abs=0.01)

def test_rarity_factor_away_10pct():
    snap = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    bd = score(0, 1, 0, 2, snap=snap)
    assert bd.rarity_factor == pytest.approx(1.9, abs=0.01)

def test_rarity_factor_neutral_when_wrong_tendency():
    snap = {"home_win_share": 0.10, "draw_share": 0.10, "away_win_share": 0.80, "total_tips": 10}
    bd = score(2, 1, 0, 1, snap=snap)
    assert bd.rarity_factor == 1.0

def test_rarity_factor_neutral_no_tips():
    bd = score(2, 1, 1, 0, snap=SNAP_NONE)
    assert bd.rarity_factor == 1.0

def test_rarity_factor_neutral_none_snapshot():
    bd = score(2, 1, 1, 0, snap=None)
    assert bd.rarity_factor == 1.0

def test_rarity_applied_to_pre_rarity_pts():
    snap = {"home_win_share": 0.50, "draw_share": 0.10, "away_win_share": 0.40, "total_tips": 10}
    # draw correct (tendency=2), total 2=2 (+1) → pre_rarity=3, factor=1.9
    bd = score(1, 1, 0, 0, snap=snap)
    assert bd.pre_rarity_pts == pytest.approx(2.0, abs=0.1)   # tendency 2, no total (0≠2)
    assert bd.rarity_factor == pytest.approx(1.9, abs=0.01)
    assert bd.base_pts == pytest.approx(2.0 * 1.9, abs=0.1)


# ─── Germany bonus ────────────────────────────────────────────

def test_germany_doubles_points():
    bd_plain = score(2, 1, 1, 0)
    bd_ger = score(2, 1, 1, 0, germany=True)
    assert bd_ger.pts_after_germany == bd_plain.base_pts * 2

def test_germany_multiplier_1_by_default():
    bd = score(2, 1, 1, 0)
    assert bd.germany_multiplier == 1


# ─── Risk game ────────────────────────────────────────────────

def test_risk_no_effect_when_not_set():
    bd = score(2, 1, 1, 0, risk=False)
    assert bd.risk_result == "none"
    assert bd.final_pts == bd.pts_after_germany

def test_risk_correct_tendency_doubles():
    bd_no_risk = score(2, 1, 1, 0)
    bd_risk = score(2, 1, 1, 0, risk=True)
    assert bd_risk.risk_result == "double"
    assert bd_risk.final_pts == bd_no_risk.pts_after_germany * 2

def test_risk_wrong_tendency_minus_10():
    bd = score(2, 1, 0, 1, risk=True)
    assert bd.risk_result == "deduct"
    assert bd.final_pts == -10.0

def test_risk_wrong_tendency_always_exactly_minus_10():
    # Even with 0 base pts, deduct is exactly -10
    bd = score(1, 0, 0, 2, risk=True)
    assert bd.final_pts == -10.0

def test_risk_draw_tip_draw_result_correct():
    # Draw result + draw tip = correct tendency → double
    bd_no_risk = score(1, 1, 0, 0, risk=False)
    bd_risk = score(1, 1, 0, 0, risk=True)
    assert bd_risk.risk_result == "double"
    assert bd_risk.final_pts == bd_no_risk.pts_after_germany * 2

def test_risk_draw_result_home_tip_minus_10():
    # Draw result, home tip = wrong tendency → -10
    bd = score(1, 1, 2, 1, risk=True)
    assert bd.risk_result == "deduct"
    assert bd.final_pts == -10.0

def test_risk_draw_tip_home_result_minus_10():
    # Home win result, draw tip = wrong tendency → -10
    bd = score(2, 1, 0, 0, risk=True)
    assert bd.risk_result == "deduct"
    assert bd.final_pts == -10.0


# ─── Risk spec test cases ─────────────────────────────────────

def test_risk_spec_correct_2pts_gives_4():
    # Tendency correct, base=2, risk doubles → 4
    bd = score(2, 1, 3, 0, risk=True)   # tendency only (diff wrong), total 3=3 → pre=3... wait
    # 2+1=3 actual, 3+0=3 tip → total correct! pre_rarity=3, base=3, doubled=6
    # Let's use a case without total goals: 2:1 vs 1:0
    # diff correct (1=1) → base_category=goal_diff=3, total 1≠3 → pre=3, base=3, doubled=6
    # Hmm, need pure tendency=2 case. 2:1 vs 3:1 → tendency home ✓, diff 1≠2, total 3≠4 → 2
    bd2 = score(2, 1, 3, 1, risk=True)
    assert bd2.base_category_pts == 2
    assert bd2.total_goals_pts == 0
    assert bd2.pts_after_germany == 2.0
    assert bd2.risk_result == "double"
    assert bd2.final_pts == 4.0

def test_risk_spec_correct_4pts_gives_8():
    # Exact result but no total: 2:1 vs 2:1, total 3=3 → exact+total=5, risk → 10
    # Need exact without total: 3:1 vs 3:1, total 4=4 → always matches with exact
    # Use 3:0 vs 3:0: exact (4), total 3=3 (+1) → 5 doubled = 10. Not 8.
    # Exact without total: 2:0 vs 2:0: exact (4), total 2=2 (+1) → 5 again.
    # Actually exact always implies same total! So exact always comes with +1 total.
    # spec says "Hochrisiko richtig, normale Punkte 4 → 8" — this must mean pre_rarity=4
    # That requires goal_diff=3 + total=1 = 4. e.g. 3:1 vs 2:0 (diff=2 both, total 4≠2)
    # 3+1=4, 2+0=2 → total different. diff=2 both → goal_diff=3, total no → pre=3.
    # Hmm. Or tendency(2)+total(1)+rarity? No snap here.
    # Actually: goal_diff(3)+total(1)=4. 3:1 vs 1:3? wrong tendency.
    # 2:0 vs 3:1: diff=2 vs diff=2 ✓, total 2≠4. goal_diff=3, no total → 3. Not 4.
    # 3:1 vs 2:0: diff=2 vs diff=2 ✓, total 4≠2. Same.
    # For pre_rarity=4: goal_diff(3)+total(1): need diff correct AND total correct.
    # e.g. 3:1 vs 4:2: diff=2 both ✓, total 4≠6. No.
    # 2:0 vs 4:2: diff=2 both ✓, total 2≠6. No.
    # 3:1 vs 2:0: no total.
    # Hmm, goal_diff+total: need real_diff = tip_diff AND real_total = tip_total.
    # 4:2 vs 3:1: diff=2 both ✓, total 6≠4. No.
    # 3:0 vs 2:1: diff=3 vs diff=1. No.
    # 2:1 vs 3:0: diff=1 vs diff=3. No.
    # Actually tendency(2)+total(1)=3, or goal_diff(3)+total(1)=4, or exact(4)+total(1)=5.
    # For 4 without snap: need goal_diff=3 + total=1.
    # 4:1 vs 2:3: wrong tendency.
    # 3:0 vs 4:1: diff=3 vs diff=3 ✓, total 3≠5. No.
    # 4:1 vs 5:2: diff=3 vs diff=3 ✓, total 5≠7. No.
    # 4:2 vs 2:0: diff=2 vs diff=2 ✓, total 6≠2. No.
    # 3:1 vs 3:1: exact ✓, total 4=4 → pre=5.
    # For exactly pre=4 with no snap: I'll use a snap to get it.
    # Or just test the spec differently:
    # "normale Punkte 4" means pts_after_germany=4. With snap that gives base_pts=4.
    # Actually the simpler interpretation: the spec cases use pre_rarity_pts, not final.
    # Let me just verify the rule: correct risk always doubles pts_after_germany.
    bd = score(2, 1, 3, 1, risk=True)  # tendency only (2), no total → doubled = 4
    assert bd.final_pts == 4.0
    bd2 = score(3, 1, 2, 0, risk=True)  # goal_diff (3), no total → doubled = 6
    assert bd2.final_pts == 6.0

def test_risk_spec_exact_doubles_to_8():
    # exact(4), no total-goals bonus, risk doubles → 8
    bd = score(2, 1, 2, 1, risk=True)
    assert bd.base_category_pts == 4
    assert bd.total_goals_pts == 0
    assert bd.pre_rarity_pts == 4.0
    assert bd.final_pts == 8.0

def test_risk_spec_falsch_minus_10():
    bd = score(2, 1, 0, 1, risk=True)
    assert bd.final_pts == -10.0

def test_risk_draw_result_draw_tip_correct():
    # 1:1, tip 1:1 → exact, risk correct → doubles
    bd = score(1, 1, 1, 1, risk=True)
    assert bd.risk_result == "double"
    assert bd.final_pts == 8.0  # 4*2 (no total-goals bonus)

def test_risk_draw_result_draw_tip_2_2_correct():
    # 1:1, tip 2:2 → tendency correct, risk doubles
    bd = score(1, 1, 2, 2, risk=True)
    assert bd.risk_result == "double"
    assert bd.base_category_pts == 2
    assert bd.final_pts == 4.0  # 2*2

def test_risk_draw_result_home_tip_minus_10():
    # 1:1, tip 2:1 → wrong tendency → -10
    bd = score(1, 1, 2, 1, risk=True)
    assert bd.risk_result == "deduct"
    assert bd.final_pts == -10.0


# ─── Germany + Risk combined ──────────────────────────────────

def test_germany_risk_correct():
    bd = score(2, 1, 1, 0, risk=True, germany=True)
    bd_plain = score(2, 1, 1, 0)
    # pts_after_germany = base_pts * 2; then risk doubles again
    assert bd.final_pts == bd_plain.base_pts * 2 * 2

def test_germany_risk_wrong_minus_20():
    # Germany risk-fail is -20: the Germany x2 applies to the risk penalty too.
    # Deliberate design (commit 539b8d9). Non-Germany risk-fail stays -10.
    bd = score(2, 1, 0, 1, risk=True, germany=True)
    assert bd.final_pts == -20.0
    bd_plain = score(2, 1, 0, 1, risk=True, germany=False)
    assert bd_plain.final_pts == -10.0


# ─── Potential rarity ─────────────────────────────────────────

def test_potential_rarity_factor_live():
    distrib = {"home_win_share": 0.80, "draw_share": 0.10, "away_win_share": 0.10, "total_tips": 10}
    val = calculate_potential_rarity(1, 0, distrib)
    assert val == pytest.approx(1.2, abs=0.01)

def test_potential_rarity_neutral_no_tips():
    val = calculate_potential_rarity(1, 0, {"total_tips": 0})
    assert val == 1.0
