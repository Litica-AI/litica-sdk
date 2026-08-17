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


# --------------------------------------------------------------------------
# Envelope routes: a broken body is a LiticaResponseError, never a KeyError
#
# These routes answer with a one-key envelope instead of a model, so they do
# not go through a ``from_json``. Reading the key directly would raise a bare
# ``KeyError`` (or a ``TypeError`` on a 204, which decodes to ``None``), and
# neither is a ``LiticaError`` — which would make the documented catch-all a
# lie for a third of the surface.
# --------------------------------------------------------------------------

ENVELOPE_ROUTES = [
    ("delete_memory", lambda c: c.delete_memory(1)),
    ("clear_memories", lambda c: c.clear_memories()),
    ("list_agents", lambda c: c.list_agents()),
    ("get_tenant", lambda c: c.get_tenant()),
    ("list_namespaces", lambda c: c.list_namespaces()),
    ("delete_namespace", lambda c: c.delete_namespace("ns_1")),
    ("list_namespace_agents", lambda c: c.list_namespace_agents("ns_1")),
    ("remove_namespace_agent", lambda c: c.remove_namespace_agent("ns_1", "a")),
    ("list_keys", lambda c: c.list_keys()),
    ("revoke_key", lambda c: c.revoke_key(1)),
    ("viz_pending", lambda c: c.viz_pending()),
]

BROKEN_BODIES = [
    ("missing key", lambda: ok({"unexpected": 1})),
    ("empty object", lambda: ok({})),
    ("no content", lambda: httpx.Response(204)),
    ("array instead of object", lambda: ok([])),
]


@pytest.mark.parametrize(
    ("route", "call"), ENVELOPE_ROUTES, ids=[r[0] for r in ENVELOPE_ROUTES]
)
@pytest.mark.parametrize(
    ("shape", "body"), BROKEN_BODIES, ids=[b[0] for b in BROKEN_BODIES]
)
def test_broken_envelope_raises_response_error(route, call, shape, body):
    client, _ = build_client(body())
    with pytest.raises(litica.LiticaResponseError):
        call(client)


def test_broken_envelope_names_the_route_and_the_missing_key():
    client, _ = build_client(ok({"unexpected": 1}))
    with pytest.raises(litica.LiticaResponseError) as caught:
        client.get_tenant()
    assert "get_tenant" in str(caught.value)
    assert "tenant_id" in str(caught.value)
    assert "unexpected" in str(caught.value)


def test_envelope_routes_still_unwrap_a_good_body():
    client, _ = build_client(ok({"deleted": 7}))
    assert client.delete_memory(7) == 7

    client, _ = build_client(ok({"agents": ["a", "b"]}))
    assert client.list_agents() == ["a", "b"]

    client, _ = build_client(ok({"keys": [{"id": 1, "label": "ci"}]}))
    assert [k.id for k in client.list_keys()] == [1]


def test_null_envelope_list_reads_as_empty():
    client, _ = build_client(ok({"namespaces": None}))
    assert client.list_namespaces() == []


def test_health_never_raises_on_a_malformed_body():
    for make_body in (
        lambda: httpx.Response(204),
        lambda: ok([]),
        lambda: ok(["up"]),
        lambda: ok("ok"),
        lambda: ok({}),
    ):
        client, _ = build_client(make_body())
        assert client.health() is False


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
