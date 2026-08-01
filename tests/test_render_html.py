import pytest

import render_html


@pytest.fixture
def sample_report(tmp_path, monkeypatch):
    monkeypatch.setattr(render_html, "REPORTS_DIR", tmp_path)
    md_path = tmp_path / "TEST_report.md"
    md_path.write_text(
        "⚠️ 테스트 고지문입니다.\n\n"
        "## TEST 정량 밸류에이션 브리핑\n\n"
        "| 항목 | 값 |\n|---|---|\n| DCF 적정가 | $100 |\n\n"
        "⚠️ 테스트 고지문입니다.\n"
    )
    return tmp_path


def test_render_report_html_produces_expected_file(sample_report):
    out_path = render_html.render_report_html("test")

    assert out_path == sample_report / "TEST_report.html"
    assert out_path.exists()


def test_render_report_html_marks_disclaimer_and_renders_table(sample_report):
    out_path = render_html.render_report_html("TEST")
    html = out_path.read_text()

    assert html.count('class="disclaimer"') == 2
    assert "<table>" in html
    assert "<h2>TEST 정량 밸류에이션 브리핑</h2>" in html
    assert "<title>TEST 정량 밸류에이션 브리핑</title>" in html


def test_render_report_html_raises_when_markdown_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(render_html, "REPORTS_DIR", tmp_path)

    with pytest.raises(FileNotFoundError):
        render_html.render_report_html("NOPE")
