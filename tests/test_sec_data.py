import pytest

from quant.sec_data import (
    _derive_single_quarter_series,
    _period_values_from_concept,
    compute_cagr,
    compute_quarterly_cagr,
    compute_ttm_series,
    compute_ttm_trend_growth_rate,
)


def test_compute_cagr_basic():
    series = {2016: 100.0, 2026: 100.0 * (1.1**10)}
    assert compute_cagr(series) == pytest.approx(0.10, rel=1e-6)


def test_compute_cagr_needs_at_least_two_points():
    assert compute_cagr({2026: 100.0}) is None
    assert compute_cagr({}) is None


def test_compute_cagr_rejects_non_positive_endpoints():
    assert compute_cagr({2016: -50.0, 2026: 100.0}) is None
    assert compute_cagr({2016: 50.0, 2026: -100.0}) is None


def _fact(fy, fp, val, form="10-Q", filed="2024-01-01"):
    return {"fy": fy, "fp": fp, "val": val, "form": form, "filed": filed}


def test_period_values_from_concept_extracts_quarterly_and_annual_facts():
    concept = {
        "units": {
            "USD": [
                _fact(2024, "Q1", 10, form="10-Q"),
                _fact(2024, "Q2", 25, form="10-Q"),
                _fact(2024, "FY", 100, form="10-K"),
            ]
        }
    }
    assert _period_values_from_concept(concept) == {
        (2024, "Q1"): 10,
        (2024, "Q2"): 25,
        (2024, "FY"): 100,
    }


def test_period_values_from_concept_ignores_irrelevant_forms_and_periods():
    concept = {
        "units": {
            "USD": [
                _fact(2024, "Q1", 10, form="8-K"),  # wrong form
                _fact(2024, None, 20, form="10-Q"),  # missing fp
                _fact(None, "Q1", 30, form="10-Q"),  # missing fy
            ]
        }
    }
    assert _period_values_from_concept(concept) == {}


def test_period_values_from_concept_keeps_latest_filed_on_restatement():
    concept = {
        "units": {
            "USD": [
                _fact(2024, "Q1", 10, filed="2024-04-01"),
                _fact(2024, "Q1", 11, filed="2024-07-01"),  # restated later
            ]
        }
    }
    assert _period_values_from_concept(concept) == {(2024, "Q1"): 11}


def test_derive_single_quarter_series_differences_ytd_figures():
    # Q1=10 (already single-quarter), Q2 YTD=25 -> Q2=15, Q3 YTD=45 -> Q3=20,
    # FY=100 -> Q4 = 100-45 = 55
    period_values = {
        (2024, "Q1"): 10,
        (2024, "Q2"): 25,
        (2024, "Q3"): 45,
        (2024, "FY"): 100,
    }
    result = _derive_single_quarter_series(period_values)
    assert result == {
        (2024, "Q1"): 10,
        (2024, "Q2"): 15,
        (2024, "Q3"): 20,
        (2024, "Q4"): 55,
    }


def test_derive_single_quarter_series_skips_quarters_missing_required_inputs():
    # Q2 missing entirely -> Q2 not derivable (needs Q1+Q2), Q3 not derivable
    # (needs Q2+Q3). Q4 is still derivable since it only needs Q3 YTD + FY,
    # not Q2.
    period_values = {(2024, "Q1"): 10, (2024, "Q3"): 45, (2024, "FY"): 100}
    result = _derive_single_quarter_series(period_values)
    assert result == {(2024, "Q1"): 10, (2024, "Q4"): 55}


def test_derive_single_quarter_series_handles_annual_only_gap_year():
    # A year with only FY (no Q1/Q2/Q3, e.g. an NVDA-style annual-only gap)
    # never produces a fabricated Q4 — nothing derivable without Q3.
    period_values = {(2015, "FY"): 500}
    assert _derive_single_quarter_series(period_values) == {}


def test_compute_ttm_series_sums_four_consecutive_quarters():
    quarterly = {
        "2024-Q1": 10,
        "2024-Q2": 20,
        "2024-Q3": 30,
        "2024-Q4": 40,
        "2025-Q1": 15,
    }
    result = compute_ttm_series(quarterly)
    assert result == {
        "2024-Q4": 100,  # Q1+Q2+Q3+Q4 2024
        "2025-Q1": 105,  # Q2 2024 + Q3 2024 + Q4 2024 + Q1 2025
    }


