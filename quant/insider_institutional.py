"""Insider/institutional-activity agent: summarizes recent insider buy/sell
activity and current institutional/insider ownership. Deterministic, no
LLM — this is a factual data pull and tally, not an interpretation.
"""
from __future__ import annotations

import yfinance as yf

BUY_KEYWORDS = ("purchase", "buy")
SELL_KEYWORDS = ("sale", "sell")
GIFT_KEYWORDS = ("gift",)


def classify_insider_transaction(text: str) -> str:
    """Classifies one insider-transaction description into buy / sell /
    gift / other, based on the free-text SEC Form 4 description yfinance
    surfaces (there's no clean transaction-code column to rely on)."""
    lowered = (text or "").lower()
    if any(k in lowered for k in GIFT_KEYWORDS):
        return "gift"
    if any(k in lowered for k in SELL_KEYWORDS):
        return "sell"
    if any(k in lowered for k in BUY_KEYWORDS):
        return "buy"
    return "other"


def summarize_insider_transactions(transactions: list[dict]) -> dict:
    """transactions: list of {"shares": float, "text": str}. Returns counts
    and net shares per category — no dollar-value netting, since not every
    row carries a reliable price."""
    counts = {"buy": 0, "sell": 0, "gift": 0, "other": 0}
    shares_by_category = {"buy": 0, "sell": 0, "gift": 0, "other": 0}

    for txn in transactions:
        category = classify_insider_transaction(txn.get("text", ""))
        counts[category] += 1
        shares_by_category[category] += txn.get("shares") or 0

    net_buy_sell_shares = shares_by_category["buy"] - shares_by_category["sell"]

    return {
        "transaction_counts": counts,
        "shares_by_category": shares_by_category,
        "net_buy_sell_shares": net_buy_sell_shares,
        "total_transactions_seen": len(transactions),
    }


def get_insider_institutional_metrics(ticker: str) -> dict:
    t = yf.Ticker(ticker.upper())

    insider_summary = {
        "transaction_counts": None,
        "shares_by_category": None,
        "net_buy_sell_shares": None,
        "total_transactions_seen": 0,
    }
    insider_df = t.insider_transactions
    if insider_df is not None and not insider_df.empty:
        transactions = [
            {"shares": row.get("Shares"), "text": row.get("Text", "")}
            for row in insider_df.to_dict(orient="records")
        ]
        insider_summary = summarize_insider_transactions(transactions)

    ownership = {"insiders_pct_held": None, "institutions_pct_held": None, "institutions_count": None}
    major_holders = t.major_holders
    if major_holders is not None and not major_holders.empty:
        value_col = "Value" if "Value" in major_holders.columns else major_holders.columns[0]
        values = major_holders[value_col]
        ownership["insiders_pct_held"] = values.get("insidersPercentHeld")
        ownership["institutions_pct_held"] = values.get("institutionsPercentHeld")
        ownership["institutions_count"] = values.get("institutionsCount")

    top_institutional_holders = []
    inst_df = t.institutional_holders
    if inst_df is not None and not inst_df.empty:
        top_institutional_holders = [
            {
                "holder": row.get("Holder"),
                "pct_held": row.get("pctHeld"),
                "shares": row.get("Shares"),
                "pct_change": row.get("pctChange"),
            }
            for row in inst_df.head(5).to_dict(orient="records")
        ]

    return {
        "ticker": ticker.upper(),
        "insider_transactions_recent": insider_summary,
        "ownership_breakdown": ownership,
        "top_institutional_holders": top_institutional_holders,
        "note": "Insider buy/sell classification is derived from free-text SEC Form 4 "
        "descriptions (no reliable transaction-code field is available), so 'other' can "
        "include option exercises/awards that aren't a discretionary buy or sell.",
    }
