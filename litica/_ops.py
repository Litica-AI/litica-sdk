"""One request-builder per route, shared by ``Client`` and ``AsyncClient``.

Each function returns an :class:`Op`: the HTTP verb, the path, the encoded
parameters, and a ``parse`` callable that turns the JSON body into the value
the client method returns. The sync and async clients differ only in how they
execute an ``Op`` — never in how one is built or parsed — so the two surfaces
cannot drift apart: the request building is shared, and the clients differ
only at the await.

Scope arguments arrive here already resolved: the clients apply their
connection-level ``agent_id``/``namespace_id`` defaults before calling in, so
an ``Op`` is a complete description of one request.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ._transport import clean
from .errors import LiticaValidationError
from .models import (
    AddEventPage,
    ApiKey,
    Graph,
    MemoryRow,
    MemoryTrace,
    MintedKey,
    Namespace,
    NamespaceAgent,
    ProvisionedTenant,
    QueryRow,
    QueuedBatch,
    QueuedDocument,
    QueuedWrite,
    SearchExplanation,
    SearchResult,
)


def _identity(payload: Any) -> Any:
    return payload


@dataclass(frozen=True, slots=True)
class Op:
    """One fully-described HTTP request and how to read its response."""

    method: str
    path: str
    params: dict[str, Any] | None = None
    json: Any = None
    files: Any = None
    data: dict[str, Any] | None = None
    timeout: float | None = None
    parse: Callable[[Any], Any] = _identity


# -- memories ----------------------------------------------------------------


def add_memory(
    content: str,
    *,
    agent_id: str | None,
    namespace_id: str | None,
    session_id: str | None,
) -> Op:
    body = clean(
        {
            "content": content,
            "agent_id": agent_id,
            "namespace_id": namespace_id,
            "session_id": session_id,
        }
    )
    return Op("POST", "/memories", json=body, parse=QueuedWrite.from_json)


def add_memories_batch(
    contents: list[str],
    *,
    agent_id: str | None,
    namespace_id: str | None,
    session_id: str | None,
) -> Op:
    if not contents:
        raise LiticaValidationError(
            "add_memories_batch requires at least one item "
            "(the route rejects an empty batch)."
        )
    body = clean(
        {
            "contents": list(contents),
            "agent_id": agent_id,
            "namespace_id": namespace_id,
            "session_id": session_id,
        }
    )
    return Op("POST", "/memories/batch", json=body, parse=QueuedBatch.from_json)


def add_document(
    filename: str,
    handle: Any,
    *,
    agent_id: str | None,
    namespace_id: str | None,
    session_id: str | None,
    timeout: float,
) -> Op:
    form = clean(
        {
            "agent_id": agent_id,
            "namespace_id": namespace_id,
            "session_id": session_id,
        }
    )
    return Op(
        "POST",
        "/documents",
        files={"file": (filename, handle)},
        data=form,
        timeout=timeout,
        parse=QueuedDocument.from_json,
    )


def search_memories(
    query: str,
    *,
    top_k: int,
    agent_id: str | None,
    namespace_id: str | None,
    session_id: str | None,
) -> Op:
    params = clean(
        {
            "query": query,
            "top_k": top_k,
            "agent_id": agent_id,
            "namespace_id": namespace_id,
            "session_id": session_id,
        }
    )
    return Op(
        "GET",
        "/memories/search",
        params=params,
        parse=lambda rows: [SearchResult.from_json(r) for r in rows or []],
    )


def list_memories(
    *,
    top_k: int,
    agent_id: str | None,
    namespace_id: str | None,
    include_archived: bool,
) -> Op:
    params = clean(
        {
            "top_k": top_k,
            "agent_id": agent_id,
            "namespace_id": namespace_id,
            "include_archived": include_archived,
        }
    )
    return Op(
        "GET",
        "/memories",
        params=params,
        parse=lambda rows: [MemoryRow.from_json(r) for r in rows or []],
    )


def get_memory_trace(memory_id: int) -> Op:
    return Op("GET", f"/memories/{memory_id}/trace", parse=MemoryTrace.from_json)


def delete_memory(memory_id: int) -> Op:
    return Op(
        "DELETE", f"/memories/{memory_id}", parse=lambda payload: payload["deleted"]
    )


def clear_memories(*, agent_id: str | None) -> Op:
    return Op(
        "DELETE",
        "/memories",
        params=clean({"agent_id": agent_id}),
        parse=lambda payload: payload["cleared"],
    )


def list_queries(limit: int) -> Op:
    return Op(
        "GET",
        "/queries",
        params={"limit": limit},
        parse=lambda rows: [QueryRow.from_json(r) for r in rows or []],
    )


def list_agents() -> Op:
    return Op("GET", "/agents", parse=lambda payload: payload["agents"])


def get_tenant() -> Op:
    return Op("GET", "/tenant", parse=lambda payload: payload["tenant_id"])


def health() -> Op:
    return Op(
        "GET",
        "/health",
        parse=lambda payload: bool(payload) and payload.get("status") == "ok",
    )


# -- namespaces ----------------------------------------------------------------


def list_namespaces() -> Op:
    return Op(
        "GET",
        "/namespaces",
        parse=lambda payload: [Namespace.from_json(n) for n in payload["namespaces"]],
    )


def create_namespace(
    name: str, *, read_policy: str, write_policy: str, agents: list[str] | None
) -> Op:
    body = {
        "name": name,
        "read_policy": read_policy,
        "write_policy": write_policy,
        "agents": list(agents or []),
    }
    return Op("POST", "/namespaces", json=body, parse=Namespace.from_json)


def delete_namespace(namespace_id: str) -> Op:
    return Op(
        "DELETE",
        f"/namespaces/{namespace_id}",
        parse=lambda payload: payload["deleted"],
    )


def list_namespace_agents(namespace_id: str) -> Op:
    return Op(
        "GET",
        f"/namespaces/{namespace_id}/agents",
        parse=lambda payload: [NamespaceAgent.from_json(a) for a in payload["agents"]],
    )


def grant_namespace_agent(
    namespace_id: str, agent_id: str, *, can_read: bool, can_write: bool
) -> Op:
    body = {"agent_id": agent_id, "can_read": can_read, "can_write": can_write}
    return Op(
        "POST",
        f"/namespaces/{namespace_id}/agents",
        json=body,
        parse=NamespaceAgent.from_json,
    )


def remove_namespace_agent(namespace_id: str, agent_id: str) -> Op:
    return Op(
        "DELETE",
        f"/namespaces/{namespace_id}/agents/{agent_id}",
        parse=lambda payload: payload["removed"],
    )


# -- api keys ------------------------------------------------------------------


def mint_key(*, label: str) -> Op:
    return Op("POST", "/keys", json={"label": label}, parse=MintedKey.from_json)


def list_keys() -> Op:
    return Op(
        "GET",
        "/keys",
        parse=lambda payload: [ApiKey.from_json(k) for k in payload["keys"]],
    )


def revoke_key(key_id: int) -> Op:
    return Op("DELETE", f"/keys/{key_id}", parse=lambda payload: payload["revoked"])


# -- admin (X-Admin-Key — AdminClient only) --------------------------------------


def provision(tenant_id: str, *, label: str) -> Op:
    # The route also accepts can_read/can_write, but the handler ignores them
    # entirely — the SDK does not expose parameters that do nothing.
    body = {"tenant_id": tenant_id, "label": label}
    return Op("POST", "/provision", json=body, parse=ProvisionedTenant.from_json)


# -- viz / explain -------------------------------------------------------------


def viz_graph(*, agent_id: str | None, namespace_id: str | None, limit: int) -> Op:
    params = clean({"agent_id": agent_id, "namespace_id": namespace_id, "limit": limit})
    return Op("GET", "/viz/graph", params=params, parse=Graph.from_json)


def viz_add_events(
    *,
    since_id: int,
    limit: int,
    order: str,
    agent_id: str | None,
    namespace_id: str | None,
) -> Op:
    params = clean(
        {
            "since_id": since_id,
            "limit": limit,
            "order": order,
            "agent_id": agent_id,
            "namespace_id": namespace_id,
        }
    )
    return Op("GET", "/viz/add-events", params=params, parse=AddEventPage.from_json)


def viz_pending(*, agent_id: str | None) -> Op:
    return Op(
        "GET",
        "/viz/pending",
        params=clean({"agent_id": agent_id}),
        parse=lambda payload: payload["pending"],
    )


def search_explain(
    query: str,
    *,
    top_k: int,
    agent_id: str | None,
    namespace_id: str | None,
    rehearse: bool,
    max_candidates: int,
    session_id: str | None,
    query_rf: dict | None,
) -> Op:
    body = clean(
        {
            "query": query,
            "top_k": top_k,
            "agent_id": agent_id,
            "namespace_id": namespace_id,
            "rehearse": rehearse,
            "max_candidates": max_candidates,
            "session_id": session_id,
            "query_rf": query_rf,
        }
    )
    return Op(
        "POST", "/viz/search-explain", json=body, parse=SearchExplanation.from_json
    )