def test_compute_ttm_series_breaks_across_a_gap_in_the_quarter_sequence():
    # 2024-Q2 is missing. No TTM should bridge across that hole (2025-Q1's
    # window would need 2024-Q2), but a later window that lands entirely
    # after the gap (2024-Q3..2025-Q2) is still valid.
    quarterly = {
        "2024-Q1": 10,
        "2024-Q3": 30,
        "2024-Q4": 40,
        "2025-Q1": 15,
        "2025-Q2": 25,
    }
    result = compute_ttm_series(quarterly)
    assert "2025-Q1" not in result  # would need Q2-Q4 2024 + Q1 2025, but Q2 missing
    assert result == {"2025-Q2": 110}  # 30+40+15+25, entirely past the gap


def test_compute_ttm_series_empty_input():
    assert compute_ttm_series({}) == {}


def test_compute_quarterly_cagr_matches_known_calculation():
    # Exactly 4 quarters apart (1 year): 100 -> 110 is a 10% annualized rate.
    ttm = {"2024-Q4": 100.0, "2025-Q4": 110.0}
    assert compute_quarterly_cagr(ttm) == pytest.approx(0.10, rel=1e-6)


def test_compute_quarterly_cagr_annualizes_over_multi_year_span():
    # 8 quarters apart (2 years): 100 -> 121 is 10% annualized.
    ttm = {"2023-Q4": 100.0, "2025-Q4": 121.0}
    assert compute_quarterly_cagr(ttm) == pytest.approx(0.10, rel=1e-6)


def test_compute_quarterly_cagr_needs_at_least_two_points():
    assert compute_quarterly_cagr({"2024-Q4": 100.0}) is None
    assert compute_quarterly_cagr({}) is None


def test_compute_quarterly_cagr_rejects_non_positive_endpoints():
    assert compute_quarterly_cagr({"2024-Q4": -50.0, "2025-Q4": 100.0}) is None
    assert compute_quarterly_cagr({"2024-Q4": 50.0, "2025-Q4": -100.0}) is None


def test_compute_ttm_trend_growth_rate_recovers_exact_rate_for_perfect_exponential_series():
    # Perfectly exponential growth at 10%/yr -> regression recovers exactly 10%.
    ttm = {"2023-Q4": 100.0, "2024-Q4": 110.0, "2025-Q4": 121.0}
    assert compute_ttm_trend_growth_rate(ttm) == pytest.approx(0.10, rel=1e-6)


def test_compute_ttm_trend_growth_rate_matches_two_point_cagr_with_only_two_points():
    # A line through 2 points has no other slope to find, so the regression
    # should degrade to exactly the same answer as the simple endpoint CAGR.
    ttm = {"2024-Q4": 100.0, "2025-Q4": 110.0}
    assert compute_ttm_trend_growth_rate(ttm) == pytest.approx(compute_quarterly_cagr(ttm), rel=1e-9)


def test_compute_ttm_trend_growth_rate_less_skewed_by_a_late_outlier_than_endpoint_cagr():
    # Flat for 3 years, then a sudden jump only at the very last point — the
    # regression is pulled down by the 3 flat years and should land below
    # what a naive first-vs-last 2-point CAGR would say.
    ttm = {"2022-Q4": 100.0, "2023-Q4": 100.0, "2024-Q4": 100.0, "2025-Q4": 200.0}
    trend_rate = compute_ttm_trend_growth_rate(ttm)
    endpoint_rate = compute_quarterly_cagr(ttm)
    assert trend_rate < endpoint_rate
    assert trend_rate == pytest.approx(0.2311, abs=0.001)


def test_compute_ttm_trend_growth_rate_needs_at_least_two_points():
    assert compute_ttm_trend_growth_rate({"2024-Q4": 100.0}) is None
    assert compute_ttm_trend_growth_rate({}) is None


def test_compute_ttm_trend_growth_rate_rejects_non_positive_values():
    assert compute_ttm_trend_growth_rate({"2024-Q4": -50.0, "2025-Q4": 100.0}) is None
    assert compute_ttm_trend_growth_rate({"2024-Q4": 50.0, "2025-Q4": -100.0}) is None
