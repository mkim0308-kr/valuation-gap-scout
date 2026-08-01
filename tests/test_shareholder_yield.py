import pytest

from quant.shareholder_yield import compute_buyback_yield, compute_total_shareholder_yield


def test_compute_buyback_yield_matches_known_calculation():
    assert compute_buyback_yield(buyback_spend=50, market_cap=1000) == 0.05


def test_compute_buyback_yield_none_when_missing_data():
    assert compute_buyback_yield(None, 1000) is None
    assert compute_buyback_yield(50, None) is None
    assert compute_buyback_yield(50, 0) is None


def test_compute_total_shareholder_yield_sums_both_legs():
    assert compute_total_shareholder_yield(0.005, 0.02) == pytest.approx(0.025)


def test_compute_total_shareholder_yield_treats_missing_leg_as_zero():
    assert compute_total_shareholder_yield(None, 0.02) == 0.02
    assert compute_total_shareholder_yield(0.005, None) == 0.005


def test_compute_total_shareholder_yield_none_when_both_missing():
    assert compute_total_shareholder_yield(None, None) is None
