"""Agent 1: System Quant. No LLM calls in this module — only API data pulls
and deterministic math, so downstream agents can't hallucinate the numbers."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from quant import dcf, market_data, quarterly_metrics, relative_valuation, residual_income, sec_data

DATA_DIR = Path(__file__).parent.parent / "data"


def run_quant_agent(ticker: str) -> dict:
    ticker = ticker.upper()

    fcf_quarters = sec_data.get_5yr_quarterly_fcf_series(ticker)
    if not fcf_quarters:
        raise RuntimeError(
            f"No SEC EDGAR FCF data found for {ticker} — check the ticker is a "
            "US filer and try again (SEC rate limits can also cause gaps)."
        )
    ttm_fcf_series = sec_data.compute_ttm_series(fcf_quarters)
    if not ttm_fcf_series:
        raise RuntimeError(
            f"{ticker}: found quarterly SEC filings but no 4 consecutive quarters "
            "to build a trailing-twelve-month FCF figure from."
        )
    # Primary growth-rate figure: log-linear regression across the whole TTM
    # series, less skewed by one outlier quarter than a 2-point comparison.
    # The simple endpoint CAGR is also kept, for transparency/comparison.
    fcf_cagr = sec_data.compute_ttm_trend_growth_rate(ttm_fcf_series)
    simple_endpoint_cagr = sec_data.compute_quarterly_cagr(ttm_fcf_series)
    latest_ttm_quarter = max(ttm_fcf_series, key=lambda label: (label.split("-")[0], label.split("-")[1]))
    latest_fcf = ttm_fcf_series[latest_ttm_quarter]

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

    # Computed before the DCF call below since the multi-stage DCF's
    # near-term growth rate prefers the analyst forward estimate PEG already
    # resolved (falling back to fcf_cagr itself when no estimate exists).
    relative = relative_valuation.get_relative_valuation_metrics(
        ticker,
        latest_fcf=latest_fcf,
        fcf_cagr=fcf_cagr,
        shares_outstanding=capital["shares_outstanding"],
        effective_tax_rate=capital["effective_tax_rate"],
    )
    near_term_growth_rate_pct = relative.get("peg_ratio", {}).get("growth_rate_pct_used")
    near_term_growth_rate = (
        near_term_growth_rate_pct / 100 if near_term_growth_rate_pct is not None else None
    )

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
        valuation = dcf.calculate_fair_value_multistage(
            latest_fcf=latest_fcf,
            near_term_growth_rate=near_term_growth_rate,
            wacc=wacc,
            total_debt=capital["total_debt"],
            shares_outstanding=capital["shares_outstanding"],
        )
        gap = dcf.valuation_gap(capital["current_price"], valuation["fair_value_per_share"])
    except ValueError as e:
        # A single anomalous base-year FCF (e.g. a temporary capex supercycle)
        # can push equity value negative — that's a real model limitation, not
        # a reason to fabricate a number, so we degrade to insufficient_data
        # instead of crashing the whole pipeline (relative valuation above is
        # computed independently of the DCF base year).
        dcf_insufficient_data_reason = str(e)
        valuation = {
            "near_term_growth_rate_used": None,
            "growth_rate_schedule": None,
            "projected_fcfs": None,
            "enterprise_value": None,
            "equity_value": None,
            "fair_value_per_share": None,
        }
        gap = None

    residual_income_result = residual_income.get_residual_income_valuation(
        book_value_per_share=relative.get("book_value_per_share"),
        roe=relative.get("profitability", {}).get("return_on_equity"),
        cost_of_equity=cost_of_equity,
        current_price=capital["current_price"],
    )

    # For the summary dashboard's interactive charts: ROE/P-E quarterly
    # series (built the same way as FCF above), unioned with TTM FCF into
    # one {quarter: {metric: value}} structure so the chart can plot any
    # metric on either axis without the caller needing to know which
    # module originally computed which figure.
    roe_pe_series = quarterly_metrics.get_quarterly_roe_and_pe(
        ticker, capital.get("shares_outstanding")
    )
    quarterly_timeseries: dict[str, dict[str, float]] = {}
    for quarter, value in ttm_fcf_series.items():
        quarterly_timeseries.setdefault(quarter, {})["fcf_ttm"] = value
    for quarter, value in roe_pe_series["roe_by_quarter"].items():
        quarterly_timeseries.setdefault(quarter, {})["roe_ttm"] = value
    for quarter, value in roe_pe_series["pe_by_quarter"].items():
        quarterly_timeseries.setdefault(quarter, {})["pe_ttm"] = value

    # Each quarter's real calendar end date, for charts that need to
    # position/label by actual time instead of the raw fiscal-year label
    # (e.g. NVIDIA's fiscal year runs ~10 months ahead of a December-FYE
    # company's, so "2026-Q2" alone is not a safe cross-ticker time axis).
    # Merged from whichever tag family has it — equity and OCF cover the
    # same fiscal periods FCF/ROE/PE are built from.
    quarter_end_dates: dict[str, str] = {}
    for source_dates in (
        sec_data.get_5yr_quarterly_snapshot_dates(ticker, quarterly_metrics.STOCKHOLDERS_EQUITY_TAGS),
        sec_data.get_5yr_quarterly_snapshot_dates(ticker, sec_data.OPERATING_CASHFLOW_TAGS),
    ):
        for quarter, end_date in source_dates.items():
            quarter_end_dates.setdefault(quarter, end_date)
    for quarter, metrics in quarterly_timeseries.items():
        end_date = quarter_end_dates.get(quarter)
        if end_date:
            metrics["end_date"] = end_date

    result = {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": {
            "fcf_history": (
                "SEC EDGAR XBRL (10-Q/10-K, trailing 5yr, quarterly OperatingCashFlow - CapEx "
                "reconstructed from as-filed YTD figures, rolled into trailing-twelve-month FCF)"
            ),
            "market_data": "yfinance",
            "risk_free_rate": "^TNX (10yr UST yield)",
        },
        "5yr_quarterly_metrics": {
            "fcf_by_quarter": fcf_quarters,
            "ttm_fcf_by_quarter": ttm_fcf_series,
            "fcf_cagr": round(fcf_cagr, 5) if fcf_cagr is not None else None,
            "fcf_cagr_method": (
                "log-linear regression across the full TTM series "
                "(compute_ttm_trend_growth_rate) — the primary growth-rate figure"
            ),
            "simple_endpoint_cagr": (
                round(simple_endpoint_cagr, 5) if simple_endpoint_cagr is not None else None
            ),
            "simple_endpoint_cagr_method": (
                "2-point CAGR between the oldest and newest TTM value only — kept "
                "for comparison; more sensitive to a single outlier quarter at "
                "either end than fcf_cagr"
            ),
            "latest_ttm_fcf": latest_fcf,
            "latest_ttm_quarter": latest_ttm_quarter,
        },
        "macro_inputs": {
            "risk_free_rate": risk_free_rate,
        },
        "capital_structure": capital,
        "dcf_model_output": {
            "dynamic_wacc": wacc,
            "cost_of_equity_capm": round(cost_of_equity, 5),
            "growth_methodology": (
                "2-stage: years 1-2 hold near_term_growth_rate_used (analyst forward "
                "estimate if available, else the 5yr quarterly trend CAGR), then "
                "growth fades linearly to terminal_growth_rate by year 5 — see "
                "growth_rate_schedule for the actual per-year rate used"
            ),
            **valuation,
            "current_price": capital["current_price"],
            "valuation_gap_pct": gap,
            "insufficient_data_reason": dcf_insufficient_data_reason,
            "implied_growth_rate_analysis": {
                **implied_growth,
                "note": (
                    "implied_growth_rate는 현재가가 이 DCF 모델에서 정확히 적정가가 되도록 "
                    "역산한 5년 성장률(소수, 예: 0.24=24%). historical_5yr_quarterly_fcf_cagr, "
                    "analyst_forward_growth_rate_pct와 비교해 시장이 가정하는 성장률이 "
                    "과거 실적·애널리스트 컨센서스 대비 합리적인 수준인지 판단하는 데 씁니다."
                ),
                "historical_5yr_quarterly_fcf_cagr": round(fcf_cagr, 5) if fcf_cagr is not None else None,
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
        "quarterly_timeseries": {
            "metrics": quarterly_timeseries,
            "metric_labels": {
                "fcf_ttm": "FCF (TTM)",
                "roe_ttm": "ROE (TTM)",
                "pe_ttm": "P/E (TTM)",
            },
            "note": (
                "Each quarter's value is trailing-twelve-month (TTM) as of that quarter's "
                "end, not a single-quarter figure — smooths seasonality the same way the "
                "primary FCF series does. pe_ttm approximates market cap using *today's* "
                "share count for every historical quarter (SEC doesn't cleanly expose a "
                "point-in-time historical diluted share count), least accurate for names "
                "with heavy buyback/issuance activity. A quarter only appears for a given "
                "metric if SEC/price data was actually available for it — never guessed. "
                "The quarter key (e.g. '2027-Q1') is the company's own SEC fiscal-year "
                "label, not a calendar quarter — fiscal year ends vary by company (e.g. "
                "NVIDIA's fiscal year starts ~10 months ahead of a December-FYE company's), "
                "so two tickers' same-numbered quarter can be many months apart in real "
                "time. end_date is each quarter's actual calendar end date, included "
                "specifically so charts can position/label by real time instead."
            ),
        },
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
