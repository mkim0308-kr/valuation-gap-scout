"""Dynamic WACC and 5-year DCF fair value calculation.

Pure arithmetic, no LLM involved — this is the "hard data" layer the LLM
agents read from, so their output can't drift from what was actually computed.
"""
from __future__ import annotations

TERMINAL_GROWTH_RATE = 0.025  # long-run GDP-ish growth assumption for terminal value
PROJECTION_YEARS = 5
MAX_GROWTH_RATE = 0.30  # sanity cap so a noisy historical CAGR can't blow up the model
MIN_GROWTH_RATE = -0.10


def calculate_wacc(
    market_cap: float,
    total_debt: float,
    beta: float,
    risk_free_rate: float,
    effective_tax_rate: float,
    equity_risk_premium: float = 0.055,
) -> float:
    """WACC = (E/V)*Re + (D/V)*Rd*(1-Tc)

    Re (cost of equity) via CAPM. Rd (cost of debt) approximated as the
    risk-free rate plus a flat credit spread, since per-issuer bond yields
    aren't available from this data source.
    """
    equity_value = market_cap
    debt_value = total_debt
    total_value = equity_value + debt_value
    if total_value <= 0:
        raise ValueError("market_cap + total_debt must be positive")

    cost_of_equity = risk_free_rate + beta * equity_risk_premium

    credit_spread = 0.015
    cost_of_debt = risk_free_rate + credit_spread

    weight_equity = equity_value / total_value
    weight_debt = debt_value / total_value

    wacc = (weight_equity * cost_of_equity) + (
        weight_debt * cost_of_debt * (1 - effective_tax_rate)
    )
    return round(wacc, 5)


def _bounded_growth_rate(fcf_cagr: float | None) -> float:
    if fcf_cagr is None:
        return TERMINAL_GROWTH_RATE
    return max(MIN_GROWTH_RATE, min(MAX_GROWTH_RATE, fcf_cagr))


def calculate_fair_value(
    latest_fcf: float,
    fcf_cagr: float | None,
    wacc: float,
    total_debt: float,
    shares_outstanding: float,
    cash_and_equivalents: float = 0.0,
    terminal_growth_rate: float = TERMINAL_GROWTH_RATE,
) -> dict:
    """Projects FCF forward, discounts at WACC, adds a Gordon-growth terminal
    value, then bridges enterprise value to equity value per share."""
    if wacc <= terminal_growth_rate:
        raise ValueError("WACC must exceed the terminal growth rate")
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive")

    growth_rate = _bounded_growth_rate(fcf_cagr)

    projected_fcfs = []
    fcf = latest_fcf
    for _ in range(PROJECTION_YEARS):
        fcf = fcf * (1 + growth_rate)
        projected_fcfs.append(fcf)

    pv_fcfs = [
        cf / ((1 + wacc) ** year)
        for year, cf in enumerate(projected_fcfs, start=1)
    ]

    terminal_value = (
        projected_fcfs[-1] * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    )
    pv_terminal_value = terminal_value / ((1 + wacc) ** PROJECTION_YEARS)

    enterprise_value = sum(pv_fcfs) + pv_terminal_value
    equity_value = enterprise_value - total_debt + cash_and_equivalents
    fair_value_per_share = equity_value / shares_outstanding

    return {
        "growth_rate_used": round(growth_rate, 5),
        "projected_fcfs": [round(v, 2) for v in projected_fcfs],
        "enterprise_value": round(enterprise_value, 2),
        "equity_value": round(equity_value, 2),
        "fair_value_per_share": round(fair_value_per_share, 2),
    }


def valuation_gap(current_price: float, fair_value_per_share: float) -> float:
    """Positive => current price trades at a premium to the DCF fair value.
    Negative => current price trades at a discount."""
    if fair_value_per_share <= 0:
        raise ValueError("fair_value_per_share must be positive")
    return round((current_price - fair_value_per_share) / fair_value_per_share, 5)
