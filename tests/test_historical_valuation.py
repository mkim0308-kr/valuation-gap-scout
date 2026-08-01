from quant.historical_valuation import compute_price_percentile


def test_compute_price_percentile_at_the_top():
    result = compute_price_percentile(100, [50, 60, 70, 80, 90])
    assert result["percentile"] == 100.0
    assert result["min"] == 50
    assert result["max"] == 90
    assert result["median"] == 70


def test_compute_price_percentile_at_the_bottom():
    result = compute_price_percentile(10, [50, 60, 70, 80, 90])
    assert result["percentile"] == 0.0


def test_compute_price_percentile_in_the_middle():
    result = compute_price_percentile(70, [50, 60, 70, 80, 90])
    # 3 of 5 historical prices are <= 70
    assert result["percentile"] == 60.0


def test_compute_price_percentile_none_when_missing_data():
    result = compute_price_percentile(None, [50, 60])
    assert result["percentile"] is None

    result = compute_price_percentile(70, [])
    assert result["percentile"] is None
