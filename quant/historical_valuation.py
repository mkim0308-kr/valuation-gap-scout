"""Historical price-positioning agent. Deterministic, no LLM.

Honest scope note: this is a **price-range percentile**, not a re-computed
historical DCF-gap percentile. Recomputing the DCF fair value at every past
date would need historical fundamentals we don't have; presenting a price
percentile as if it were a valuation percentile would overclaim precision.
This module says exactly what it measures — where today's price sits within
its own trailing price history — and nothing more.
"""
from __future__ import annotations

import statistics

import yfinance as yf


def compute_price_percentile(current_price: float | None, historical_prices: list[float]) -> dict:
    """Where `current_price` ranks within `historical_prices` (0 = at the
    historical low, 100 = at or above the historical high)."""
    historical_prices = [p for p in historical_prices if p is not None]
    if current_price is None or not historical_prices:
        return {
            "percentile": None, "min": None, "max": None, "median": None,
        }

    percentile = round(
        100 * sum(1 for p in historical_prices if current_price >= p) / len(historical_prices), 1
    )
    return {
        "percentile": percentile,
        "min": round(min(historical_prices), 2),
        "max": round(max(historical_prices), 2),
        "median": round(statistics.median(historical_prices), 2),
    }


def get_historical_valuation_context(ticker: str, years: int = 5) -> dict:
    t = yf.Ticker(ticker.upper())
    history = t.history(period=f"{years}y")

    if history.empty:
        return {
            "ticker": ticker.upper(),
            "note": "insufficient_data — no historical price data returned",
        }

    closes = history["Close"].dropna().tolist()
    current_price = closes[-1] if closes else None

    five_year_position = compute_price_percentile(current_price, closes)

    info = t.get_info()
    fifty_two_week_high = info.get("fiftyTwoWeekHigh")
    fifty_two_week_low = info.get("fiftyTwoWeekLow")
    fifty_two_week_position = None
    if current_price is not None and fifty_two_week_high and fifty_two_week_low:
        band = fifty_two_week_high - fifty_two_week_low
        if band > 0:
            fifty_two_week_position = round(
                100 * (current_price - fifty_two_week_low) / band, 1
            )

    return {
        "ticker": ticker.upper(),
        "current_price": round(current_price, 2) if current_price is not None else None,
        f"{years}yr_price_percentile": five_year_position,
        "52wk_range_position_pct": {
            "value": fifty_two_week_position,
            "fifty_two_week_high": fifty_two_week_high,
            "fifty_two_week_low": fifty_two_week_low,
            "method": "0 = at 52wk low, 100 = at 52wk high",
        },
        "scope_note": "This is a price-range percentile (where today's price sits within "
        "its own trailing history), not a recomputed historical valuation-gap percentile — "
        "that would require historical fundamentals not available here.",
    }
