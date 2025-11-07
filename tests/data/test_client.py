from unittest.mock import Mock

import pytest

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.errors import EODHDAuthError, EODHDRateLimitError


def _make_response(status_code: int, json_payload=None, headers=None, text: str = "") -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_payload
    response.headers = headers or {}
    response.text = text
    return response


def test_fetch_intraday_success(monkeypatch) -> None:
    session = Mock()
    payload = [
        {
            "code": "AAPL",
            "exchange_short_name": "US",
            "timestamp": 1_700_000_000,
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 10,
        }
    ]
    session.get.return_value = _make_response(200, payload)

    config = EODHDConfig(api_token="token", session=session, requests_per_minute=1000)
    client = EODHDClient(config)

    monkeypatch.setattr(client._rate_limiter, "acquire", lambda: None)

    bars = client.fetch_intraday("AAPL")

    assert len(bars) == 1
    assert bars[0].symbol == "AAPL"
    session.get.assert_called_once()


def test_fetch_intraday_raises_on_auth_failure(monkeypatch) -> None:
    session = Mock()
    session.get.return_value = _make_response(401, text="Unauthorized")

    config = EODHDConfig(api_token="token", session=session, requests_per_minute=1000)
    client = EODHDClient(config)
    monkeypatch.setattr(client._rate_limiter, "acquire", lambda: None)

    with pytest.raises(EODHDAuthError):
        client.fetch_intraday("AAPL")


def test_fetch_intraday_rate_limit_exhausts_retries(monkeypatch) -> None:
    session = Mock()
    response = _make_response(429, headers={"Retry-After": "0"})
    session.get.side_effect = [response, response]

    config = EODHDConfig(
        api_token="token",
        session=session,
        requests_per_minute=1000,
        max_retries=2,
    )
    client = EODHDClient(config)

    monkeypatch.setattr(client._rate_limiter, "acquire", lambda: None)
    monkeypatch.setattr("dgas.data.client.time.sleep", lambda _: None)

    with pytest.raises(EODHDRateLimitError):
        client.fetch_intraday("AAPL")

    assert session.get.call_count == 2
