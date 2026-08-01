import pytest

from quant.relative_valuation import compute_graham_number, compute_peg_ratio, compute_roic


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


def test_compute_roic_matches_known_calculation():
    # NOPAT = 100 * (1 - 0.2) = 80; invested capital = 200 + 300 - 50 = 450
    # ROIC = 80 / 450 = 0.17778
    roic = compute_roic(ebit=100, total_debt=200, total_equity=300, cash=50, effective_tax_rate=0.2)
    assert roic == pytest.approx(0.17778, abs=0.00001)


def test_compute_roic_none_when_invested_capital_not_positive():
    # total_debt + total_equity - cash <= 0
    assert compute_roic(ebit=100, total_debt=10, total_equity=10, cash=50, effective_tax_rate=0.2) is None


@pytest.mark.parametrize(
    "ebit,debt,equity,cash,tax",
    [
        (None, 200, 300, 50, 0.2),
        (100, None, 300, 50, 0.2),
        (100, 200, None, 50, 0.2),
        (100, 200, 300, None, 0.2),
        (100, 200, 300, 50, None),
    ],
)
def test_compute_roic_none_when_any_input_missing(ebit, debt, equity, cash, tax):
    assert compute_roic(ebit, debt, equity, cash, tax) is None
