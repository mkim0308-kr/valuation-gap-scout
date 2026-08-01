"""Options-market signal agent: implied volatility and put/call ratios as a
market-implied risk read. Deterministic, no LLM — pure data pull plus
arithmetic on the public option chain, not a forecast.
"""
from __future__ import annotations

from datetime import date, datetime

import yfinance as yf

TARGET_DAYS_TO_EXPIRY = 30  # prefer a ~monthly expiration over 0-2 DTE, which has noisy IV


def compute_put_call_ratio(put_total: float | None, call_total: float | None) -> float | None:
    """Volume or open-interest based put/call ratio. >1 means more put than
    call activity (often read as bearish-leaning hedging demand); <1 the
    reverse. None if there's no call-side activity to divide by."""
    if put_total is None or not call_total:
        return None
    return round(put_total / call_total, 3)


def find_nearest_expiration(expirations: list[str], today: date) -> str | None:
    """Picks the expiration closest to TARGET_DAYS_TO_EXPIRY days out."""
    if not expirations:
        return None
    return min(
        expirations,
        key=lambda e: abs(
            (datetime.strptime(e, "%Y-%m-%d").date() - today).days - TARGET_DAYS_TO_EXPIRY
        ),
    )


def find_atm_strike(strikes: list[float], current_price: float) -> float | None:
    if not strikes or current_price is None:
        return None
    return min(strikes, key=lambda s: abs(s - current_price))


def get_options_market_signal(ticker: str) -> dict:
    t = yf.Ticker(ticker.upper())
    expirations = t.options

    if not expirations:
        return {"ticker": ticker.upper(), "note": "insufficient_data — no listed options found"}

    expiry = find_nearest_expiration(list(expirations), date.today())
    chain = t.option_chain(expiry)
    calls, puts = chain.calls, chain.puts

    current_price = t.get_info().get("currentPrice") or t.get_info().get("regularMarketPrice")
    atm_strike = find_atm_strike(calls["strike"].tolist(), current_price) if current_price else None

    atm_call_iv = None
    atm_put_iv = None
    if atm_strike is not None:
        call_row = calls.loc[calls["strike"] == atm_strike]
        put_row = puts.loc[puts["strike"] == atm_strike]
        if not call_row.empty:
            atm_call_iv = float(call_row["impliedVolatility"].iloc[0])
        if not put_row.empty:
            atm_put_iv = float(put_row["impliedVolatility"].iloc[0])

    atm_iv_values = [v for v in (atm_call_iv, atm_put_iv) if v is not None]
    atm_iv_avg = round(sum(atm_iv_values) / len(atm_iv_values), 4) if atm_iv_values else None

    call_volume = calls["volume"].fillna(0).sum()
    put_volume = puts["volume"].fillna(0).sum()
    call_oi = calls["openInterest"].fillna(0).sum()
    put_oi = puts["openInterest"].fillna(0).sum()

    return {
        "ticker": ticker.upper(),
        "expiration_used": expiry,
        "atm_strike": atm_strike,
        "atm_implied_volatility": {
            "call": round(atm_call_iv, 4) if atm_call_iv is not None else None,
            "put": round(atm_put_iv, 4) if atm_put_iv is not None else None,
            "average": atm_iv_avg,
        },
        "put_call_ratio": {
            "by_volume": compute_put_call_ratio(put_volume, call_volume),
            "by_open_interest": compute_put_call_ratio(put_oi, call_oi),
        },
        "note": "Implied volatility and put/call ratios reflect current options-market "
        "positioning, not a prediction — they can shift day to day and are read here from "
        "a single expiration near 30 days out.",
    }
