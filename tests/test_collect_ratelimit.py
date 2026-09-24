"""A 429 from a company's ArcGIS service is a rate limit, not a moved dataset (2026-09-24).

Before this, any 4xx — including 429 — raised FetchError, which made collect.py re-resolve the
layer and retry about a second later. South West Water's service had said "Retry after 60 sec",
so the retry failed too and the poll run died. These tests pin the corrected behaviour.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import collect  # noqa: E402


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"features": []}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 500:
            raise collect.requests.RequestException(f"HTTP {self.status_code}")


@pytest.fixture
def no_sleep(monkeypatch):
    """Record what the collector waits for instead of actually waiting.

    Also resets the per-run waiting budget, because each test stands for one poll run.
    """
    waits = []
    monkeypatch.setattr(collect.time, "sleep", lambda s: waits.append(s))
    monkeypatch.setattr(collect, "_rate_limit_spent", 0.0)
    return waits


def run_with(monkeypatch, responses):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(collect.requests, "get", fake_get)
    return calls


def test_http_429_waits_and_then_succeeds(monkeypatch, no_sleep):
    ok = FakeResponse(payload={"features": [{"attributes": {"a": 1}}]})
    calls = run_with(monkeypatch, [FakeResponse(429), ok])
    page = collect.query_page("http://example/0", 0, 10)
    assert page["features"] == [{"attributes": {"a": 1}}]
    assert len(calls) == 2
    assert no_sleep == [collect.RATE_LIMIT_WAIT_S], "should wait a full minute, not one second"


def test_arcgis_429_inside_a_200_is_also_a_rate_limit(monkeypatch, no_sleep):
    """South West Water's service returns HTTP 200 with the 429 in the body — the real failure."""
    body = {"error": {"code": 429, "message": "Unable to perform query. Too many requests.",
                      "details": ["API calls quota exceeded (6884 request units)!"]}}
    calls = run_with(monkeypatch, [FakeResponse(payload=body), FakeResponse(payload={"features": []})])
    collect.query_page("http://example/0", 0, 10)
    assert len(calls) == 2
    assert no_sleep == [collect.RATE_LIMIT_WAIT_S]


def test_server_retry_after_header_is_honoured(monkeypatch, no_sleep):
    limited = FakeResponse(429, headers={"Retry-After": "30"})
    run_with(monkeypatch, [limited, FakeResponse()])
    collect.query_page("http://example/0", 0, 10)
    assert no_sleep == [30.0]


def test_retry_after_is_capped(monkeypatch, no_sleep):
    limited = FakeResponse(429, headers={"Retry-After": "3600"})
    run_with(monkeypatch, [limited, FakeResponse()])
    collect.query_page("http://example/0", 0, 10)
    assert no_sleep == [collect.RATE_LIMIT_MAX_WAIT_S], "a poll must stay inside the job timeout"


def test_persistent_429_gives_up_without_re_resolving(monkeypatch, no_sleep):
    """Three attempts, then OSError — never FetchError, which would re-resolve a healthy layer."""
    calls = run_with(monkeypatch, [FakeResponse(429)])
    with pytest.raises(OSError) as e:
        collect.query_page("http://example/0", 0, 10)
    assert not isinstance(e.value, collect.FetchError)
    assert len(calls) == 3
    assert len(no_sleep) == 2, "waits between attempts, not after the last one"


def test_a_real_4xx_still_re_resolves(monkeypatch, no_sleep):
    """A 404 means the layer moved; that path must keep raising FetchError."""
    run_with(monkeypatch, [FakeResponse(404)])
    with pytest.raises(collect.FetchError):
        collect.query_page("http://example/0", 0, 10)
    assert no_sleep == [], "a moved dataset is not something to wait for"


def test_waiting_is_capped_for_the_whole_run(monkeypatch, no_sleep):
    """A poll shares one waiting budget, so a bad day cannot drag it into the job timeout."""
    run_with(monkeypatch, [FakeResponse(429)])
    for _ in range(3):
        with pytest.raises(OSError):
            collect.query_page("http://example/0", 0, 10)
    assert sum(no_sleep) <= collect.RATE_LIMIT_BUDGET_S
