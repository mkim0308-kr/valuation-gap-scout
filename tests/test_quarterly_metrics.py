from quant.quarterly_metrics import compute_pe_series, compute_roe_series


def test_compute_roe_series_matches_known_calculation():
    ttm_net_income = {"2024-Q1": 20.0, "2024-Q2": 25.0}
    equity_series = {"2024-Q1": 100.0, "2024-Q2": 100.0}
    assert compute_roe_series(ttm_net_income, equity_series) == {
        "2024-Q1": 0.2,
        "2024-Q2": 0.25,
    }


def test_compute_roe_series_skips_quarters_missing_equity():
    ttm_net_income = {"2024-Q1": 20.0, "2024-Q2": 25.0}
    equity_series = {"2024-Q1": 100.0}  # Q2 equity missing
    assert compute_roe_series(ttm_net_income, equity_series) == {"2024-Q1": 0.2}


def test_compute_roe_series_skips_non_positive_equity():
    ttm_net_income = {"2024-Q1": 20.0}
    equity_series = {"2024-Q1": -50.0}
    assert compute_roe_series(ttm_net_income, equity_series) == {}


def test_compute_roe_series_empty_input():
    assert compute_roe_series({}, {}) == {}


def test_compute_pe_series_matches_known_calculation():
    # market cap = 150 * 10 = 1500; P/E = 1500 / 100 = 15.0
    ttm_net_income = {"2024-Q1": 100.0}
    price_by_quarter = {"2024-Q1": 150.0}
    assert compute_pe_series(ttm_net_income, price_by_quarter, current_shares_outstanding=10.0) == {
        "2024-Q1": 15.0
    }


def test_compute_pe_series_excludes_non_positive_earnings():
    ttm_net_income = {"2024-Q1": -100.0, "2024-Q2": 0.0, "2024-Q3": 50.0}
    price_by_quarter = {"2024-Q1": 150.0, "2024-Q2": 150.0, "2024-Q3": 150.0}
    result = compute_pe_series(ttm_net_income, price_by_quarter, current_shares_outstanding=10.0)
    assert result == {"2024-Q3": 30.0}


def test_compute_pe_series_skips_quarters_missing_price():
    ttm_net_income = {"2024-Q1": 100.0, "2024-Q2": 100.0}
    price_by_quarter = {"2024-Q1": 150.0}  # Q2 price missing
    result = compute_pe_series(ttm_net_income, price_by_quarter, current_shares_outstanding=10.0)
    assert result == {"2024-Q1": 15.0}


def test_compute_pe_series_none_when_no_shares_outstanding():
    ttm_net_income = {"2024-Q1": 100.0}
    price_by_quarter = {"2024-Q1": 150.0}
    assert compute_pe_series(ttm_net_income, price_by_quarter, current_shares_outstanding=None) == {}
    assert compute_pe_series(ttm_net_income, price_by_quarter, current_shares_outstanding=0) == {}
