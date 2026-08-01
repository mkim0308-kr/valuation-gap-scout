"""Analyst-estimates agent: reports what sell-side analysts have published
(price targets, recommendation distribution) — third-party opinions being
tallied factually, not this pipeline's own view. Deterministic, no LLM.
"""
from __future__ import annotations

import yfinance as yf

# Standard 1 (most bullish) - 5 (most bearish) recommendation scale.
RECOMMENDATION_WEIGHTS = {"strongBuy": 1, "buy": 2, "hold": 3, "sell": 4, "strongSell": 5}


def compute_target_implied_upside_pct(
    current_price: float | None, target_price: float | None
) -> float | None:
    """(target - current) / current * 100 — how far the target sits above or
    below the current price, as analysts' own published targets imply it.
    This reports what analysts said, not a claim this pipeline endorses."""
    if current_price is None or not target_price:
        return None
    return round((target_price - current_price) / current_price * 100, 2)


def compute_recommendation_mean_score(counts: dict[str, int]) -> float | None:
    """Weighted mean of the recommendation distribution on the standard
    1 (strong buy) - 5 (strong sell) scale. None if there are no ratings."""
    total = sum(counts.get(k, 0) for k in RECOMMENDATION_WEIGHTS)
    if total == 0:
        return None
    weighted_sum = sum(counts.get(k, 0) * w for k, w in RECOMMENDATION_WEIGHTS.items())
    return round(weighted_sum / total, 3)


def get_analyst_estimates(ticker: str) -> dict:
    t = yf.Ticker(ticker.upper())
    info = t.get_info()

    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    target_mean = info.get("targetMeanPrice")

    latest_counts = None
    recommendation_trend = []
    recommendations = t.recommendations
    if recommendations is not None and not recommendations.empty:
        for row in recommendations.to_dict(orient="records"):
            entry = {
                "period": row.get("period"),
                "strongBuy": row.get("strongBuy", 0),
                "buy": row.get("buy", 0),
                "hold": row.get("hold", 0),
                "sell": row.get("sell", 0),
                "strongSell": row.get("strongSell", 0),
            }
            recommendation_trend.append(entry)
        latest_counts = recommendation_trend[0] if recommendation_trend else None

    mean_score = compute_recommendation_mean_score(latest_counts) if latest_counts else None

    return {
        "ticker": ticker.upper(),
        "price_targets": {
            "mean": target_mean,
            "high": info.get("targetHighPrice"),
            "low": info.get("targetLowPrice"),
            "median": info.get("targetMedianPrice"),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
            "implied_upside_pct_vs_mean_target": compute_target_implied_upside_pct(
                current_price, target_mean
            ),
        },
        "recommendation_key": info.get("recommendationKey"),
        "recommendation_mean_score_1to5": mean_score,
        "recommendation_trend_by_month": recommendation_trend,
        "note": "This reports published sell-side analyst targets and ratings as-is — third "
        "party opinions being tallied, not a view this pipeline holds or endorses. "
        "recommendation_mean_score_1to5: 1.0 = unanimous Strong Buy, 5.0 = unanimous Strong Sell.",
    }
