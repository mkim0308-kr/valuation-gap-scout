import pandas as pd

from quant import market_data


def test_get_risk_free_rate_converts_percent_to_decimal_fraction(monkeypatch):
    class FakeTicker:
        def history(self, period):
            return pd.DataFrame({"Close": [4.70, 4.72, 4.745]})

    monkeypatch.setattr(market_data.yf, "Ticker", lambda symbol: FakeTicker())

    rate = market_data.get_risk_free_rate()

    assert rate == 0.04745


def test_get_risk_free_rate_raises_on_empty_history(monkeypatch):
    class FakeTicker:
        def history(self, period):
            return pd.DataFrame({"Close": []})

    monkeypatch.setattr(market_data.yf, "Ticker", lambda symbol: FakeTicker())

    try:
        market_data.get_risk_free_rate()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
