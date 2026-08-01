import math

import pytest

from quant.volatility_comparison import (
    compute_realized_volatility,
    compute_volatility_risk_premium,
)


def test_compute_realized_volatility_zero_for_constant_prices():
    closes = [100.0] * 30
    assert compute_realized_volatility(closes) == 0.0


def test_compute_realized_volatility_matches_known_calculation():
    # Two log returns: ln(110/100), ln(100/110) -> stdev computed manually
    closes = [100.0, 110.0, 100.0]
    r1 = math.log(110 / 100)
    r2 = math.log(100 / 110)
    mean = (r1 + r2) / 2
    variance = ((r1 - mean) ** 2 + (r2 - mean) ** 2) / (2 - 1)
    expected = round((variance**0.5) * (252**0.5), 4)
    assert compute_realized_volatility(closes) == expected


def test_compute_realized_volatility_none_with_too_few_closes():
    assert compute_realized_volatility([100.0]) is None
    assert compute_realized_volatility([]) is None


def test_compute_volatility_risk_premium_matches_known_calculation():
    assert compute_volatility_risk_premium(implied_vol=0.30, realized_vol=0.25) == pytest.approx(0.05)


def test_compute_volatility_risk_premium_none_when_missing_data():
    assert compute_volatility_risk_premium(None, 0.25) is None
    assert compute_volatility_risk_premium(0.30, None) is None
