import pytest

from quant.relative_valuation import compute_graham_number, compute_peg_ratio


def test_compute_graham_number_matches_known_calculation():
    # sqrt(22.5 * 5 * 20) = sqrt(2250) = 47.4342...
    assert compute_graham_number(eps=5, book_value_per_share=20) == pytest.approx(47.43, abs=0.01)


@pytest.mark.parametrize("eps,book_value", [(0, 20), (-1, 20), (5, 0), (5, -3), (None, 20), (5, None)])
def test_compute_graham_number_undefined_for_non_positive_or_missing_inputs(eps, book_value):
    assert compute_graham_number(eps, book_value) is None


def test_compute_peg_ratio_matches_known_calculation():
    # PE 30, growth 15% -> PEG 2.0
    assert compute_peg_ratio(pe_ratio=30, growth_rate_pct=15) == pytest.approx(2.0)


@pytest.mark.parametrize(
    "pe,growth", [(0, 15), (-10, 15), (30, 0), (30, -5), (None, 15), (30, None)]
)
def test_compute_peg_ratio_undefined_for_non_positive_or_missing_inputs(pe, growth):
    assert compute_peg_ratio(pe, growth) is None
