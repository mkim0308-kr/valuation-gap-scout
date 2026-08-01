from datetime import date

from quant.options_market_signal import (
    compute_put_call_ratio,
    find_atm_strike,
    find_nearest_expiration,
)


def test_compute_put_call_ratio_matches_known_calculation():
    assert compute_put_call_ratio(put_total=50, call_total=100) == 0.5


def test_compute_put_call_ratio_none_when_no_call_activity():
    assert compute_put_call_ratio(put_total=50, call_total=0) is None
    assert compute_put_call_ratio(put_total=50, call_total=None) is None
    assert compute_put_call_ratio(put_total=None, call_total=100) is None


def test_find_nearest_expiration_picks_closest_to_target_window():
    today = date(2026, 1, 1)
    expirations = ["2026-01-05", "2026-01-31", "2026-03-01"]
    # target is ~30 days out -> 2026-01-31 (30 days) is closest
    assert find_nearest_expiration(expirations, today) == "2026-01-31"


def test_find_nearest_expiration_empty_list():
    assert find_nearest_expiration([], date.today()) is None


def test_find_atm_strike_picks_closest_strike():
    assert find_atm_strike([90, 100, 110, 120], current_price=103) == 100


def test_find_atm_strike_none_when_missing_data():
    assert find_atm_strike([], 100) is None
    assert find_atm_strike([90, 100], None) is None
