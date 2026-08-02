"""Agent 1d: Residual Income (Excess Return) Model — a second, independent
fair-value lens alongside DCF. Instead of compounding a projected cash flow
forward, it starts from book value and adds the present value of expected
"excess" returns (ROE above the cost of equity) as a growing perpetuity.
Because it's anchored to today's book value rather than a 5-year compounding
FCF projection, it's far less sensitive to a single aggressive growth
assumption blowing up the terminal value — useful as a cross-check whenever
the DCF shows an extreme premium. Deterministic, no LLM.
"""
from __future__ import annotations

TERMINAL_GROWTH_RATE = 0.025


def compute_residual_income_fair_value(
    book_value_per_share: float | None,
    roe: float | None,
    cost_of_equity: float | None,
    terminal_growth_rate: float = TERMINAL_GROWTH_RATE,
) -> float | None:
    """Single-stage (perpetuity) residual income model:
    V = BV + BV * (ROE - r) / (r - g)
    equivalent to a "justified P/B" of 1 + (ROE - r) / (r - g). None if any
    input is missing, book value isn't positive, or the cost of equity
    doesn't exceed the terminal growth rate (same degenerate-perpetuity
    guard as the DCF's Gordon growth term) — never a guessed value."""
    if None in (book_value_per_share, roe, cost_of_equity):
        return None
    if book_value_per_share <= 0:
        return None
    if cost_of_equity <= terminal_growth_rate:
        return None
    excess_return_spread = roe - cost_of_equity
    fair_value = book_value_per_share * (
        1 + excess_return_spread / (cost_of_equity - terminal_growth_rate)
    )
    return round(fair_value, 2)


def get_residual_income_valuation(
    book_value_per_share: float | None,
    roe: float | None,
    cost_of_equity: float | None,
    current_price: float | None,
    terminal_growth_rate: float = TERMINAL_GROWTH_RATE,
) -> dict:
    fair_value = compute_residual_income_fair_value(
        book_value_per_share, roe, cost_of_equity, terminal_growth_rate
    )
    gap = None
    if fair_value is not None and fair_value > 0 and current_price is not None:
        gap = round((current_price - fair_value) / fair_value, 5)

    return {
        "fair_value_per_share": fair_value,
        "valuation_gap_pct": gap,
        "inputs": {
            "book_value_per_share": book_value_per_share,
            "roe": roe,
            "cost_of_equity": cost_of_equity,
            "terminal_growth_rate": terminal_growth_rate,
        },
        "method": (
            "잔여이익모델(Residual Income / Excess Return Model, 단일단계 영구성장 가정): "
            "V = 장부가치 + 장부가치 × (ROE − 자기자본비용) / (자기자본비용 − 터미널성장률). "
            "DCF처럼 미래 현금흐름을 복리로 투영하지 않고, 현재 ROE가 자기자본비용 대비 "
            "만들어내는 초과수익이 영구히 유지된다고 가정하는 방식이라 단일 성장률 가정에 "
            "덜 민감한 두 번째 독립적 기준점입니다."
        ),
    }
