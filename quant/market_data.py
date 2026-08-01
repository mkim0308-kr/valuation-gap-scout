"""Market/reference data via yfinance: risk-free rate, beta, capital structure."""
from __future__ import annotations

import yfinance as yf

DEFAULT_EQUITY_RISK_PREMIUM = 0.055  # long-run US equity risk premium assumption
DEFAULT_BETA = 1.0  # fallback if yfinance doesn't report one


def get_risk_free_rate() -> float:
    """10-year US Treasury yield (^TNX quotes in index points = yield * 10)."""
    tnx = yf.Ticker("^TNX").history(period="5d")
    if tnx.empty:
        raise RuntimeError("Could not fetch ^TNX treasury yield data")
    last_close = tnx["Close"].dropna().iloc[-1]
    return round(last_close / 100, 5)


def get_capital_structure(ticker: str) -> dict:
    info = yf.Ticker(ticker).get_info()

    market_cap = info.get("marketCap")
    total_debt = info.get("totalDebt", 0) or 0
    shares_outstanding = info.get("sharesOutstanding")
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    beta = info.get("beta") or DEFAULT_BETA
    effective_tax_rate = info.get("effectiveTaxRate")
    if not effective_tax_rate or effective_tax_rate <= 0:
        effective_tax_rate = 0.21  # US statutory corporate rate as a fallback

    if market_cap is None or shares_outstanding is None or current_price is None:
        raise RuntimeError(f"Incomplete market data from yfinance for {ticker}")

    return {
        "market_cap": market_cap,
        "total_debt": total_debt,
        "shares_outstanding": shares_outstanding,
        "current_price": current_price,
        "beta": beta,
        "effective_tax_rate": effective_tax_rate,
    }
