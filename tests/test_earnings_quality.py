import pytest

from quant.earnings_quality import compute_accruals_ratio, compute_beneish_m_score


def test_compute_accruals_ratio_matches_known_calculation():
    # (120 - 100) / 1000 = 0.02
    assert compute_accruals_ratio(net_income=120, operating_cash_flow=100, total_assets=1000) == 0.02


@pytest.mark.parametrize(
    "ni,ocf,ta", [(None, 100, 1000), (120, None, 1000), (120, 100, None), (120, 100, 0), (120, 100, -5)]
)
def test_compute_accruals_ratio_none_on_missing_or_invalid_inputs(ni, ocf, ta):
    assert compute_accruals_ratio(ni, ocf, ta) is None


def test_compute_beneish_m_score_matches_known_calculation():
    # All components = 1.0 except tata = 0
    # M = -4.84 + 0.92 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 + 0 - 0.327
    score = compute_beneish_m_score(
        dsri=1.0, gmi=1.0, aqi=1.0, sgi=1.0, depi=1.0, sgai=1.0, lvgi=1.0, tata=0.0
    )
    expected = -4.84 + 0.92 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 - 0.327
    assert score == pytest.approx(expected, abs=0.0001)


def test_compute_beneish_m_score_none_if_any_component_missing():
    assert compute_beneish_m_score(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None) is None
    assert compute_beneish_m_score(None, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0) is None
