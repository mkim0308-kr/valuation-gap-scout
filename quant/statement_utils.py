"""Shared helper for reading yfinance financial-statement DataFrames, whose
row labels vary across yfinance versions and tickers."""
from __future__ import annotations


def first_value(df, candidates: list[str], period_index: int = 0) -> float | None:
    """Looks up a row by the first matching label in `candidates`, and
    returns the value `period_index` columns back (0 = most recent period,
    1 = the period before that). None if the row or period isn't there."""
    if df is None or df.empty:
        return None
    for name in candidates:
        if name in df.index:
            series = df.loc[name].dropna()
            if len(series) > period_index:
                return float(series.iloc[period_index])
    return None
