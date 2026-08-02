import json

import pytest

from quant import trend


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(trend, "DATA_DIR", d)
    return d


def _quant(current_price, fair_value, gap_pct, pe, roe):
    return {
        "as_of": "2026-02-01T00:00:00+00:00",
        "dcf_model_output": {
            "current_price": current_price,
            "fair_value_per_share": fair_value,
            "valuation_gap_pct": gap_pct,
        },
        "relative_valuation": {
            "comps_multiples": {"trailing_pe": pe},
            "profitability": {"return_on_equity": roe},
        },
    }


def test_compute_trend_insufficient_data_when_no_current_quant(data_dir):
    result = trend.compute_trend("AAPL")

    assert result["insufficient_data"] is True
    assert "AAPL_quant.json" in result["reason"]


def test_compute_trend_insufficient_data_when_no_reference_snapshot(data_dir, monkeypatch):
    (data_dir / "AAPL_quant.json").write_text(json.dumps(_quant(100, 90, 0.11, 20, 0.3)))
    monkeypatch.setattr(trend.archive, "load_reference_snapshot", lambda ticker: None)

    result = trend.compute_trend("AAPL")

    assert result["insufficient_data"] is True
    assert "참조 스냅샷" in result["reason"]


def test_compute_trend_computes_field_diffs(data_dir, monkeypatch):
    (data_dir / "AAPL_quant.json").write_text(json.dumps(_quant(120, 100, 0.20, 25, 0.35)))
    reference = {"snapshot_date": "2025-12-01", "quant": _quant(100, 90, 0.111, 20, 0.30)}
    monkeypatch.setattr(trend.archive, "load_reference_snapshot", lambda ticker: reference)

    result = trend.compute_trend("AAPL")

    assert result["insufficient_data"] is False
    assert result["reference_snapshot_date"] == "2025-12-01"
    assert result["current_price"] == {
        "previous": 100,
        "current": 120,
        "change": 20,
        "change_pct": 20.0,
    }
    assert result["fair_value_per_share"]["change"] == 10
    assert result["valuation_gap_pct"]["change"] == pytest.approx(0.089, abs=0.001)
    assert result["trailing_pe"]["change"] == 5
    assert result["return_on_equity"]["change"] == pytest.approx(0.05, abs=1e-9)


def test_compute_trend_handles_missing_fields_gracefully(data_dir, monkeypatch):
    (data_dir / "AAPL_quant.json").write_text(json.dumps(_quant(120, None, None, 25, 0.35)))
    reference = {"snapshot_date": "2025-12-01", "quant": _quant(100, 90, 0.111, None, None)}
    monkeypatch.setattr(trend.archive, "load_reference_snapshot", lambda ticker: reference)

    result = trend.compute_trend("AAPL")

    assert result["fair_value_per_share"] == {
        "previous": 90,
        "current": None,
        "change": None,
        "change_pct": None,
    }
    assert result["trailing_pe"] == {
        "previous": None,
        "current": 25,
        "change": None,
        "change_pct": None,
    }


def test_save_trend_writes_file(data_dir, monkeypatch):
    monkeypatch.setattr(trend.archive, "load_reference_snapshot", lambda ticker: None)

    out_path = trend.save_trend("aapl")

    assert out_path == data_dir / "AAPL_trend.json"
    saved = json.loads(out_path.read_text())
    assert saved["ticker"] == "AAPL"
    assert saved["insufficient_data"] is True
