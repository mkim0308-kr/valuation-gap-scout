"""Dividend + buyback agent: total shareholder yield and dividend growth.
Deterministic, no LLM.
"""
from __future__ import annotations

import yfinance as yf

from quant.capital_allocation import BUYBACK_TAGS
from quant.sec_data import compute_cagr, get_annual_xbrl_series


def compute_buyback_yield(buyback_spend: float | None, market_cap: float | None) -> float | None:
    if buyback_spend is None or not market_cap:
        return None
    return round(buyback_spend / market_cap, 5)


def compute_total_shareholder_yield(
    dividend_yield: float | None, buyback_yield: float | None
) -> float | None:
    """Dividend yield + buyback yield. None if both legs are unknown; treats
    a missing single leg as 0 (e.g. a company that buys back stock but
    doesn't pay a dividend still has a real total yield)."""
    if dividend_yield is None and buyback_yield is None:
        return None
    return round((dividend_yield or 0) + (buyback_yield or 0), 5)


def _annualize_dividends(dividends_series) -> dict[int, float]:
    """Collapses a yfinance per-payment dividend Series (DatetimeIndex) into
    {calendar_year: total dividends paid that year}."""
    annual: dict[int, float] = {}
    for date, amount in dividends_series.items():
        year = date.year
        annual[year] = annual.get(year, 0) + float(amount)
    return annual


def get_shareholder_yield_metrics(ticker: str) -> dict:
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.get_info()

    dividend_yield = info.get("dividendYield")
    market_cap = info.get("marketCap")

    buyback_series = get_annual_xbrl_series(ticker, BUYBACK_TAGS)
    latest_buyback_year = max(buyback_series) if buyback_series else None
    latest_buyback_spend = buyback_series.get(latest_buyback_year) if latest_buyback_year else None
    buyback_yield_pct = compute_buyback_yield(latest_buyback_spend, market_cap)
    buyback_yield_pct = round(buyback_yield_pct * 100, 3) if buyback_yield_pct is not None else None

    dividend_yield_frac = dividend_yield / 100 if dividend_yield else None
    total_yield_pct = compute_total_shareholder_yield(
        dividend_yield_frac, buyback_yield_pct / 100 if buyback_yield_pct is not None else None
    )
    total_yield_pct = round(total_yield_pct * 100, 3) if total_yield_pct is not None else None

    dividends_raw = t.dividends
    dividend_cagr = None
    if dividends_raw is not None and not dividends_raw.empty:
        annual_dividends = _annualize_dividends(dividends_raw)
        # Drop the first/last partial calendar years to avoid understating growth
        years = sorted(annual_dividends.keys())
        if len(years) > 2:
            trimmed = {y: annual_dividends[y] for y in years[1:-1]}
            dividend_cagr = compute_cagr(trimmed)

    return {
        "ticker": ticker,
        "dividend_yield_pct": dividend_yield,
        "buyback_yield_pct": buyback_yield_pct,
        "total_shareholder_yield_pct": total_yield_pct,
        "latest_buyback_year": latest_buyback_year,
        "latest_buyback_spend": latest_buyback_spend,
        "dividend_cagr": round(dividend_cagr, 5) if dividend_cagr is not None else None,
        "note": "Buyback yield uses the most recent full fiscal year's SEC-reported buyback "
        "spend over current market cap — a backward-looking rate, not a forward commitment. "
        "Dividend CAGR excludes the first/last calendar year of the dividend history since "
        "those are typically partial years.",
    }
