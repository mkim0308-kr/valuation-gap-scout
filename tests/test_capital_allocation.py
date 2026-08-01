from quant.capital_allocation import compute_allocation_mix


def test_compute_allocation_mix_matches_known_calculation():
    totals = {"capex": 100, "rd": 200, "buybacks": 600, "dividends": 100, "ma": 0}
    mix = compute_allocation_mix(totals)
    assert mix == {"capex": 10.0, "rd": 20.0, "buybacks": 60.0, "dividends": 10.0, "ma": 0.0}


def test_compute_allocation_mix_all_none_when_nothing_deployed():
    totals = {"capex": 0, "rd": 0, "buybacks": 0, "dividends": 0, "ma": 0}
    mix = compute_allocation_mix(totals)
    assert all(v is None for v in mix.values())


def test_compute_allocation_mix_treats_missing_category_as_zero_share():
    totals = {"capex": 100, "rd": None, "buybacks": 0, "dividends": 0, "ma": 0}
    mix = compute_allocation_mix(totals)
    assert mix["capex"] == 100.0
    assert mix["rd"] == 0.0
