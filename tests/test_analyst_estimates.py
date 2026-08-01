import pytest

from quant.analyst_estimates import (
    compute_recommendation_mean_score,
    compute_target_implied_upside_pct,
)


def test_compute_target_implied_upside_pct_matches_known_calculation():
    # (110 - 100) / 100 * 100 = 10.0
    assert compute_target_implied_upside_pct(current_price=100, target_price=110) == 10.0


def test_compute_target_implied_upside_pct_negative_when_target_below_price():
    assert compute_target_implied_upside_pct(current_price=100, target_price=90) == -10.0


def test_compute_target_implied_upside_pct_none_when_missing_data():
    assert compute_target_implied_upside_pct(None, 110) is None
    assert compute_target_implied_upside_pct(100, None) is None
    assert compute_target_implied_upside_pct(100, 0) is None


def test_compute_recommendation_mean_score_unanimous_strong_buy():
    counts = {"strongBuy": 10, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}
    assert compute_recommendation_mean_score(counts) == 1.0


def test_compute_recommendation_mean_score_unanimous_strong_sell():
    counts = {"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 10}
    assert compute_recommendation_mean_score(counts) == 5.0


def test_compute_recommendation_mean_score_mixed():
    # 1*6 + 2*22 + 3*14 + 4*2 + 5*2 = 6+44+42+8+10 = 110; total=46; 110/46
    counts = {"strongBuy": 6, "buy": 22, "hold": 14, "sell": 2, "strongSell": 2}
    assert compute_recommendation_mean_score(counts) == pytest.approx(110 / 46, abs=0.001)


def test_compute_recommendation_mean_score_none_when_no_ratings():
    counts = {"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}
    assert compute_recommendation_mean_score(counts) is None
