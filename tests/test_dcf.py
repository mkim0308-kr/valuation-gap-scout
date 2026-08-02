import pytest

from quant.dcf import (
    calculate_fair_value,
    calculate_fair_value_multistage,
    calculate_implied_growth_rate,
    calculate_wacc,
    compute_cost_of_equity,
    valuation_gap,
)


def test_calculate_wacc_matches_manual_capm_calculation():
    # Re/Rd computed by hand: Re = 0.04 + 1.2*0.055 = 0.106
    # Rd = 0.04 + 0.015 credit spread = 0.055
    # WACC = 0.8*0.106 + 0.2*0.055*(1-0.21) = 0.09349
    wacc = calculate_wacc(
        market_cap=800,
        total_debt=200,
        beta=1.2,
        risk_free_rate=0.04,
        effective_tax_rate=0.21,
    )
    assert wacc == pytest.approx(0.09349, rel=1e-4)


def test_calculate_wacc_rejects_zero_capital_structure():
    with pytest.raises(ValueError):
        calculate_wacc(
            market_cap=0,
            total_debt=0,
            beta=1.0,
            risk_free_rate=0.04,
            effective_tax_rate=0.21,
        )


def test_calculate_fair_value_zero_growth_reduces_to_perpetuity():
    # With zero FCF growth and zero terminal growth, the whole 5yr DCF +
    # terminal value telescopes to the closed-form perpetuity FCF/WACC.
    result = calculate_fair_value(
        latest_fcf=100,
        fcf_cagr=0.0,
        wacc=0.10,
        total_debt=0,
        shares_outstanding=100,
        cash_and_equivalents=0,
        terminal_growth_rate=0.0,
    )
    assert result["enterprise_value"] == pytest.approx(1000.0, rel=1e-4)
    assert result["fair_value_per_share"] == pytest.approx(10.0, rel=1e-4)


def test_calculate_fair_value_bridges_debt_and_cash_to_equity_value():
    base = calculate_fair_value(
        latest_fcf=100,
        fcf_cagr=0.0,
        wacc=0.10,
        total_debt=0,
        shares_outstanding=100,
        terminal_growth_rate=0.0,
    )
    with_debt = calculate_fair_value(
        latest_fcf=100,
        fcf_cagr=0.0,
        wacc=0.10,
        total_debt=200,
        shares_outstanding=100,
        terminal_growth_rate=0.0,
    )
    # Same enterprise value, but 200 more debt should reduce equity value by
    # exactly 200 (i.e. $2/share on 100 shares outstanding).
    assert with_debt["enterprise_value"] == pytest.approx(base["enterprise_value"])
    assert base["fair_value_per_share"] - with_debt["fair_value_per_share"] == pytest.approx(2.0)


def test_calculate_fair_value_rejects_wacc_below_terminal_growth():
    with pytest.raises(ValueError):
        calculate_fair_value(
            latest_fcf=100,
            fcf_cagr=0.0,
            wacc=0.02,
            total_debt=0,
            shares_outstanding=100,
            terminal_growth_rate=0.025,
        )


def test_calculate_fair_value_rejects_non_positive_shares():
    with pytest.raises(ValueError):
        calculate_fair_value(
            latest_fcf=100,
            fcf_cagr=0.05,
            wacc=0.10,
            total_debt=0,
            shares_outstanding=0,
        )


def test_calculate_fair_value_caps_runaway_growth_rate():
    exploded = calculate_fair_value(
        latest_fcf=100,
        fcf_cagr=5.0,  # 500% CAGR should be clamped, not taken at face value
        wacc=0.10,
        total_debt=0,
        shares_outstanding=100,
    )
    capped = calculate_fair_value(
        latest_fcf=100,
        fcf_cagr=0.30,  # MAX_GROWTH_RATE
        wacc=0.10,
        total_debt=0,
        shares_outstanding=100,
    )
    assert exploded["fair_value_per_share"] == pytest.approx(capped["fair_value_per_share"])


def test_valuation_gap_sign_matches_premium_or_discount():
    assert valuation_gap(current_price=110, fair_value_per_share=100) == pytest.approx(0.10)
    assert valuation_gap(current_price=90, fair_value_per_share=100) == pytest.approx(-0.10)


def test_compute_cost_of_equity_matches_capm():
    # Re = Rf + Beta * ERP = 0.04 + 1.2*0.055 = 0.106
    assert compute_cost_of_equity(risk_free_rate=0.04, beta=1.2) == pytest.approx(0.106)


def test_calculate_implied_growth_rate_recovers_known_growth_rate():
    # Build a fair value at a known (unclamped) growth rate, then check the
    # reverse search finds that same rate given that price as the target.
    known_growth_rate = 0.15
    target = calculate_fair_value(
        latest_fcf=100,
        fcf_cagr=known_growth_rate,
        wacc=0.10,
        total_debt=0,
        shares_outstanding=100,
    )["fair_value_per_share"]

    result = calculate_implied_growth_rate(
        current_price=target,
        latest_fcf=100,
        wacc=0.10,
        total_debt=0,
        shares_outstanding=100,
    )

    assert result["insufficient_data_reason"] is None
    assert result["implied_growth_rate"] == pytest.approx(known_growth_rate, abs=0.002)


def test_calculate_implied_growth_rate_none_when_fcf_not_positive():
    result = calculate_implied_growth_rate(
        current_price=100, latest_fcf=0, wacc=0.10, total_debt=0, shares_outstanding=100
    )
    assert result["implied_growth_rate"] is None
    assert "FCF" in result["insufficient_data_reason"]


