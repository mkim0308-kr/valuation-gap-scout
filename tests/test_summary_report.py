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


def _write_quant(data_dir, ticker, current_price, fair_value, gap_pct, pe, roe):
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
    }
    (data_dir / f"{ticker}_quant.json").write_text(json.dumps(payload))


def test_build_roe_pe_scatter_svg_empty_when_no_points():
    svg = summary_report._build_roe_pe_scatter_svg([])
    assert "차트를 그릴 수 없습니다" in svg


def test_build_roe_pe_scatter_svg_renders_points_and_labels():
    points = [
        {"ticker": "AAPL", "pe": 30, "roe": 1.4},
        {"ticker": "NVDA", "pe": 45, "roe": 0.9},
    ]
    svg = summary_report._build_roe_pe_scatter_svg(points)

    assert svg.startswith("<svg")
    assert svg.count('class="chart-dot"') == 2
    assert ">AAPL<" in svg
    assert ">NVDA<" in svg


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


def test_build_summary_report_writes_html_with_links_and_chart(isolated_dirs):
    data_dir, reports_dir = isolated_dirs
    _write_quant(data_dir, "AAPL", 308.91, 94.57, 2.266, 38.5, 1.488)
    (reports_dir / "AAPL_report.html").write_text("<html></html>")

    out_path = summary_report.build_summary_report(["AAPL"], stale_tickers=[])

    assert out_path == reports_dir / "summary_report.html"
    html = out_path.read_text()
    assert 'href="AAPL_report.html"' in html
    assert "<svg" in html


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
