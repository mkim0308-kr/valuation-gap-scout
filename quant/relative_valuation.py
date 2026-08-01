"""Agent 1b: relative-valuation and classic value-investing metrics.

Deterministic, no LLM — same philosophy as dcf.py. DCF is one lens on "fair
value"; these are others (comps multiples, Graham's formula, Lynch's PEG,
Buffett's owner earnings) so the CFO report can show where they agree or
disagree instead of leaning on a single model.
"""
from __future__ import annotations

import yfinance as yf

from quant.statement_utils import first_value


def compute_graham_number(eps: float | None, book_value_per_share: float | None) -> float | None:
    """Benjamin Graham's conservative intrinsic-value formula:
    sqrt(22.5 * EPS * Book Value Per Share). Undefined (returns None) unless
    both inputs are positive — the formula assumes a profitable, solvent
    company and produces nonsense otherwise."""
    if not eps or not book_value_per_share or eps <= 0 or book_value_per_share <= 0:
        return None
    return round((22.5 * eps * book_value_per_share) ** 0.5, 2)


def compute_peg_ratio(pe_ratio: float | None, growth_rate_pct: float | None) -> float | None:
    """Peter Lynch's PEG ratio: P/E divided by the expected earnings growth
    rate (as a plain number, e.g. 15 for 15%). Undefined for a non-positive
    P/E or non-positive growth — PEG only means something for a profitable,
    growing company."""
    if not pe_ratio or not growth_rate_pct or pe_ratio <= 0 or growth_rate_pct <= 0:
        return None
    return round(pe_ratio / growth_rate_pct, 2)


def compute_roic(
    ebit: float | None,
    total_debt: float | None,
    total_equity: float | None,
    cash: float | None,
    effective_tax_rate: float | None,
) -> float | None:
    """Return on Invested Capital = NOPAT / Invested Capital, where
    NOPAT = EBIT * (1 - tax rate) and Invested Capital = Total Debt +
    Total Equity - Cash. None if any input is missing or invested capital
    isn't positive (the ratio is meaningless for a net-cash-negative capital
    base)."""
    if None in (ebit, total_debt, total_equity, cash, effective_tax_rate):
        return None
    invested_capital = total_debt + total_equity - cash
    if invested_capital <= 0:
        return None
    nopat = ebit * (1 - effective_tax_rate)
    return round(nopat / invested_capital, 5)


def get_relative_valuation_metrics(
    ticker: str,
    latest_fcf: float,
    fcf_cagr: float | None,
    shares_outstanding: float,
    effective_tax_rate: float | None = None,
) -> dict:
    """Pulls comps multiples and classic value metrics from yfinance, and
    derives Graham Number / PEG / owner earnings / ROIC on top. Any field
    yfinance doesn't report comes back as None rather than a guessed value."""
    ticker_obj = yf.Ticker(ticker)
    info = ticker_obj.get_info()

    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    ev_to_ebitda = info.get("enterpriseToEbitda")
    price_to_book = info.get("priceToBook")
    trailing_eps = info.get("trailingEps")
    book_value_per_share = info.get("bookValue")
    dividend_yield = info.get("dividendYield")

    # Prefer yfinance's own forward earnings-growth estimate for PEG; fall
    # back to the 10yr FCF CAGR we already computed if it's unavailable.
    earnings_growth = info.get("earningsGrowth")
    if earnings_growth is not None:
        growth_rate_pct = round(earnings_growth * 100, 2)
        growth_rate_source = "yfinance earningsGrowth (forward estimate)"
    elif fcf_cagr is not None:
        growth_rate_pct = round(fcf_cagr * 100, 2)
        growth_rate_source = "10yr FCF CAGR (proxy — no forward earnings estimate available)"
    else:
        growth_rate_pct = None
        growth_rate_source = None

    owner_earnings_per_share = (
        round(latest_fcf / shares_outstanding, 2) if shares_outstanding else None
    )

    return_on_equity = info.get("returnOnEquity")

    financials = ticker_obj.financials
    balance_sheet = ticker_obj.balance_sheet
    ebit = first_value(financials, ["EBIT", "Operating Income"])
    total_debt_bs = first_value(balance_sheet, ["Total Debt"])
    total_equity = first_value(
        balance_sheet, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"]
    )
    cash = first_value(
        balance_sheet,
        ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"],
    )
    return_on_invested_capital = compute_roic(
        ebit, total_debt_bs, total_equity, cash, effective_tax_rate
    )

    return {
        "comps_multiples": {
            "trailing_pe": trailing_pe,
            "forward_pe": forward_pe,
            "ev_to_ebitda": ev_to_ebitda,
            "price_to_book": price_to_book,
            "dividend_yield": dividend_yield,
        },
        "graham_number": {
            "value": compute_graham_number(trailing_eps, book_value_per_share),
            "inputs": {"trailing_eps": trailing_eps, "book_value_per_share": book_value_per_share},
            "method": "Benjamin Graham: sqrt(22.5 * EPS * Book Value Per Share)",
        },
        "peg_ratio": {
            "value": compute_peg_ratio(trailing_pe, growth_rate_pct),
            "growth_rate_pct_used": growth_rate_pct,
            "growth_rate_source": growth_rate_source,
            "method": "Peter Lynch: P/E divided by expected earnings growth rate",
        },
        "owner_earnings": {
            "per_share": owner_earnings_per_share,
            "method": "Warren Buffett proxy: latest 10-K-derived FCF / shares outstanding",
        },
        "profitability": {
            "return_on_equity": return_on_equity,
            "return_on_invested_capital": return_on_invested_capital,
            "roic_inputs": {
                "ebit": ebit,
                "total_debt": total_debt_bs,
                "total_equity": total_equity,
                "cash": cash,
                "effective_tax_rate": effective_tax_rate,
            },
        },
    }
