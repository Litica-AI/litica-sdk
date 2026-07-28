"""Client configuration resolution and the status-code -> exception mapping."""

from __future__ import annotations

import httpx
import pytest
from helpers import build_client, ok

import litica

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_api_key_required(monkeypatch):
    monkeypatch.delenv("LITICA_API_KEY", raising=False)
    with pytest.raises(litica.LiticaConfigError):
        litica.Client()


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("LITICA_API_KEY", "lk_from_env")
    client = litica.Client(transport=httpx.MockTransport(lambda r: ok({})))
    assert client.api_key == "lk_from_env"


def test_explicit_api_key_beats_the_environment(monkeypatch):
    monkeypatch.setenv("LITICA_API_KEY", "lk_from_env")
    client, rec = build_client(ok([]), api_key="lk_explicit")
    client.search_memories("q")
    assert rec.last.headers["X-API-Key"] == "lk_explicit"


def test_base_url_defaults_to_hosted(monkeypatch):
    monkeypatch.delenv("LITICA_BASE_URL", raising=False)
    monkeypatch.setenv("LITICA_API_KEY", "lk_x")
    client = litica.Client(transport=httpx.MockTransport(lambda r: ok({})))
    assert client.base_url == "https://mcp.litica.org"


def test_base_url_env_beats_default_but_not_argument(monkeypatch):
    monkeypatch.setenv("LITICA_API_KEY", "lk_x")
    monkeypatch.setenv("LITICA_BASE_URL", "http://localhost:8000")
    transport = httpx.MockTransport(lambda r: ok({}))

    assert litica.Client(transport=transport).base_url == "http://localhost:8000"
    explicit = litica.Client(base_url="https://other.test", transport=transport)
    assert explicit.base_url == "https://other.test"


def test_base_url_trailing_slash_is_normalized(monkeypatch):
    monkeypatch.setenv("LITICA_API_KEY", "lk_x")
    client = litica.Client(
        base_url="https://api.test/", transport=httpx.MockTransport(lambda r: ok({}))
    )
    assert client.base_url == "https://api.test"


def test_api_key_sent_on_every_request():
    client, rec = build_client(ok([]), api_key="lk_secret")
    client.search_memories("q")
    assert rec.last.headers["X-API-Key"] == "lk_secret"


def test_user_agent_identifies_the_sdk():
    client, rec = build_client(ok([]))
    client.search_memories("q")
    assert rec.last.headers["User-Agent"].startswith("litica-python/")


# --------------------------------------------------------------------------
# Error mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, litica.LiticaAuthError),
        (404, litica.LiticaNotFoundError),
        (409, litica.LiticaConflictError),
        (415, litica.LiticaUnsupportedMediaError),
        (422, litica.LiticaValidationError),
        (429, litica.LiticaRateLimitError),
        (500, litica.LiticaServerError),
        (503, litica.LiticaServerError),
        (418, litica.LiticaAPIError),
    ],
)
def test_status_maps_to_exception(status, exc):
    client, _ = build_client(httpx.Response(status, json={"detail": "boom"}))
    with pytest.raises(exc) as caught:
        client.get_tenant()
    assert caught.value.status_code == status
    assert caught.value.detail == "boom"
    assert caught.value.response is not None


def test_every_error_is_catchable_as_litica_error():
    client, _ = build_client(httpx.Response(500, json={"detail": "x"}))
    with pytest.raises(litica.LiticaError):
        client.get_tenant()


def test_rate_limit_carries_retry_after():
    client, _ = build_client(
        httpx.Response(429, json={"detail": "slow down"}, headers={"Retry-After": "60"})
    )
    with pytest.raises(litica.LiticaRateLimitError) as caught:
        client.get_tenant()
    assert caught.value.retry_after == 60


def test_rate_limit_without_header_defaults_to_none():
    client, _ = build_client(httpx.Response(429, json={"detail": "slow down"}))
    with pytest.raises(litica.LiticaRateLimitError) as caught:
        client.get_tenant()
    assert caught.value.retry_after is None


def test_detail_survives_a_non_json_error_body():
    client, _ = build_client(httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(litica.LiticaServerError) as caught:
        client.get_tenant()
    assert caught.value.status_code == 502
    assert "bad gateway" in caught.value.detail


def test_detail_is_not_reworded():
    client, _ = build_client(httpx.Response(404, json={"detail": "Memory 7 not found"}))
    with pytest.raises(litica.LiticaNotFoundError) as caught:
        client.delete_memory(7)
    assert caught.value.detail == "Memory 7 not found"


def test_request_timeout_becomes_litica_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    client, _ = build_client(handler)
    with pytest.raises(litica.LiticaTimeout):
        client.get_tenant()


def test_connection_error_becomes_litica_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    client, _ = build_client(handler)
    with pytest.raises(litica.LiticaConnectionError):
        client.get_tenant()


def test_client_works_as_a_context_manager():
    client, rec = build_client(ok({"tenant_id": "acme"}))
    with client as c:
        assert c.get_tenant() == "acme"
    assert rec.requests
