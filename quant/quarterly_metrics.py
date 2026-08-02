"""Agent 1e: quarterly time-series metrics (ROE, P/E) for the interactive
summary-dashboard charts. Built on the same SEC quarterly-reconstruction
machinery as FCF (see sec_data.py), plus historical stock prices for P/E.
Deterministic, no LLM.
"""
from __future__ import annotations

import yfinance as yf

from quant import sec_data

NET_INCOME_TAGS = ["NetIncomeLoss", "ProfitLoss"]
STOCKHOLDERS_EQUITY_TAGS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]


def compute_roe_series(
    ttm_net_income: dict[str, float], equity_series: dict[str, float]
) -> dict[str, float]:
    """ROE per quarter = TTM Net Income / quarter-end Stockholders Equity.
    Only quarters where both are available and equity is positive are
    included — never guessed (a negative or zero equity base makes ROE
    undefined, not just a big number)."""
    roe = {}
    for quarter, ttm_ni in ttm_net_income.items():
        equity = equity_series.get(quarter)
        if equity is not None and equity > 0:
            roe[quarter] = round(ttm_ni / equity, 5)
    return roe


def compute_pe_series(
    ttm_net_income: dict[str, float],
    price_by_quarter: dict[str, float],
    current_shares_outstanding: float | None,
) -> dict[str, float]:
    """Approximate TTM P/E per quarter: (quarter-end price * current shares
    outstanding) / TTM Net Income. Uses *today's* share count as a stand-in
    for each historical quarter's actual diluted count, since SEC doesn't
    cleanly expose a point-in-time historical share count — a known
    simplification, least accurate for names with heavy buyback/issuance
    activity (documented in README). Only positive-TTM-earnings quarters
    are included, since P/E on negative earnings isn't conventionally
    meaningful."""
    if not current_shares_outstanding:
        return {}
    pe = {}
    for quarter, ttm_ni in ttm_net_income.items():
        if ttm_ni <= 0:
            continue
        price = price_by_quarter.get(quarter)
        if price is None:
            continue
        market_cap = price * current_shares_outstanding
        pe[quarter] = round(market_cap / ttm_ni, 2)
    return pe


def _price_by_quarter(ticker: str, quarter_end_dates: dict[str, str]) -> dict[str, float]:
    """Looks up the closing price on (or nearest trading day before) each
    quarter's end date, via one bulk price-history download."""
    if not quarter_end_dates:
        return {}
    start = min(quarter_end_dates.values())
    history = yf.Ticker(ticker).history(start=start)
    if history.empty:
        return {}
    closes = history["Close"]
    closes.index = closes.index.tz_localize(None)

    prices = {}
    for quarter, end_date in quarter_end_dates.items():
        price = closes.asof(end_date)
        if price == price:  # excludes NaN (asof returns NaN if date precedes all data)
            prices[quarter] = float(price)
    return prices


def get_quarterly_roe_and_pe(ticker: str, current_shares_outstanding: float | None) -> dict:
    """Orchestrates the SEC + yfinance fetches and returns
    {"roe_by_quarter": {...}, "pe_by_quarter": {...}}, both keyed by the
    same "{fiscal_year}-Q{n}" quarter labels used elsewhere in the pipeline
    (data/{TICKER}_quant.json's 5yr_quarterly_metrics)."""
    ticker = ticker.upper()

    net_income_quarters = sec_data.get_5yr_quarterly_flow_series(ticker, NET_INCOME_TAGS)
    if not net_income_quarters:
        return {"roe_by_quarter": {}, "pe_by_quarter": {}}
    ttm_net_income = sec_data.compute_ttm_series(net_income_quarters)

    equity_series = sec_data.get_5yr_quarterly_snapshot_series(ticker, STOCKHOLDERS_EQUITY_TAGS)
    roe_by_quarter = compute_roe_series(ttm_net_income, equity_series)

    quarter_end_dates = sec_data.get_5yr_quarterly_snapshot_dates(ticker, STOCKHOLDERS_EQUITY_TAGS)
    relevant_dates = {q: quarter_end_dates[q] for q in ttm_net_income if q in quarter_end_dates}
    price_by_quarter = _price_by_quarter(ticker, relevant_dates)
    pe_by_quarter = compute_pe_series(ttm_net_income, price_by_quarter, current_shares_outstanding)

    return {"roe_by_quarter": roe_by_quarter, "pe_by_quarter": pe_by_quarter}
