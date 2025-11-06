from datetime import datetime, timezone

from dgas.monitoring.report import (
    SymbolIngestionStats,
    generate_ingestion_report,
    render_markdown_report,
    write_report,
)


class DummyCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        self.executed = (query, params)

    def fetchall(self):
        return self.rows


class DummyConnection:
    def __init__(self, rows):
        self.cursor_instance = DummyCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance


def _dummy_rows():
    first = datetime(2024, 1, 1, tzinfo=timezone.utc)
    last = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return [
        ("AAPL", "US", "30min", 10, first, last, 0),
        ("MSFT", "US", "30min", 0, None, None, 0),
    ]


def test_generate_ingestion_report(monkeypatch):
    rows = _dummy_rows()
    dummy_conn = DummyConnection(rows)

    def fake_get_connection():
        return dummy_conn

    monkeypatch.setattr("dgas.monitoring.report.get_connection", fake_get_connection)

    stats = generate_ingestion_report(interval="30min")

    assert len(stats) == 2
    assert stats[0].symbol == "AAPL"
    assert stats[0].bar_count == 10
    assert stats[1].bar_count == 0


def test_render_and_write_markdown(tmp_path):
    stats = [
        SymbolIngestionStats(
            symbol="AAPL",
            exchange="US",
            interval="30min",
            bar_count=5,
            first_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            last_timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            estimated_missing_bars=1,
        )
    ]

    markdown = render_markdown_report(stats)
    assert "Symbol" in markdown and "AAPL" in markdown

    output_path = tmp_path / "report.md"
    write_report(stats, output_path)
    assert output_path.read_text(encoding="utf-8").startswith("| Symbol |")
