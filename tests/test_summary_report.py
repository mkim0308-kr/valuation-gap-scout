import json
from datetime import date, timedelta

import pytest

import summary_report
from quant import archive


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    data_dir.mkdir()
    reports_dir.mkdir()
    monkeypatch.setattr(summary_report, "DATA_DIR", data_dir)
    monkeypatch.setattr(summary_report, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(archive, "DATA_DIR", data_dir)
    monkeypatch.setattr(archive, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(archive, "HISTORY_DATA_DIR", data_dir / "history")
    monkeypatch.setattr(archive, "HISTORY_REPORTS_DIR", reports_dir / "history")
    return data_dir, reports_dir


def _write_quant(data_dir, ticker, current_price, fair_value, gap_pct, pe, roe, quarterly=None):
    payload = {
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
        "quarterly_timeseries": {"metrics": quarterly or {}},
    }
    (data_dir / f"{ticker}_quant.json").write_text(json.dumps(payload))


def test_build_table_html_shows_stale_badge_and_links():
    rows = [
        {
            "ticker": "AAPL",
            "current_price": 308.91,
            "fair_value_per_share": 94.57,
            "valuation_gap_pct": 2.266,
            "primary_moat": "switching_costs",
            "last_run_date": "2026-01-01",
            "is_stale": True,
        }
    ]

    html = summary_report._build_table_html(rows)

    assert 'href="AAPL_report.html"' in html
    assert "+226.6%" in html
    assert 'class="stale-badge"' in html
    assert "switching_costs" in html


def test_build_table_html_handles_missing_data():
    rows = [
        {
            "ticker": "SPCX",
            "current_price": None,
            "fair_value_per_share": None,
            "valuation_gap_pct": None,
            "primary_moat": None,
            "last_run_date": None,
            "is_stale": False,
        }
    ]

    html = summary_report._build_table_html(rows)

    assert "insufficient_data" in html
    assert ">—<" in html


def test_load_ticker_summary_reads_quant_and_moat(isolated_dirs):
    data_dir, _ = isolated_dirs
    _write_quant(data_dir, "AAPL", 308.91, 94.57, 2.266, 38.5, 1.488)
    (data_dir / "AAPL_tech_moat.json").write_text(
        json.dumps({"moat_evaluation": {"primary_moat_type": "switching_costs"}})
    )

    info = summary_report._load_ticker_summary("AAPL")

    assert info["current_price"] == 308.91
    assert info["primary_moat"] == "switching_costs"
    assert info["trailing_pe"] == 38.5
    assert info["roe"] == 1.488


def test_load_ticker_summary_missing_files_returns_nones(isolated_dirs):
    info = summary_report._load_ticker_summary("NOPE")

    assert info["current_price"] is None
    assert info["primary_moat"] is None


def test_build_summary_report_writes_html_with_links_and_charts(isolated_dirs):
    data_dir, reports_dir = isolated_dirs
    _write_quant(
        data_dir, "AAPL", 308.91, 94.57, 2.266, 38.5, 1.488,
        quarterly={
            "2025-Q4": {"fcf_ttm": 100.0, "roe_ttm": 0.3, "pe_ttm": 30.0, "end_date": "2025-12-31"}
        },
    )
    (reports_dir / "AAPL_report.html").write_text("<html></html>")

    out_path = summary_report.build_summary_report(["AAPL"], stale_tickers=[])

    assert out_path == reports_dir / "summary_report.html"
    html = out_path.read_text()
    assert 'href="AAPL_report.html"' in html
    assert 'id="scatter-svg"' in html
    assert 'id="trend-svg"' in html
    assert "<script>" in html
    assert '"AAPL"' in html  # embedded in CHART_DATA / ticker checkboxes
    assert 'name="scatter-ticker"' in html
    assert 'name="trend-ticker"' in html
    assert '"end_date": "2025-12-31"' in html
    assert "실제 캘린더" in html  # caption explaining fiscal-year-label caveat


def test_collect_quarterly_timeseries_reads_metrics_and_skips_missing(isolated_dirs):
    data_dir, _ = isolated_dirs
    _write_quant(
        data_dir, "AAPL", 308.91, 94.57, 2.266, 38.5, 1.488,
        quarterly={"2025-Q4": {"fcf_ttm": 100.0, "roe_ttm": 0.3}},
    )
    # NVDA has no quant.json at all -> should simply be absent, not fabricated

    result = summary_report._collect_quarterly_timeseries(["AAPL", "NVDA"])

    assert result == {"AAPL": {"2025-Q4": {"fcf_ttm": 100.0, "roe_ttm": 0.3}}}


def test_collect_quarterly_timeseries_skips_ticker_with_empty_metrics(isolated_dirs):
    data_dir, _ = isolated_dirs
    _write_quant(data_dir, "SPCX", None, None, None, None, None, quarterly={})

    result = summary_report._collect_quarterly_timeseries(["SPCX"])

    assert result == {}


def test_build_metric_options_marks_default_selected():
    html = summary_report._build_metric_options(default="roe_ttm")

    assert '<option value="fcf_ttm">' in html
    assert '<option value="roe_ttm" selected>' in html
    assert '<option value="pe_ttm">' in html


def test_build_ticker_checkboxes_all_checked_by_default():
    html = summary_report._build_ticker_checkboxes(["AAPL", "NVDA"], name="scatter-ticker")

    assert html.count('name="scatter-ticker"') == 2
    assert html.count("checked") == 2
    assert 'value="AAPL"' in html
    assert 'value="NVDA"' in html


def test_build_chart_js_embeds_data_and_defines_render_functions():
    chart_data = {
        "AAPL": {
            "2025-Q4": {"fcf_ttm": 100.0, "roe_ttm": 0.3, "pe_ttm": 30.0, "end_date": "2025-12-31"}
        }
    }

    js = summary_report._build_chart_js(chart_data, ["AAPL"])

    assert "const CHART_DATA = " in js
    assert '"AAPL"' in js
    assert '"fcf_ttm": 100.0' in js
    assert '"end_date": "2025-12-31"' in js
    assert "function renderScatter(" in js
    assert "function renderTrend(" in js
    assert "function updateScatterChart(" in js
    assert "function updateTrendChart(" in js
    # the trend chart positions by real end_date, not by fiscal-label order
    # (two tickers' same-numbered fiscal quarter can be many months apart)
    assert "m.end_date" in js
    assert "new Date(" in js
    # every opening brace introduced by JS code must be balanced (a stray
    # unescaped f-string brace would desync this, not just look wrong)
    assert js.count("{") == js.count("}")


def test_main_check_stale_lists_stale_tickers(isolated_dirs, monkeypatch, capsys):
    data_dir, reports_dir = isolated_dirs
    (reports_dir / "AAPL_report.html").write_text("<html></html>")
    old_date = (date.today() - timedelta(days=60)).isoformat()
    (data_dir / "history" / "AAPL" / old_date).mkdir(parents=True)

    monkeypatch.setattr("sys.argv", ["summary_report.py", "--check-stale", "--staleness-days", "30"])
    summary_report.main()

    captured = capsys.readouterr()
    assert "AAPL" in captured.out


def test_main_check_stale_all_fresh_message(isolated_dirs, monkeypatch, capsys):
    _, reports_dir = isolated_dirs
    (reports_dir / "AAPL_report.html").write_text("<html></html>")

    monkeypatch.setattr("sys.argv", ["summary_report.py", "--check-stale"])
    summary_report.main()

    captured = capsys.readouterr()
    assert "모든 티커가 최신 상태" in captured.out


def test_main_exits_when_no_reports_found(isolated_dirs, monkeypatch):
    monkeypatch.setattr("sys.argv", ["summary_report.py"])

    with pytest.raises(SystemExit):
        summary_report.main()
