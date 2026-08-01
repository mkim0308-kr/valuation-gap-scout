"""Balance-sheet health agent: Altman Z-Score, interest coverage, current
ratio, Debt/EBITDA. Deterministic, no LLM.
"""
from __future__ import annotations

import yfinance as yf

from quant.statement_utils import first_value

# Original Altman (1968) thresholds — designed for public manufacturing
# companies. Asset-light services/tech firms routinely score outside this
# band without it implying distress; report the number, not a verdict.
Z_SCORE_SAFE_THRESHOLD = 2.99
Z_SCORE_DISTRESS_THRESHOLD = 1.81


def compute_altman_z_score(
    working_capital: float | None,
    retained_earnings: float | None,
    ebit: float | None,
    market_cap: float | None,
    total_liabilities: float | None,
    sales: float | None,
    total_assets: float | None,
) -> float | None:
    """Z = 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MVE/TL) + 1.0*(Sales/TA)."""
    inputs = (working_capital, retained_earnings, ebit, market_cap, total_liabilities, sales, total_assets)
    if any(v is None for v in inputs) or not total_assets or not total_liabilities:
        return None
    z = (
        1.2 * (working_capital / total_assets)
        + 1.4 * (retained_earnings / total_assets)
        + 3.3 * (ebit / total_assets)
        + 0.6 * (market_cap / total_liabilities)
        + 1.0 * (sales / total_assets)
    )
    return round(z, 4)


def compute_interest_coverage_ratio(ebit: float | None, interest_expense: float | None) -> float | None:
    """EBIT / |Interest Expense|. None if the company carries no interest
    expense to divide by (undefined, not "infinite coverage")."""
    if ebit is None or not interest_expense:
        return None
    return round(ebit / abs(interest_expense), 2)


def compute_current_ratio(current_assets: float | None, current_liabilities: float | None) -> float | None:
    if current_assets is None or not current_liabilities:
        return None
    return round(current_assets / current_liabilities, 2)


def compute_debt_to_ebitda(total_debt: float | None, ebitda: float | None) -> float | None:
    if total_debt is None or not ebitda or ebitda <= 0:
        return None
    return round(total_debt / ebitda, 2)


def get_balance_sheet_health(ticker: str) -> dict:
    t = yf.Ticker(ticker.upper())
    info = t.get_info()
    balance_sheet = t.balance_sheet
    financials = t.financials

    working_capital = first_value(balance_sheet, ["Working Capital"])
    retained_earnings = first_value(balance_sheet, ["Retained Earnings"])
    current_assets = first_value(balance_sheet, ["Current Assets"])
    current_liabilities = first_value(balance_sheet, ["Current Liabilities"])
    total_liabilities = first_value(
        balance_sheet, ["Total Liabilities Net Minority Interest", "Total Liab"]
    )
    total_assets = first_value(balance_sheet, ["Total Assets"])
    ebit = first_value(financials, ["EBIT", "Operating Income"])
    interest_expense = first_value(financials, ["Interest Expense"])
    sales = first_value(financials, ["Total Revenue"])

    market_cap = info.get("marketCap")
    total_debt = info.get("totalDebt")
    ebitda = info.get("ebitda")

    z_score = compute_altman_z_score(
        working_capital, retained_earnings, ebit, market_cap, total_liabilities, sales, total_assets
    )
    if z_score is None:
        z_zone = None
    elif z_score >= Z_SCORE_SAFE_THRESHOLD:
        z_zone = "safe"
    elif z_score >= Z_SCORE_DISTRESS_THRESHOLD:
        z_zone = "grey"
    else:
        z_zone = "distress"

    return {
        "ticker": ticker.upper(),
        "altman_z_score": {
            "value": z_score,
            "zone": z_zone,
            "method": "Original Altman (1968) 5-factor model — calibrated for public "
            "manufacturing companies. Asset-light services/tech firms often score outside "
            "the classic bands without that implying distress; read alongside the business "
            "model, not as a standalone verdict.",
            "thresholds": {"safe": f">= {Z_SCORE_SAFE_THRESHOLD}", "distress": f"< {Z_SCORE_DISTRESS_THRESHOLD}"},
        },
        "interest_coverage_ratio": compute_interest_coverage_ratio(ebit, interest_expense),
        "current_ratio": compute_current_ratio(current_assets, current_liabilities),
        "debt_to_ebitda": compute_debt_to_ebitda(total_debt, ebitda),
    }