def test_calculate_implied_growth_rate_none_when_wacc_below_terminal_growth():
    result = calculate_implied_growth_rate(
        current_price=100,
        latest_fcf=100,
        wacc=0.02,
        total_debt=0,
        shares_outstanding=100,
        terminal_growth_rate=0.025,
    )
    assert result["implied_growth_rate"] is None
    assert "WACC" in result["insufficient_data_reason"]


def test_calculate_implied_growth_rate_none_when_price_below_lower_bound_fair_value():
    result = calculate_implied_growth_rate(
        current_price=0.01, latest_fcf=100, wacc=0.10, total_debt=0, shares_outstanding=100
    )
    assert result["implied_growth_rate"] is None
    assert result["insufficient_data_reason"] is not None


def test_calculate_implied_growth_rate_none_when_price_exceeds_search_bounds():
    result = calculate_implied_growth_rate(
        current_price=1e15, latest_fcf=100, wacc=0.10, total_debt=0, shares_outstanding=100
    )
    assert result["implied_growth_rate"] is None
    assert "불가능" in result["insufficient_data_reason"]


def test_calculate_fair_value_multistage_zero_growth_reduces_to_perpetuity():
    result = calculate_fair_value_multistage(
        latest_fcf=100,
        near_term_growth_rate=0.0,
        wacc=0.10,
        total_debt=0,
        shares_outstanding=100,
        cash_and_equivalents=0,
        terminal_growth_rate=0.0,
    )
    assert result["enterprise_value"] == pytest.approx(1000.0, rel=1e-4)
    assert result["fair_value_per_share"] == pytest.approx(10.0, rel=1e-4)
    assert result["growth_rate_schedule"] == [pytest.approx(0.0)] * 5


def test_calculate_fair_value_multistage_fades_growth_rate_to_terminal():
    result = calculate_fair_value_multistage(
        latest_fcf=100,
        near_term_growth_rate=0.20,
        wacc=0.15,
        total_debt=0,
        shares_outstanding=100,
        terminal_growth_rate=0.025,
        fade_start_year=2,
    )
    # abs=1e-5 to account for the source's round(r, 5) on each schedule entry
    schedule = result["growth_rate_schedule"]
    assert schedule[0] == pytest.approx(0.20, abs=1e-5)
    assert schedule[1] == pytest.approx(0.20, abs=1e-5)
    assert schedule[2] == pytest.approx(0.20 + (0.025 - 0.20) * (1 / 3), abs=1e-5)
    assert schedule[3] == pytest.approx(0.20 + (0.025 - 0.20) * (2 / 3), abs=1e-5)
    assert schedule[4] == pytest.approx(0.025, abs=1e-5)  # final year lands exactly on terminal


def test_calculate_fair_value_multistage_no_fade_when_fade_start_at_horizon():
    result = calculate_fair_value_multistage(
        latest_fcf=100,
        near_term_growth_rate=0.20,
        wacc=0.15,
        total_debt=0,
        shares_outstanding=100,
        terminal_growth_rate=0.025,
        fade_start_year=5,
    )
    assert result["growth_rate_schedule"] == [pytest.approx(0.20)] * 5


def test_calculate_fair_value_multistage_clamps_runaway_near_term_growth_rate():
    exploded = calculate_fair_value_multistage(
        latest_fcf=100,
        near_term_growth_rate=5.0,  # 500% should be clamped to MAX_GROWTH_RATE
        wacc=0.15,
        total_debt=0,
        shares_outstanding=100,
        fade_start_year=5,
    )
    capped = calculate_fair_value_multistage(
        latest_fcf=100,
        near_term_growth_rate=0.30,
        wacc=0.15,
        total_debt=0,
        shares_outstanding=100,
        fade_start_year=5,
    )
    assert exploded["fair_value_per_share"] == pytest.approx(capped["fair_value_per_share"])


def test_calculate_fair_value_multistage_none_growth_rate_falls_back_to_terminal():
    result = calculate_fair_value_multistage(
        latest_fcf=100,
        near_term_growth_rate=None,
        wacc=0.15,
        total_debt=0,
        shares_outstanding=100,
        terminal_growth_rate=0.025,
    )
    assert result["near_term_growth_rate_used"] == pytest.approx(0.025)
    assert all(r == pytest.approx(0.025) for r in result["growth_rate_schedule"])


def test_calculate_fair_value_multistage_rejects_wacc_below_terminal_growth():
    with pytest.raises(ValueError):
        calculate_fair_value_multistage(
            latest_fcf=100,
            near_term_growth_rate=0.1,
            wacc=0.02,
            total_debt=0,
            shares_outstanding=100,
            terminal_growth_rate=0.025,
        )


def test_calculate_fair_value_multistage_rejects_non_positive_shares():
    with pytest.raises(ValueError):
        calculate_fair_value_multistage(
            latest_fcf=100,
            near_term_growth_rate=0.1,
            wacc=0.1,
            total_debt=0,
            shares_outstanding=0,
        )


def test_calculate_fair_value_multistage_rejects_invalid_fade_start_year():
    with pytest.raises(ValueError):
        calculate_fair_value_multistage(
            latest_fcf=100,
            near_term_growth_rate=0.1,
            wacc=0.1,
            total_debt=0,
            shares_outstanding=100,
            fade_start_year=0,
        )
    with pytest.raises(ValueError):
        calculate_fair_value_multistage(
            latest_fcf=100,
            near_term_growth_rate=0.1,
            wacc=0.1,
            total_debt=0,
            shares_outstanding=100,
            fade_start_year=6,
        )
