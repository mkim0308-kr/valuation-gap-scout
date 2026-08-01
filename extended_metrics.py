"""Runs the five extended-metrics agents (peer comps, earnings quality,
insider/institutional activity, historical price positioning, options
market signal) and writes data/{TICKER}_extended_metrics.json.

All deterministic — no LLM, no API key needed, same as main.py.

    python extended_metrics.py AAPL
    python extended_metrics.py AAPL --peers MSFT GOOGL AMZN
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quant import (
    earnings_quality,
    historical_valuation,
    insider_institutional,
    options_market_signal,
    peer_comps,
)

DATA_DIR = Path(__file__).parent / "data"


def run_extended_metrics(ticker: str, peer_tickers: list[str] | None = None) -> dict:
    ticker = ticker.upper()

    result = {
        "ticker": ticker,
        "peer_comps": peer_comps.get_peer_comps(ticker, peer_tickers),
        "earnings_quality": earnings_quality.get_earnings_quality_metrics(ticker),
        "insider_institutional": insider_institutional.get_insider_institutional_metrics(ticker),
        "historical_valuation": historical_valuation.get_historical_valuation_context(ticker),
        "options_market_signal": options_market_signal.get_options_market_signal(ticker),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{ticker}_extended_metrics.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="확장 지표 5종 (peer, 이익품질, 내부자/기관, 과거밴드, 옵션)")
    parser.add_argument("ticker", help="예: AAPL")
    parser.add_argument("--peers", nargs="*", default=None, help="비교할 피어 티커 (예: MSFT GOOGL AMZN)")
    args = parser.parse_args()

    print(f"=== {args.ticker.upper()} 확장 지표 수집 중 ===")
    try:
        result = run_extended_metrics(args.ticker, args.peers)
    except Exception as exc:  # noqa: BLE001
        print(f"[오류] {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  -> data/{args.ticker.upper()}_extended_metrics.json 저장 완료")
    print(f"  -> peer 비교: {result['peer_comps'].get('peers_used') or '(기본 피어 없음 — --peers로 지정)'}")
    print(f"  -> Beneish M-Score: {result['earnings_quality']['beneish_m_score']['value']}")
    print(f"  -> 내부자 매매(최근): buy={result['insider_institutional']['insider_transactions_recent']['transaction_counts'].get('buy')}, "
          f"sell={result['insider_institutional']['insider_transactions_recent']['transaction_counts'].get('sell')}")


if __name__ == "__main__":
    main()
