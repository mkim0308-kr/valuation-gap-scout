"""Agent 1c: time-series trend. Compares the current quant run to a
reference snapshot from 1-6 months ago (archive.load_reference_snapshot) so
the report can note what's changed since last time. Deterministic, no LLM —
purely numeric diffing, never an interpretation of *why* something changed
(that's debate-synthesis-agent's job, reading this file's output)."""
from __future__ import annotations

import json
from pathlib import Path

from quant import archive

DATA_DIR = Path(__file__).parent.parent / "data"


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 4)


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def _field(current_val, previous_val) -> dict:
    return {
        "previous": previous_val,
        "current": current_val,
        "change": _delta(current_val, previous_val),
        "change_pct": _pct_change(current_val, previous_val),
    }


def compute_trend(ticker: str) -> dict:
    ticker = ticker.upper()
    current_path = DATA_DIR / f"{ticker}_quant.json"
    if not current_path.exists():
        return {
            "ticker": ticker,
            "insufficient_data": True,
            "reason": f"data/{ticker}_quant.json not found — run the quant pipeline first",
        }

    reference = archive.load_reference_snapshot(ticker)
    if reference is None:
        return {
            "ticker": ticker,
            "insufficient_data": True,
            "reason": (
                "1~6개월 전 참조 스냅샷이 없습니다 (해당 기간 내 실행 이력이 없음 — "
                "이 툴을 쓴 지 1개월이 안 됐거나, 6개월 넘게 실행 공백이 있었을 수 있음)"
            ),
        }

    current = json.loads(current_path.read_text())
    prev = reference["quant"]
    cur_dcf = current.get("dcf_model_output", {})
    prev_dcf = prev.get("dcf_model_output", {})
    cur_rel = current.get("relative_valuation", {})
    prev_rel = prev.get("relative_valuation", {})

    return {
        "ticker": ticker,
        "insufficient_data": False,
        "reference_snapshot_date": reference["snapshot_date"],
        "current_as_of": current.get("as_of"),
        "current_price": _field(cur_dcf.get("current_price"), prev_dcf.get("current_price")),
        "fair_value_per_share": _field(
            cur_dcf.get("fair_value_per_share"), prev_dcf.get("fair_value_per_share")
        ),
        "valuation_gap_pct": _field(
            cur_dcf.get("valuation_gap_pct"), prev_dcf.get("valuation_gap_pct")
        ),
        "trailing_pe": _field(
            cur_rel.get("comps_multiples", {}).get("trailing_pe"),
            prev_rel.get("comps_multiples", {}).get("trailing_pe"),
        ),
        "return_on_equity": _field(
            cur_rel.get("profitability", {}).get("return_on_equity"),
            prev_rel.get("profitability", {}).get("return_on_equity"),
        ),
    }


def save_trend(ticker: str) -> Path:
    ticker = ticker.upper()
    trend = compute_trend(ticker)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{ticker}_trend.json"
    out_path.write_text(json.dumps(trend, indent=2, default=str))
    return out_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m quant.trend TICKER [TICKER ...]")
        sys.exit(1)

    for t in sys.argv[1:]:
        path = save_trend(t)
        print(f"{t}: {path}")
