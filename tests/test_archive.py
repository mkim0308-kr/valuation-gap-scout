import json
from datetime import date

import pytest

from quant import archive


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    data_dir.mkdir()
    reports_dir.mkdir()
    monkeypatch.setattr(archive, "DATA_DIR", data_dir)
    monkeypatch.setattr(archive, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(archive, "HISTORY_DATA_DIR", data_dir / "history")
    monkeypatch.setattr(archive, "HISTORY_REPORTS_DIR", reports_dir / "history")
    return data_dir, reports_dir


def test_archive_run_copies_json_and_report_files(isolated_dirs):
    data_dir, reports_dir = isolated_dirs
    (data_dir / "AAPL_quant.json").write_text('{"a": 1}')
    (reports_dir / "AAPL_report.md").write_text("# report")
    (reports_dir / "AAPL_report.html").write_text("<html></html>")

    dest = archive.archive_run("AAPL", as_of=date(2026, 1, 15))

    assert dest == data_dir / "history" / "AAPL" / "2026-01-15"
    assert (dest / "AAPL_quant.json").read_text() == '{"a": 1}'
    assert (reports_dir / "history" / "AAPL" / "2026-01-15" / "AAPL_report.md").exists()
    assert (reports_dir / "history" / "AAPL" / "2026-01-15" / "AAPL_report.html").exists()


def test_archive_run_only_copies_this_tickers_files(isolated_dirs):
    data_dir, _ = isolated_dirs
    (data_dir / "AAPL_quant.json").write_text("{}")
    (data_dir / "NVDA_quant.json").write_text("{}")

    dest = archive.archive_run("AAPL", as_of=date(2026, 1, 15))

    assert (dest / "AAPL_quant.json").exists()
    assert not (dest / "NVDA_quant.json").exists()


def test_list_snapshot_dates_sorted_and_skips_non_dates(isolated_dirs):
    data_dir, _ = isolated_dirs
    (data_dir / "history" / "AAPL" / "2026-03-01").mkdir(parents=True)
    (data_dir / "history" / "AAPL" / "2026-01-01").mkdir(parents=True)
    (data_dir / "history" / "AAPL" / "not-a-date").mkdir(parents=True)

    assert archive.list_snapshot_dates("AAPL") == [date(2026, 1, 1), date(2026, 3, 1)]


def test_list_snapshot_dates_empty_when_no_history(isolated_dirs):
    assert archive.list_snapshot_dates("NOPE") == []


def test_load_reference_snapshot_picks_freshest_within_window(isolated_dirs):
    data_dir, _ = isolated_dirs
    for d, val in [("2025-08-01", 1), ("2025-11-01", 2), ("2026-01-10", 3)]:
        snap_dir = data_dir / "history" / "AAPL" / d
        snap_dir.mkdir(parents=True)
        (snap_dir / "AAPL_quant.json").write_text(json.dumps({"v": val}))

    # as_of 2026-02-01 -> window is roughly [2025-08-06, 2026-01-02]
    ref = archive.load_reference_snapshot("AAPL", as_of=date(2026, 2, 1))

    assert ref["snapshot_date"] == "2025-11-01"
    assert ref["quant"] == {"v": 2}


def test_load_reference_snapshot_none_when_only_too_recent(isolated_dirs):
    data_dir, _ = isolated_dirs
    snap_dir = data_dir / "history" / "AAPL" / "2026-01-30"
    snap_dir.mkdir(parents=True)
    (snap_dir / "AAPL_quant.json").write_text("{}")

    assert archive.load_reference_snapshot("AAPL", as_of=date(2026, 2, 1)) is None


def test_load_reference_snapshot_none_when_only_too_old(isolated_dirs):
    data_dir, _ = isolated_dirs
    snap_dir = data_dir / "history" / "AAPL" / "2025-01-01"
    snap_dir.mkdir(parents=True)
    (snap_dir / "AAPL_quant.json").write_text("{}")

    assert archive.load_reference_snapshot("AAPL", as_of=date(2026, 2, 1)) is None


def test_get_last_run_date_prefers_snapshot_history(isolated_dirs):
    data_dir, reports_dir = isolated_dirs
    (data_dir / "history" / "AAPL" / "2026-01-01").mkdir(parents=True)
    (reports_dir / "AAPL_report.html").write_text("<html></html>")

    assert archive.get_last_run_date("AAPL") == date(2026, 1, 1)


def test_get_last_run_date_falls_back_to_report_mtime(isolated_dirs):
    _, reports_dir = isolated_dirs
    report = reports_dir / "AAPL_report.html"
    report.write_text("<html></html>")

    assert archive.get_last_run_date("AAPL") == date.fromtimestamp(report.stat().st_mtime)


def test_get_last_run_date_none_when_never_run(isolated_dirs):
    assert archive.get_last_run_date("NOPE") is None


def test_list_stale_tickers(isolated_dirs):
    data_dir, _ = isolated_dirs
    (data_dir / "history" / "FRESH" / "2026-01-20").mkdir(parents=True)
    (data_dir / "history" / "OLD" / "2025-10-01").mkdir(parents=True)

    stale = archive.list_stale_tickers(
        ["FRESH", "OLD", "NEVER"], staleness_days=30, as_of=date(2026, 2, 1)
    )

    assert stale == ["OLD", "NEVER"]


def test_discover_tickers_from_reports_dir_excludes_summary(isolated_dirs):
    _, reports_dir = isolated_dirs
    (reports_dir / "AAPL_report.html").write_text("<html></html>")
    (reports_dir / "NVDA_report.html").write_text("<html></html>")
    (reports_dir / "summary_report.html").write_text("<html></html>")

    assert archive.discover_tickers() == ["AAPL", "NVDA"]


def test_discover_tickers_empty_when_no_reports(isolated_dirs):
    assert archive.discover_tickers() == []
