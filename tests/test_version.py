"""Basic sanity tests for package metadata."""

from dgas import get_version


def test_get_version_returns_string() -> None:
    result = get_version()
    assert isinstance(result, str)
    assert result
