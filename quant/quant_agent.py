"""Agent 1: System Quant. No LLM calls in this module — only API data pulls
and deterministic math, so downstream agents can't hallucinate the numbers."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from quant import dcf, market_data, relative_valuation, residual_income, sec_data

DATA_DIR = Path(__file__).parent.parent / "data"


def run_quant_agent(ticker: str) -> dict:
    ticker = ticker.upper()

    fcf_series = sec_data.get_10yr_fcf_series(ticker)
    if not fcf_series:
        raise RuntimeError(
            f"No SEC EDGAR FCF data found for {ticker} — check the ticker is a "
            "US filer and try again (SEC rate limits can also cause gaps)."
        )
    fcf_cagr = sec_data.compute_cagr(fcf_series)
    latest_year = max(fcf_series)
    latest_fcf = fcf_series[latest_year]

    risk_free_rate = market_data.get_risk_free_rate()
    capital = market_data.get_capital_structure(ticker)

    wacc = dcf.calculate_wacc(
        market_cap=capital["market_cap"],
        total_debt=capital["total_debt"],
        beta=capital["beta"],
        risk_free_rate=risk_free_rate,
        effective_tax_rate=capital["effective_tax_rate"],
    )
    cost_of_equity = dcf.compute_cost_of_equity(risk_free_rate, capital["beta"])

    # Reverse DCF: computed independently of whether the forward DCF below
    # succeeds — a large valuation_gap_pct (or even an insufficient_data
    # DCF, as can happen with a temporarily depressed base-year FCF) is
    # easier to reason about as "what growth rate would this price imply?"
    implied_growth = dcf.calculate_implied_growth_rate(
        current_price=capital["current_price"],
        latest_fcf=latest_fcf,
        wacc=wacc,
        total_debt=capital["total_debt"],
        shares_outstanding=capital["shares_outstanding"],
    )

    dcf_insufficient_data_reason = None
    try:
        valuation = dcf.calculate_fair_value(
            latest_fcf=latest_fcf,
            fcf_cagr=fcf_cagr,
            wacc=wacc,
            total_debt=capital["total_debt"],
            shares_outstanding=capital["shares_outstanding"],
        )
        gap = dcf.valuation_gap(capital["current_price"], valuation["fair_value_per_share"])
    except ValueError as e:
        # A single anomalous base-year FCF (e.g. a temporary capex supercycle)
        # can push equity value negative — that's a real model limitation, not
        # a reason to fabricate a number, so we degrade to insufficient_data
        # instead of crashing the whole pipeline (relative valuation below is
        # still computed independently of the DCF base year).
        dcf_insufficient_data_reason = str(e)
        valuation = {
            "growth_rate_used": None,
            "projected_fcfs": None,
            "enterprise_value": None,
            "equity_value": None,
            "fair_value_per_share": None,
        }
        gap = None

    relative = relative_valuation.get_relative_valuation_metrics(
        ticker,
        latest_fcf=latest_fcf,
        fcf_cagr=fcf_cagr,
        shares_outstanding=capital["shares_outstanding"],
        effective_tax_rate=capital["effective_tax_rate"],
    )

    residual_income_result = residual_income.get_residual_income_valuation(
        book_value_per_share=relative.get("book_value_per_share"),
        roe=relative.get("profitability", {}).get("return_on_equity"),
        cost_of_equity=cost_of_equity,
        current_price=capital["current_price"],
    )

    result = {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": {
            "fcf_history": "SEC EDGAR XBRL (10-K, OperatingCashFlow - CapEx)",
            "market_data": "yfinance",
            "risk_free_rate": "^TNX (10yr UST yield)",
        },
        "10yr_metrics": {
            "fcf_by_fiscal_year": fcf_series,
            "fcf_cagr": round(fcf_cagr, 5) if fcf_cagr is not None else None,
            "latest_fcf": latest_fcf,
        },
        "macro_inputs": {
            "risk_free_rate": risk_free_rate,
        },
        "capital_structure": capital,
        "dcf_model_output": {
            "dynamic_wacc": wacc,
            "cost_of_equity_capm": round(cost_of_equity, 5),
            **valuation,
            "current_price": capital["current_price"],
            "valuation_gap_pct": gap,
            "insufficient_data_reason": dcf_insufficient_data_reason,
            "implied_growth_rate_analysis": {
                **implied_growth,
                "note": (
                    "implied_growth_rate는 현재가가 이 DCF 모델에서 정확히 적정가가 되도록 "
                    "역산한 5년 성장률(소수, 예: 0.24=24%). historical_10yr_fcf_cagr, "
                    "analyst_forward_growth_rate_pct와 비교해 시장이 가정하는 성장률이 "
                    "과거 실적·애널리스트 컨센서스 대비 합리적인 수준인지 판단하는 데 씁니다."
                ),
                "historical_10yr_fcf_cagr": round(fcf_cagr, 5) if fcf_cagr is not None else None,
                "analyst_forward_growth_rate_pct": relative.get("peg_ratio", {}).get(
                    "growth_rate_pct_used"
                ),
                "analyst_forward_growth_rate_source": relative.get("peg_ratio", {}).get(
                    "growth_rate_source"
                ),
            },
        },
        "residual_income_model_output": residual_income_result,
        "relative_valuation": relative,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{ticker}_quant.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m quant.quant_agent TICKER [TICKER ...]")
        sys.exit(1)

    for t in sys.argv[1:]:
        print(f"Running quant agent for {t}...")
        data = run_quant_agent(t)
        print(json.dumps(data["dcf_model_output"], indent=2))
