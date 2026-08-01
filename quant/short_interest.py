"""Short-interest agent: how much of the float is sold short, and whether
that's rising or falling month over month. Deterministic, no LLM.
"""
from __future__ import annotations

import yfinance as yf


def compute_short_interest_change_pct(
    shares_short: float | None, shares_short_prior_month: float | None
) -> float | None:
    if shares_short is None or not shares_short_prior_month:
        return None
    return round((shares_short - shares_short_prior_month) / shares_short_prior_month * 100, 2)


def get_short_interest_metrics(ticker: str) -> dict:
    t = yf.Ticker(ticker.upper())
    info = t.get_info()

    shares_short = info.get("sharesShort")
    shares_short_prior_month = info.get("sharesShortPriorMonth")

    return {
        "ticker": ticker.upper(),
        "short_ratio_days_to_cover": info.get("shortRatio"),
        "short_pct_of_float": info.get("shortPercentOfFloat"),
        "shares_short": shares_short,
        "shares_short_prior_month": shares_short_prior_month,
        "short_interest_change_pct": compute_short_interest_change_pct(
            shares_short, shares_short_prior_month
        ),
        "note": "Short-ratio (days to cover) and float% figures are exchange-reported "
        "monthly, so they can lag by several weeks — this is a positioning snapshot, not a "
        "real-time read.",
    }
