import pytest

from quant.sec_data import compute_cagr


def test_compute_cagr_basic():
    series = {2016: 100.0, 2026: 100.0 * (1.1**10)}
    assert compute_cagr(series) == pytest.approx(0.10, rel=1e-6)


def test_compute_cagr_needs_at_least_two_points():
    assert compute_cagr({2026: 100.0}) is None
    assert compute_cagr({}) is None


def test_compute_cagr_rejects_non_positive_endpoints():
    assert compute_cagr({2016: -50.0, 2026: 100.0}) is None
    assert compute_cagr({2016: 50.0, 2026: -100.0}) is None
