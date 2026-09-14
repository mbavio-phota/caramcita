import httpx
import pytest

from caramcita.http import Http


def _http(handler, monkeypatch=None):
    h = Http(delay=0, retries=2, forbidden_pause=0)
    h.client = httpx.Client(transport=httpx.MockTransport(handler))
    return h


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("caramcita.http.time.sleep", lambda s: None)


def test_403_retried_once_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(403 if len(calls) == 1 else 200, text="ok")

    assert _http(handler).get_text("https://x/") == "ok"
    assert len(calls) == 2


def test_403_twice_raises_without_more_retries():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(403)

    with pytest.raises(httpx.HTTPStatusError):
        _http(handler).get("https://x/")
    assert len(calls) == 2


def test_404_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        _http(handler).get("https://x/")
    assert len(calls) == 1


def test_500_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500 if len(calls) < 3 else 200, text="ok")

    assert _http(handler).get_text("https://x/") == "ok"
    assert len(calls) == 3
