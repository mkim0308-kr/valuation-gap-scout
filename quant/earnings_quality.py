"""Earnings-quality agent: flags accounting red flags via the Sloan accruals
ratio and the Beneish M-Score. Deterministic, no LLM. Beneish needs 8 inputs
spanning two fiscal years — yfinance's statement coverage varies a lot by
ticker, so any missing component makes the final score None rather than a
partial (misleading) number.
"""
from __future__ import annotations

import yfinance as yf

from quant.statement_utils import first_value


def compute_accruals_ratio(
    net_income: float | None, operating_cash_flow: float | None, total_assets: float | None
) -> float | None:
    """Sloan accruals ratio = (Net Income - Operating Cash Flow) / Total
    Assets. A large positive value (earnings well above cash generated)
    is the classic low-earnings-quality red flag."""
    if None in (net_income, operating_cash_flow, total_assets) or total_assets <= 0:
        return None
    return round((net_income - operating_cash_flow) / total_assets, 5)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _safe_index(current: float | None, prior: float | None) -> float | None:
    """current / prior, guarding zero/None — the shape shared by every
    Beneish sub-index."""
    if current is None or not prior:
        return None
    return current / prior


def compute_beneish_m_score(
    dsri: float | None,
    gmi: float | None,
    aqi: float | None,
    sgi: float | None,
    depi: float | None,
    sgai: float | None,
    lvgi: float | None,
    tata: float | None,
) -> float | None:
    """Beneish M-Score. Requires all 8 components — a partial weighted sum
    would misstate the score, so this returns None unless every input is
    present. Above ~-1.78 is the traditional "more likely to be a
    manipulator" threshold from Beneish's original paper."""
    components = (dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata)
    if any(c is None for c in components):
        return None
    return round(
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi,
        4,
    )


def get_earnings_quality_metrics(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    financials = t.financials
    balance_sheet = t.balance_sheet
    cashflow = t.cashflow

    net_income_t = first_value(financials, ["Net Income"], 0)
    ocf_t = first_value(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"], 0)
    total_assets_t = first_value(balance_sheet, ["Total Assets"], 0)
    accruals_ratio = compute_accruals_ratio(net_income_t, ocf_t, total_assets_t)

    # Beneish M-Score inputs: period 0 = most recent fiscal year, 1 = prior.
    receivables_t = first_value(balance_sheet, ["Receivables", "Accounts Receivable"], 0)
    receivables_t1 = first_value(balance_sheet, ["Receivables", "Accounts Receivable"], 1)
    sales_t = first_value(financials, ["Total Revenue"], 0)
    sales_t1 = first_value(financials, ["Total Revenue"], 1)
    gross_profit_t = first_value(financials, ["Gross Profit"], 0)
    gross_profit_t1 = first_value(financials, ["Gross Profit"], 1)
    current_assets_t = first_value(balance_sheet, ["Current Assets"], 0)
    current_assets_t1 = first_value(balance_sheet, ["Current Assets"], 1)
    ppe_t = first_value(balance_sheet, ["Net PPE"], 0)
    ppe_t1 = first_value(balance_sheet, ["Net PPE"], 1)
    total_assets_t1 = first_value(balance_sheet, ["Total Assets"], 1)
    depreciation_t = first_value(cashflow, ["Depreciation And Amortization", "Depreciation"], 0)
    depreciation_t1 = first_value(cashflow, ["Depreciation And Amortization", "Depreciation"], 1)
    sga_t = first_value(financials, ["Selling General And Administration"], 0)
    sga_t1 = first_value(financials, ["Selling General And Administration"], 1)
    current_liab_t = first_value(balance_sheet, ["Current Liabilities"], 0)
    current_liab_t1 = first_value(balance_sheet, ["Current Liabilities"], 1)
    lt_debt_t = first_value(balance_sheet, ["Long Term Debt"], 0)
    lt_debt_t1 = first_value(balance_sheet, ["Long Term Debt"], 1)
    net_income_t1 = first_value(financials, ["Net Income"], 1)
    ocf_t1 = first_value(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"], 1)

    dsri = _safe_index(_safe_ratio(receivables_t, sales_t), _safe_ratio(receivables_t1, sales_t1))
    gmi = _safe_index(
        _safe_ratio(gross_profit_t1, sales_t1), _safe_ratio(gross_profit_t, sales_t)
    )
    aqi = _safe_index(
        _non_current_asset_share(total_assets_t, current_assets_t, ppe_t),
        _non_current_asset_share(total_assets_t1, current_assets_t1, ppe_t1),
    )
    sgi = _safe_index(sales_t, sales_t1)
    depi = _safe_index(
        _dep_rate(depreciation_t1, ppe_t1), _dep_rate(depreciation_t, ppe_t)
    )
    sgai = _safe_index(_safe_ratio(sga_t, sales_t), _safe_ratio(sga_t1, sales_t1))
    lvgi = _safe_index(
        _safe_ratio(_sum_or_none(current_liab_t, lt_debt_t), total_assets_t),
        _safe_ratio(_sum_or_none(current_liab_t1, lt_debt_t1), total_assets_t1),
    )
    tata = _safe_ratio(_diff_or_none(net_income_t, ocf_t), total_assets_t)

    m_score = compute_beneish_m_score(dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata)

    return {
        "ticker": ticker.upper(),
        "sloan_accruals_ratio": {
            "value": accruals_ratio,
            "method": "(Net Income - Operating Cash Flow) / Total Assets — "
            "large positive values are a classic low-earnings-quality flag",
        },
        "beneish_m_score": {
            "value": m_score,
            "components": {
                "dsri": dsri, "gmi": gmi, "aqi": aqi, "sgi": sgi,
                "depi": depi, "sgai": sgai, "lvgi": lvgi, "tata": tata,
            },
            "method": "Beneish (1999) 8-variable model; requires all 8 components "
            "— None if yfinance is missing any of the underlying statement rows",
            "reference_threshold": "Original paper: scores above ~-1.78 warrant scrutiny. "
            "This is a screening heuristic, not a diagnosis of manipulation — legitimate "
            "high-growth companies routinely score above this threshold because several "
            "components (SGI, AQI) rise mechanically with fast revenue/asset growth, so a "
            "flagged score should always be read alongside the company's actual growth "
            "profile before drawing any conclusion.",
        },
    }


def _non_current_asset_share(total_assets, current_assets, ppe):
    if None in (total_assets, current_assets, ppe) or not total_assets:
        return None
    return 1 - (current_assets + ppe) / total_assets


def _dep_rate(depreciation, ppe):
    if None in (depreciation, ppe) or (depreciation + ppe) == 0:
        return None
    return depreciation / (depreciation + ppe)


def _sum_or_none(a, b):
    return None if None in (a, b) else a + b


def _diff_or_none(a, b):
    return None if None in (a, b) else a - b
