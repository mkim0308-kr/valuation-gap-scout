"""Dynamic WACC and 5-year DCF fair value calculation.

Pure arithmetic, no LLM involved — this is the "hard data" layer the LLM
agents read from, so their output can't drift from what was actually computed.
"""
from __future__ import annotations

TERMINAL_GROWTH_RATE = 0.025  # long-run GDP-ish growth assumption for terminal value
PROJECTION_YEARS = 5
MAX_GROWTH_RATE = 0.30  # sanity cap so a noisy historical CAGR can't blow up the model
MIN_GROWTH_RATE = -0.10


def compute_cost_of_equity(
    risk_free_rate: float, beta: float, equity_risk_premium: float = 0.055
) -> float:
    """CAPM cost of equity: Re = Rf + Beta * Equity Risk Premium. Broken out
    from calculate_wacc so residual_income.py can reuse the same Re without
    duplicating the formula."""
    return risk_free_rate + beta * equity_risk_premium


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

    cost_of_equity = compute_cost_of_equity(risk_free_rate, beta, equity_risk_premium)

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


def _fair_value_per_share_for_growth_rate(
    latest_fcf: float,
    growth_rate: float,
    wacc: float,
    total_debt: float,
    shares_outstanding: float,
    cash_and_equivalents: float = 0.0,
    terminal_growth_rate: float = TERMINAL_GROWTH_RATE,
) -> float:
    """Same projection math as calculate_fair_value, but takes growth_rate
    directly with no CAGR/clamping — the search primitive for
    calculate_implied_growth_rate. Kept as a separate function (rather than
    refactoring calculate_fair_value to call it) so the already-tested
    calculate_fair_value body stays untouched."""
    fcf = latest_fcf
    pv_fcfs = 0.0
    for year in range(1, PROJECTION_YEARS + 1):
        fcf = fcf * (1 + growth_rate)
        pv_fcfs += fcf / ((1 + wacc) ** year)

    terminal_value = fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    pv_terminal_value = terminal_value / ((1 + wacc) ** PROJECTION_YEARS)

    enterprise_value = pv_fcfs + pv_terminal_value
    equity_value = enterprise_value - total_debt + cash_and_equivalents
    return equity_value / shares_outstanding


def calculate_implied_growth_rate(
    current_price: float,
    latest_fcf: float,
    wacc: float,
    total_debt: float,
    shares_outstanding: float,
    cash_and_equivalents: float = 0.0,
    terminal_growth_rate: float = TERMINAL_GROWTH_RATE,
    search_lower_bound: float = -0.5,
    search_upper_bound: float = 3.0,
    tolerance: float = 1e-4,
    max_iterations: int = 100,
) -> dict:
    """Reverse-solves the same DCF for the (unclamped) 5-year growth rate
    that would make fair_value_per_share equal current_price — i.e. "what
    growth rate is the market pricing in?" Reframes a large valuation_gap_pct
    (which can look alarming, e.g. +3000%) into a comparable growth-rate
    question: is that implied rate plausible next to historical CAGR or
    analyst estimates?

    Bisection search, since fair value is monotonically increasing in
    growth_rate. Returns {"implied_growth_rate": float|None,
    "insufficient_data_reason": str|None} — never a fabricated number: None
    with a reason if latest_fcf isn't positive, or if no rate within the
    search bounds reaches (or is already exceeded by) current_price.
    """
    if latest_fcf is None or latest_fcf <= 0:
        return {
            "implied_growth_rate": None,
            "insufficient_data_reason": "latest FCF가 0 이하라 성장률 역산이 정의되지 않음",
        }
    if wacc <= terminal_growth_rate:
        return {
            "implied_growth_rate": None,
            "insufficient_data_reason": "WACC가 터미널 성장률 이하라 역산 불가",
        }

    def fair_value_at(g: float) -> float:
        return _fair_value_per_share_for_growth_rate(
            latest_fcf, g, wacc, total_debt, shares_outstanding,
            cash_and_equivalents, terminal_growth_rate,
        )

    lo, hi = search_lower_bound, search_upper_bound
    fv_lo, fv_hi = fair_value_at(lo), fair_value_at(hi)

    if current_price <= fv_lo:
        return {
            "implied_growth_rate": None,
            "insufficient_data_reason": (
                f"{search_lower_bound * 100:.0f}% 이하의 성장률에서도 이미 현재가를 넘어서는 "
                "적정가가 나와, 구체적인 역산 성장률을 특정하기 어려움 (매우 낮은 성장 가정에서도 "
                "현재가가 정당화되는 구간)"
            ),
        }
    if current_price > fv_hi:
        return {
            "implied_growth_rate": None,
            "insufficient_data_reason": (
                f"현재가를 정당화하려면 연 {search_upper_bound * 100:.0f}%를 넘는 성장률이 "
                "필요해, 이 모델의 탐색 범위로는 합리적인 역산이 불가능함"
            ),
        }

    for _ in range(max_iterations):
        mid = (lo + hi) / 2
        if fair_value_at(mid) < current_price:
            lo = mid
        else:
            hi = mid
        if hi - lo < tolerance:
            break

    return {"implied_growth_rate": round((lo + hi) / 2, 4), "insufficient_data_reason": None}
