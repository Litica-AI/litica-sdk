"""AsyncClient: surface parity with Client, and the async-specific plumbing.

Request building and parsing are shared with the sync client through
``litica._ops``, so the per-method request-shape coverage in the sync suite
already covers both. What this file pins down is (a) that the two surfaces
cannot drift — every sync route method exists on AsyncClient with an identical
signature — and (b) the plumbing that is genuinely different on the async
path: transport, error mapping, lifecycle.
"""

from __future__ import annotations

import inspect

import httpx
import pytest
from helpers import build_async_client, ok

import litica

# Lifecycle differs by design (sync close vs awaitable close); everything else
# public must match one-to-one.
LIFECYCLE = {"close"}


def _route_methods(cls) -> set[str]:
    return {
        name
        for name, member in vars(cls).items()
        if not name.startswith("_") and callable(member) and name not in LIFECYCLE
    }


# --------------------------------------------------------------------------
# Parity — the SDK-side drift guard
# --------------------------------------------------------------------------


def test_async_client_covers_every_sync_route_method():
    missing = _route_methods(litica.Client) - _route_methods(litica.AsyncClient)
    assert not missing, f"AsyncClient is missing route methods: {sorted(missing)}"


def test_async_client_adds_no_extra_route_methods():
    extra = _route_methods(litica.AsyncClient) - _route_methods(litica.Client)
    assert not extra, f"AsyncClient has methods Client lacks: {sorted(extra)}"


def test_every_route_method_is_an_identical_coroutine():
    for name in sorted(_route_methods(litica.Client)):
        sync_fn = getattr(litica.Client, name)
        async_fn = getattr(litica.AsyncClient, name)
        assert inspect.iscoroutinefunction(async_fn), f"{name} is not async"
        assert inspect.signature(async_fn) == inspect.signature(sync_fn), (
            f"{name}: async signature diverged from sync"
        )
        assert (async_fn.__doc__ or "").strip(), f"{name} lost its docstring"


# --------------------------------------------------------------------------
# The async plumbing itself
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_memory_posts_and_inherits_the_agent_default():
    client, rec = build_async_client(ok({"queued": True}, status=202), agent_id="bot")
    result = await client.add_memory("Sam owns pricing.")
    assert result.queued is True
    assert rec.last.method == "POST"
    assert rec.last.url.path == "/memories"
    assert rec.last_json["agent_id"] == "bot"
    assert rec.last.headers["X-API-Key"] == "lk_test"


@pytest.mark.anyio
async def test_explicit_none_namespace_overrides_the_client_default():
    client, rec = build_async_client(ok([]), namespace_id="team-shared")
    await client.search_memories("q", namespace_id=None)
    assert "namespace_id" not in rec.param_names


@pytest.mark.anyio
async def test_search_parses_rows_through_the_shared_models():
    client, rec = build_async_client(ok([{"id": 7, "text": "a", "extra": "kept"}]))
    hits = await client.search_memories("q", top_k=3)
    assert rec.param("top_k") == "3"
    assert hits[0].id == 7
    assert hits[0].raw["extra"] == "kept"


@pytest.mark.anyio
async def test_error_mapping_survives_the_async_path():
    client, _ = build_async_client(httpx.Response(404, json={"detail": "nope"}))
    with pytest.raises(litica.LiticaNotFoundError) as caught:
        await client.delete_memory(41)
    assert caught.value.status_code == 404
    assert caught.value.detail == "nope"


@pytest.mark.anyio
async def test_empty_batch_is_rejected_before_any_request():
    client, rec = build_async_client(ok({"queued": 0}))
    with pytest.raises(litica.LiticaValidationError):
        await client.add_memories_batch([])
    assert not rec.requests


@pytest.mark.anyio
async def test_add_document_uploads_multipart(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("hello")
    client, rec = build_async_client(
        ok({"queued": True, "filename": "notes.txt", "chars": 5}, status=202)
    )
    result = await client.add_document(doc)
    assert result.queued is True
    assert rec.last.url.path == "/documents"
    assert b"notes.txt" in rec.last.content


@pytest.mark.anyio
async def test_add_events_does_not_inherit_client_scope_defaults():
    """The deliberate audit-feed exception holds on the async surface too."""
    client, rec = build_async_client(
        ok({"events": [], "cursor": 0}),
        agent_id="support-bot",
        namespace_id="team-shared",
    )
    await client.viz_add_events()
    assert "agent_id" not in rec.param_names
    assert "namespace_id" not in rec.param_names


@pytest.mark.anyio
async def test_health_returns_false_when_unreachable():
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client, _ = build_async_client(explode)
    assert await client.health() is False


@pytest.mark.anyio
async def test_async_context_manager_closes_the_pool():
    client, _ = build_async_client(ok({"status": "ok"}))
    async with client as c:
        assert await c.health() is True
    assert c._transport._client.is_closed


def test_repr_names_the_class():
    client, _ = build_async_client(ok({}), agent_id="bot")
    assert repr(client).startswith("AsyncClient(")
