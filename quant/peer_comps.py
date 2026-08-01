"""Peer/relative-comps agent: compares a ticker's multiples against a peer
group. Deterministic, no LLM — peer selection is either supplied explicitly
or looked up from a small curated big-tech/semiconductor map; there is no
guessing of "who the real competitors are" beyond that.
"""
from __future__ import annotations

import statistics

import yfinance as yf

# Curated defaults for this project's focus (big tech / semis) — not
# exhaustive. Pass explicit peers for any ticker not covered here.
DEFAULT_PEER_MAP: dict[str, list[str]] = {
    "AAPL": ["MSFT", "GOOGL", "AMZN"],
    "MSFT": ["AAPL", "GOOGL", "AMZN"],
    "GOOGL": ["MSFT", "META", "AMZN"],
    "AMZN": ["MSFT", "GOOGL", "WMT"],
    "META": ["GOOGL", "SNAP", "MSFT"],
    "NVDA": ["AMD", "AVGO", "QCOM"],
    "AMD": ["NVDA", "INTC", "QCOM"],
    "INTC": ["AMD", "TXN", "QCOM"],
    "TSM": ["INTC", "AVGO", "ASML"],
    "QCOM": ["AVGO", "TXN", "NVDA"],
    "AVGO": ["QCOM", "TXN", "NVDA"],
    "TXN": ["QCOM", "AVGO", "ASML"],
    "ASML": ["TSM", "AVGO", "TXN"],
    "MU": ["INTC", "TXN", "AVGO"],
}

COMPARED_FIELDS = {
    "trailing_pe": "trailingPE",
    "forward_pe": "forwardPE",
    "ev_to_ebitda": "enterpriseToEbitda",
    "price_to_book": "priceToBook",
    "price_to_sales": "priceToSalesTrailing12Months",
    "return_on_equity": "returnOnEquity",
}


def compute_peer_relative_position(target_value: float | None, peer_values: list[float]) -> dict:
    """Where the target sits relative to its peer group for one metric.
    `percentile` is the fraction of peers the target is >= to (0-100);
    `delta_vs_median_pct` is how far the target is from the peer median."""
    peer_values = [v for v in peer_values if v is not None]
    if target_value is None or not peer_values:
        return {"peer_median": None, "delta_vs_median_pct": None, "percentile_vs_peers": None}

    peer_median = statistics.median(peer_values)
    delta_pct = round((target_value - peer_median) / peer_median * 100, 2) if peer_median else None
    percentile = round(
        100 * sum(1 for v in peer_values if target_value >= v) / len(peer_values), 1
    )
    return {
        "peer_median": round(peer_median, 4),
        "delta_vs_median_pct": delta_pct,
        "percentile_vs_peers": percentile,
    }


def get_peer_comps(ticker: str, peer_tickers: list[str] | None = None) -> dict:
    ticker = ticker.upper()
    peers = [p.upper() for p in peer_tickers] if peer_tickers else DEFAULT_PEER_MAP.get(ticker, [])

    if not peers:
        return {
            "ticker": ticker,
            "peers_used": [],
            "comparison": {},
            "note": "insufficient_data — no default peer group is defined for this ticker; "
            "pass explicit peer tickers to compare.",
        }

    target_info = yf.Ticker(ticker).get_info()
    peer_infos = {p: yf.Ticker(p).get_info() for p in peers}

    comparison = {}
    for label, yf_field in COMPARED_FIELDS.items():
        target_value = target_info.get(yf_field)
        peer_values = [info.get(yf_field) for info in peer_infos.values()]
        comparison[label] = {
            "target_value": target_value,
            "peer_values": {p: peer_infos[p].get(yf_field) for p in peers},
            **compute_peer_relative_position(target_value, peer_values),
        }

    return {
        "ticker": ticker,
        "peers_used": peers,
        "comparison": comparison,
    }
