"""Entry point: runs the quant data pipeline for one or more tickers.

    python main.py AAPL NVDA

This only handles Agent 1 (quant) — SEC EDGAR + yfinance data collection and
the DCF/WACC calculation. No LLM calls, no API key needed. The interpretive
agents (tech/moat audit, macro/risk analysis, CFO report) run inside Claude
Code itself as subagents — see .claude/agents/ and README.md.
"""
from __future__ import annotations

import sys

from quant.quant_agent import run_quant_agent


def run_pipeline(ticker: str) -> None:
    print(f"\n=== {ticker} ===")
    print("[Agent 1] 퀀트: SEC EDGAR + yfinance에서 데이터 수집 및 DCF 계산 중...")
    quant_json = run_quant_agent(ticker)
    dcf_output = quant_json["dcf_model_output"]
    if dcf_output["valuation_gap_pct"] is None:
        print(f"  -> DCF 적정가 산출 불가 (insufficient_data: {dcf_output['insufficient_data_reason']}) "
              f"vs 현재가 ${dcf_output['current_price']}")
    else:
        gap_pct = dcf_output["valuation_gap_pct"] * 100
        print(f"  -> DCF 적정가 ${dcf_output['fair_value_per_share']} "
              f"vs 현재가 ${dcf_output['current_price']} "
              f"(괴리율 {gap_pct:+.1f}%)")
    print(f"  -> data/{ticker}_quant.json 저장 완료")
    print("  -> 다음 단계: Claude Code에서 \"AAPL 분석 리포트 만들어줘\"라고 요청하면 "
          "tech-moat-auditor / macro-risk-analyst / cfo-report-writer 서브에이전트가 이어서 진행합니다.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="빅테크/반도체 오토-리서치 퀀트 파이프라인")
    parser.add_argument("tickers", nargs="+", help="예: AAPL NVDA TSM")
    args = parser.parse_args()

    for ticker in args.tickers:
        try:
            run_pipeline(ticker.upper())
        except Exception as exc:  # noqa: BLE001 - surface and continue to next ticker
            print(f"  [오류] {ticker}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
