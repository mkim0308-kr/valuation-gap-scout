from quant.short_interest import compute_short_interest_change_pct


def test_compute_short_interest_change_pct_matches_known_calculation():
    # (110 - 100) / 100 * 100 = 10.0
    assert compute_short_interest_change_pct(110, 100) == 10.0


def test_compute_short_interest_change_pct_negative_when_shrinking():
    assert compute_short_interest_change_pct(90, 100) == -10.0


def test_compute_short_interest_change_pct_none_when_missing_data():
    assert compute_short_interest_change_pct(None, 100) is None
    assert compute_short_interest_change_pct(110, None) is None
    assert compute_short_interest_change_pct(110, 0) is None
