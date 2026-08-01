import pytest

from quant.balance_sheet_health import (
    compute_altman_z_score,
    compute_current_ratio,
    compute_debt_to_ebitda,
    compute_interest_coverage_ratio,
)


def test_compute_altman_z_score_matches_known_calculation():
    # WC/TA=0.1, RE/TA=0.2, EBIT/TA=0.15, MVE/TL=2.0, Sales/TA=0.8
    # Z = 1.2*0.1 + 1.4*0.2 + 3.3*0.15 + 0.6*2.0 + 1.0*0.8
    z = compute_altman_z_score(
        working_capital=100, retained_earnings=200, ebit=150,
        market_cap=1000, total_liabilities=500, sales=800, total_assets=1000,
    )
    expected = 1.2 * 0.1 + 1.4 * 0.2 + 3.3 * 0.15 + 0.6 * 2.0 + 1.0 * 0.8
    assert z == pytest.approx(expected, abs=0.0001)


def test_compute_altman_z_score_none_when_missing_inputs():
    assert compute_altman_z_score(None, 200, 150, 1000, 500, 800, 1000) is None
    assert compute_altman_z_score(100, 200, 150, 1000, 0, 800, 1000) is None
    assert compute_altman_z_score(100, 200, 150, 1000, 500, 800, 0) is None


def test_compute_interest_coverage_ratio_matches_known_calculation():
    assert compute_interest_coverage_ratio(ebit=300, interest_expense=-100) == 3.0
    assert compute_interest_coverage_ratio(ebit=300, interest_expense=100) == 3.0


def test_compute_interest_coverage_ratio_none_without_interest_expense():
    assert compute_interest_coverage_ratio(300, None) is None
    assert compute_interest_coverage_ratio(300, 0) is None


def test_compute_current_ratio_matches_known_calculation():
    assert compute_current_ratio(current_assets=150, current_liabilities=100) == 1.5


def test_compute_current_ratio_none_without_current_liabilities():
    assert compute_current_ratio(150, None) is None
    assert compute_current_ratio(150, 0) is None


def test_compute_debt_to_ebitda_matches_known_calculation():
    assert compute_debt_to_ebitda(total_debt=200, ebitda=100) == 2.0


def test_compute_debt_to_ebitda_none_for_non_positive_ebitda():
    assert compute_debt_to_ebitda(200, 0) is None
    assert compute_debt_to_ebitda(200, -50) is None
    assert compute_debt_to_ebitda(200, None) is None
