from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from dgas.data.ingestion import IngestionSummary, backfill_intraday, incremental_update_intraday
from dgas.data.models import IntervalData


class DummyClient:
    def __init__(self, payload: List):
        self.payload = payload
        self.closed = False

    def fetch_intraday(self, *args, **kwargs):
        return self.payload

    def close(self):  # pragma: no cover - not used in tests where client passed in
        self.closed = True


class DummyConn:
    def __init__(self):
        self.symbols: List[tuple] = []
        self.data: List = []
        self.latest: datetime | None = None

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    # Cursor methods used in repository
    def execute(self, query, params=None):
        if "INSERT INTO market_symbols" in query:
            self.symbols.append(params)
            self._lastrow = (1,)
        elif "SELECT timestamp" in query:
            if self.latest is None:
                self._fetch_result = []
            else:
                self._fetch_result = [(self.latest,)]
        else:
            self._fetch_result = []

    def fetchone(self):
        return getattr(self, "_lastrow", None)

    def fetchall(self):
        return getattr(self, "_fetch_result", [])

    def mogrify(self, query, params=None):  # pragma: no cover - required by execute_values
        return query.encode()


@contextmanager
def dummy_connection_context(conn: DummyConn):
    yield conn


@pytest.fixture
def mock_repo(monkeypatch):
    conn = DummyConn()

    monkeypatch.setattr("dgas.data.ingestion.get_connection", lambda: dummy_connection_context(conn))
    monkeypatch.setattr("dgas.data.ingestion.ensure_market_symbol", lambda c, symbol, exchange: 1)

    def fake_upsert(c, symbol_id, interval, data):
        conn.data.extend(data)
        return len(data)

    monkeypatch.setattr("dgas.data.ingestion.bulk_upsert_market_data", fake_upsert)

    def fake_latest(c, symbol_id, interval):
        return conn.latest

    monkeypatch.setattr("dgas.data.ingestion.get_latest_timestamp", fake_latest)
    return conn


def _sample_intervals() -> List[IntervalData]:
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    raw = [
        {
            "code": "AAPL",
            "exchange_short_name": "US",
            "timestamp": int(base.timestamp()),
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 10,
        },
        {
            "code": "AAPL",
            "exchange_short_name": "US",
            "timestamp": int((base + timedelta(minutes=30)).timestamp()),
            "open": 101,
            "high": 102,
            "low": 100,
            "close": 101,
            "volume": 12,
        },
    ]
    return [IntervalData.from_api_record(item, interval="30m") for item in raw]


def test_backfill_intraday_persists_data(mock_repo, monkeypatch):
    data = _sample_intervals()
    client = DummyClient(data)

    summary = backfill_intraday(
        "AAPL",
        exchange="US",
        start_date="2024-01-01",
        end_date="2024-01-02",
        client=client,
    )

    assert isinstance(summary, IngestionSummary)
    assert summary.stored == len(data)
    assert summary.quality.total_bars == len(data)


def test_incremental_update_uses_default_start_when_empty(mock_repo, monkeypatch):
    client = DummyClient(_sample_intervals())

    summary = incremental_update_intraday(
        "AAPL",
        exchange="US",
        default_start="2024-01-01",
        client=client,
    )

    assert summary.fetched == 2


def test_incremental_update_requires_default_start_when_no_data(mock_repo):
    client = DummyClient([])

    with pytest.raises(ValueError):
        incremental_update_intraday(
            "AAPL",
            exchange="US",
            client=client,
        )
