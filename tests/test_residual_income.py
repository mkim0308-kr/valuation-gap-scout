import pytest

from quant.residual_income import (
    compute_residual_income_fair_value,
    get_residual_income_valuation,
)


def test_compute_residual_income_fair_value_matches_known_calculation():
    # V = 20 + 20*(0.20-0.10)/(0.10-0.025) = 20 + 2/0.075 = 46.6667
    value = compute_residual_income_fair_value(
        book_value_per_share=20, roe=0.20, cost_of_equity=0.10, terminal_growth_rate=0.025
    )
    assert value == pytest.approx(46.67, abs=0.01)


def test_compute_residual_income_fair_value_below_book_value_when_roe_under_cost_of_equity():
    # A company earning less than its cost of equity should be worth less
    # than book value, not more.
    value = compute_residual_income_fair_value(
        book_value_per_share=20, roe=0.05, cost_of_equity=0.10, terminal_growth_rate=0.025
    )
    assert value < 20


@pytest.mark.parametrize(
    "book_value,roe,cost_of_equity",
    [
        (None, 0.20, 0.10),
        (20, None, 0.10),
        (20, 0.20, None),
        (0, 0.20, 0.10),
        (-5, 0.20, 0.10),
        (20, 0.20, 0.02),  # cost_of_equity <= terminal_growth_rate (0.025)
    ],
)
def test_compute_residual_income_fair_value_none_for_invalid_inputs(book_value, roe, cost_of_equity):
    assert compute_residual_income_fair_value(book_value, roe, cost_of_equity) is None


def test_get_residual_income_valuation_computes_gap():
    result = get_residual_income_valuation(
        book_value_per_share=20, roe=0.20, cost_of_equity=0.10, current_price=56.0
    )
    assert result["fair_value_per_share"] == pytest.approx(46.67, abs=0.01)
    assert result["valuation_gap_pct"] == pytest.approx((56.0 - 46.67) / 46.67, abs=0.001)
    assert "잔여이익모델" in result["method"]


def test_get_residual_income_valuation_insufficient_data_when_inputs_missing():
    result = get_residual_income_valuation(
        book_value_per_share=None, roe=0.20, cost_of_equity=0.10, current_price=56.0
    )
    assert result["fair_value_per_share"] is None
    assert result["valuation_gap_pct"] is None
