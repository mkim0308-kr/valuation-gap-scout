import pytest

from quant.dcf import calculate_fair_value, calculate_wacc, valuation_gap


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
