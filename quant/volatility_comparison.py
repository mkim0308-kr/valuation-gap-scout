"""Realized-vs-implied volatility agent: compares backward-looking realized
volatility (from price history) against the options market's forward-looking
implied volatility (reusing options_market_signal.py). Deterministic, no
LLM — arithmetic on public data, not a forecast.
"""
from __future__ import annotations

import math

import yfinance as yf

from quant.options_market_signal import get_options_market_signal

TRADING_DAYS_PER_YEAR = 252
SHORT_WINDOW_DAYS = 21  # ~1 month, comparable to the ~30-day option expiry used elsewhere
LONG_WINDOW_DAYS = 63  # ~3 months


def compute_realized_volatility(
    closes: list[float], trading_days_per_year: int = TRADING_DAYS_PER_YEAR
) -> float | None:
    """Annualized stdev of daily log returns. None if there aren't enough
    closes to compute at least two returns."""
    closes = [c for c in closes if c and c > 0]
    if len(closes) < 3:
        return None
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    n = len(log_returns)
    mean = sum(log_returns) / n
    variance = sum((r - mean) ** 2 for r in log_returns) / (n - 1)
    return round((variance**0.5) * (trading_days_per_year**0.5), 4)


def compute_volatility_risk_premium(
    implied_vol: float | None, realized_vol: float | None
) -> float | None:
    """Implied - realized. Positive means options are pricing in more
    movement than has actually occurred recently (a common baseline state,
    not itself a signal to act on)."""
    if implied_vol is None or realized_vol is None:
        return None
    return round(implied_vol - realized_vol, 4)


def get_volatility_comparison(ticker: str) -> dict:
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    history = t.history(period="6mo")
    closes = history["Close"].dropna().tolist() if not history.empty else []

    realized_vol_1m = compute_realized_volatility(closes[-(SHORT_WINDOW_DAYS + 1):])
    realized_vol_3m = compute_realized_volatility(closes[-(LONG_WINDOW_DAYS + 1):])

    options_signal = get_options_market_signal(ticker)
    implied_vol = options_signal.get("atm_implied_volatility", {}).get("average")

    return {
        "ticker": ticker,
        "realized_volatility_1m": realized_vol_1m,
        "realized_volatility_3m": realized_vol_3m,
        "implied_volatility_atm": implied_vol,
        "volatility_risk_premium_vs_1m": compute_volatility_risk_premium(
            implied_vol, realized_vol_1m
        ),
        "note": "Volatility risk premium (implied - realized) is a snapshot of current "
        "options pricing relative to recent actual price movement, not a forecast of future "
        "volatility.",
    }
