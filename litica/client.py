"""``litica.Client`` — one method per route over the Litica HTTP API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from ._transport import Transport, clean
from .errors import (
    LiticaConfigError,
    LiticaConnectionError,
    LiticaTimeout,
    LiticaValidationError,
)
from .models import (
    AddEventPage,
    Graph,
    MemoryRow,
    MemoryTrace,
    Namespace,
    NamespaceAgent,
    QueryRow,
    QueuedBatch,
    QueuedDocument,
    QueuedWrite,
    SearchExplanation,
    SearchResult,
)

__all__ = ["Client"]

DEFAULT_BASE_URL = "https://mcp.litica.org"


class _Unset:
    """Sentinel for "argument not supplied".

    ``None`` cannot serve here: the namespace-scoping invariant makes
    ``namespace_id IS NULL`` a real scope (agent-private), so an explicit
    ``namespace_id=None`` has to mean something different from omitting it.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<unset>"

    def __bool__(self) -> bool:
        return False


UNSET: Any = _Unset()


class Client:
    """A synchronous client for the Litica HTTP API.

    ::

        import litica

        client = litica.Client(api_key="lk_...")
        client.add_memory("Sam owns the Atlas pricing page.")
        for hit in client.search_memories("who owns pricing?"):
            print(hit.text)

    Writes are queued, not instant: ``add_memory`` returns once the server has
    accepted the write, before it is searchable. See :meth:`add_memory`.

    ``agent_id`` and ``namespace_id`` are set once here and applied to every
    call that accepts them; any call can override them. Passing
    ``namespace_id=None`` explicitly means agent-private scope and overrides
    the client default.

    Configuration precedence is argument, then environment variable, then
    built-in default:

    ==================  ==========================  =========================
    Argument            Environment variable        Default
    ==================  ==========================  =========================
    ``api_key``         ``LITICA_API_KEY``          required
    ``base_url``        ``LITICA_BASE_URL``         ``https://mcp.litica.org``
    ``agent_id``        ``LITICA_AGENT_ID``         ``"default"``
    ``namespace_id``    ``LITICA_NAMESPACE_ID``     ``None``
    ==================  ==========================  =========================
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        agent_id: str | None = None,
        namespace_id: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("LITICA_API_KEY")
        if not resolved_key:
            raise LiticaConfigError(
                "No API key. Pass api_key=... or set the LITICA_API_KEY "
                "environment variable."
            )

        resolved_base = (
            base_url or os.environ.get("LITICA_BASE_URL") or DEFAULT_BASE_URL
        )

        self.api_key = resolved_key
        self.base_url = resolved_base.rstrip("/")
        self.agent_id = agent_id or os.environ.get("LITICA_AGENT_ID") or "default"
        self.namespace_id = namespace_id or os.environ.get("LITICA_NAMESPACE_ID")
        self.timeout = timeout

        from . import __version__

        self._transport = Transport(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
            user_agent=f"litica-python/{__version__}",
            transport=transport,
        )

    # -- scope resolution --------------------------------------------------

    def _agent(self, value: Any) -> str:
        return self.agent_id if value is UNSET else value

    def _namespace(self, value: Any) -> str | None:
        return self.namespace_id if value is UNSET else value

    # -- memories ----------------------------------------------------------

    def add_memory(
        self,
        content: str,
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
    ) -> QueuedWrite:
        """Queue one memory. ``POST /memories`` (202).

        Returns as soon as the server has **accepted** the write. The memory is
        **not searchable yet** — decomposition, embedding, and persistence all
        happen in the background, so a search issued immediately after this
        call will usually come back empty.

        There is no built-in wait: the server currently exposes no signal that
        reliably says "this write has landed". Poll until your content appears:

        ::

            client.add_memory("Sam owns pricing.")

            for _ in range(20):
                if any("Sam" in h.text for h in client.search_memories("pricing")):
                    break
                time.sleep(3)
        """
        body = clean(
            {
                "content": content,
                "agent_id": self._agent(agent_id),
                "namespace_id": self._namespace(namespace_id),
                "session_id": session_id,
            }
        )
        return QueuedWrite.from_json(
            self._transport.request("POST", "/memories", json=body)
        )

    def add_memories_batch(
        self,
        contents: list[str],
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
    ) -> QueuedBatch:
        """Queue several memories in one call. ``POST /memories/batch`` (202).

        Queued, not yet searchable — same as :meth:`add_memory`.

        The namespace write ACL is checked once for the whole batch, and
        enqueue order is persist order. The server caps batch size; an
        over-cap batch comes back as a 422.
        """
        if not contents:
            raise LiticaValidationError(
                "add_memories_batch requires at least one item "
                "(the route rejects an empty batch)."
            )
        body = clean(
            {
                "contents": list(contents),
                "agent_id": self._agent(agent_id),
                "namespace_id": self._namespace(namespace_id),
                "session_id": session_id,
            }
        )
        return QueuedBatch.from_json(
            self._transport.request("POST", "/memories/batch", json=body)
        )

    def add_document(
        self,
        file_path: str | Path,
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
        timeout: float = 120.0,
    ) -> QueuedDocument:
        """Upload a document to ingest as memories. ``POST /documents`` (202).

        PDF, DOCX, PPTX, or text. The server parses it to text at the edge and
        queues the decomposition; a type it cannot parse is a 415, and a file
        with no extractable text is a 422.

        Queued, not yet searchable — same as :meth:`add_memory`, and more so
        here: one document fans out into many memories, so expect a longer
        gap before everything is retrievable.

        ``timeout`` is the upload's HTTP timeout, raised from the client
        default because large files take a while to transfer and parse.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")

        form = clean(
            {
                "agent_id": self._agent(agent_id),
                "namespace_id": self._namespace(namespace_id),
                "session_id": session_id,
            }
        )
        with path.open("rb") as handle:
            return QueuedDocument.from_json(
                self._transport.request(
                    "POST",
                    "/documents",
                    files={"file": (path.name, handle)},
                    data=form,
                    timeout=timeout,
                )
            )

    def search_memories(
        self,
        query: str,
        *,
        top_k: int = 5,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
    ) -> list[SearchResult]:
        """Search memories. ``GET /memories/search``.

        Returns a plain list — this route answers with a bare JSON array where
        most others return an object, and the SDK does not invent a wrapper.
        """
        params = clean(
            {
                "query": query,
                "top_k": top_k,
                "agent_id": self._agent(agent_id),
                "namespace_id": self._namespace(namespace_id),
                "session_id": session_id,
            }
        )
        rows = self._transport.request("GET", "/memories/search", params=params) or []
        return [SearchResult.from_json(r) for r in rows]

    def list_memories(
        self,
        *,
        top_k: int = 10,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        include_archived: bool = False,
    ) -> list[MemoryRow]:
        """Recent memories, newest first. ``GET /memories``.

        Consolidated-away memories are hidden by default;
        ``include_archived=True`` is the explicit window into the archive.
        """
        params = clean(
            {
                "top_k": top_k,
                "agent_id": self._agent(agent_id),
                "namespace_id": self._namespace(namespace_id),
                "include_archived": include_archived,
            }
        )
        rows = self._transport.request("GET", "/memories", params=params) or []
        return [MemoryRow.from_json(r) for r in rows]

    def get_memory_trace(self, memory_id: int) -> MemoryTrace:
        """Retrieval lineage for one memory. ``GET /memories/{id}/trace``.

        ``rank`` inside ``retrievals`` is **0-based** — it is 1-based in
        ``search_explain``. Both are mirrored as the server sends them.
        """
        return MemoryTrace.from_json(
            self._transport.request("GET", f"/memories/{memory_id}/trace")
        )

    def delete_memory(self, memory_id: int) -> int:
        """Delete one memory. ``DELETE /memories/{id}``. Returns its id."""
        payload = self._transport.request("DELETE", f"/memories/{memory_id}")
        return payload["deleted"]

    def clear_memories(self, *, agent_id: Any = UNSET) -> int:
        """Delete every memory for one agent. ``DELETE /memories``.

        Returns how many were removed. There is no undo.
        """
        params = clean({"agent_id": self._agent(agent_id)})
        payload = self._transport.request("DELETE", "/memories", params=params)
        return payload["cleared"]

    def list_queries(self, limit: int = 50) -> list[QueryRow]:
        """Recent logged queries, newest first. ``GET /queries``."""
        rows = self._transport.request("GET", "/queries", params={"limit": limit}) or []
        return [QueryRow.from_json(r) for r in rows]

    def list_agents(self) -> list[str]:
        """Agent ids that have memories under this tenant. ``GET /agents``."""
        return self._transport.request("GET", "/agents")["agents"]

    def get_tenant(self) -> str:
        """The tenant id this API key resolves to. ``GET /tenant``."""
        return self._transport.request("GET", "/tenant")["tenant_id"]

    def health(self) -> bool:
        """Whether the server is reachable and healthy. ``GET /health``.

        The one unauthenticated route. Returns ``False`` rather than raising
        when the server cannot be reached — a health check that explodes is
        not much of a health check.
        """
        try:
            payload = self._transport.request("GET", "/health")
        except (LiticaConnectionError, LiticaTimeout):
            return False
        return bool(payload) and payload.get("status") == "ok"

    # -- namespaces --------------------------------------------------------

    def list_namespaces(self) -> list[Namespace]:
        """Every namespace under this tenant. ``GET /namespaces``."""
        payload = self._transport.request("GET", "/namespaces")
        return [Namespace.from_json(n) for n in payload["namespaces"]]

    def create_namespace(
        self,
        name: str,
        *,
        read_policy: str = "grant",
        write_policy: str = "grant",
        agents: list[str] | None = None,
    ) -> Namespace:
        """Create a shared namespace. ``POST /namespaces`` (201).

        Policies are ``"grant"`` (explicit access only) or ``"open"`` (any
        agent in the tenant). Listed ``agents`` are granted read and write.
        The server caps agents per namespace and rejects duplicate names with
        a 409 — those rules stay server-side rather than being copied here.
        """
        body = {
            "name": name,
            "read_policy": read_policy,
            "write_policy": write_policy,
            "agents": list(agents or []),
        }
        return Namespace.from_json(
            self._transport.request("POST", "/namespaces", json=body)
        )

    def delete_namespace(self, namespace_id: str) -> str:
        """Delete a namespace. ``DELETE /namespaces/{id}``. Returns its id."""
        payload = self._transport.request("DELETE", f"/namespaces/{namespace_id}")
        return payload["deleted"]

    def list_namespace_agents(self, namespace_id: str) -> list[NamespaceAgent]:
        """Agents granted access to a namespace. ``GET /namespaces/{id}/agents``."""
        payload = self._transport.request("GET", f"/namespaces/{namespace_id}/agents")
        return [NamespaceAgent.from_json(a) for a in payload["agents"]]

    def grant_namespace_agent(
        self,
        namespace_id: str,
        agent_id: str,
        *,
        can_read: bool = True,
        can_write: bool = True,
    ) -> NamespaceAgent:
        """Grant an agent access. ``POST /namespaces/{id}/agents``. Upserts."""
        body = {"agent_id": agent_id, "can_read": can_read, "can_write": can_write}
        return NamespaceAgent.from_json(
            self._transport.request(
                "POST", f"/namespaces/{namespace_id}/agents", json=body
            )
        )

    def remove_namespace_agent(self, namespace_id: str, agent_id: str) -> str:
        """Revoke an agent's access. ``DELETE /namespaces/{id}/agents/{agent_id}``."""
        payload = self._transport.request(
            "DELETE", f"/namespaces/{namespace_id}/agents/{agent_id}"
        )
        return payload["removed"]

    # -- viz / explain -----------------------------------------------------

    def viz_graph(
        self,
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        limit: int = 300,
    ) -> Graph:
        """Memory graph for one scope. ``GET /viz/graph``.

        ``truncated`` flags that ``limit`` cut the result short.
        """
        params = clean(
            {
                "agent_id": self._agent(agent_id),
                "namespace_id": self._namespace(namespace_id),
                "limit": limit,
            }
        )
        return Graph.from_json(
            self._transport.request("GET", "/viz/graph", params=params)
        )

    def viz_add_events(
        self,
        *,
        since_id: int = 0,
        limit: int = 100,
        order: str = "asc",
        agent_id: str | None = None,
        namespace_id: str | None = None,
    ) -> AddEventPage:
        """Cursor feed over the write-side audit trail. ``GET /viz/add-events``.

        Poll with ascending order and feed ``cursor`` back as ``since_id``;
        ``order="desc", limit=1`` bootstraps the cursor.

        Unlike every other scoped method here, ``agent_id`` and
        ``namespace_id`` do **not** inherit the client defaults. They default
        to ``None``, meaning all scopes. Silently narrowing an audit feed to
        the connection's agent is the opposite of what an audit feed is for.
        """
        params = clean(
            {
                "since_id": since_id,
                "limit": limit,
                "order": order,
                "agent_id": agent_id,
                "namespace_id": namespace_id,
            }
        )
        return AddEventPage.from_json(
            self._transport.request("GET", "/viz/add-events", params=params)
        )

    def viz_pending(self, *, agent_id: Any = UNSET) -> int:
        """Write-queue depth for one agent. ``GET /viz/pending``."""
        params = clean({"agent_id": self._agent(agent_id)})
        return self._transport.request("GET", "/viz/pending", params=params)["pending"]

    def search_explain(
        self,
        query: str,
        *,
        top_k: int = 5,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        rehearse: bool = True,
        max_candidates: int = 25,
        session_id: str | None = None,
        query_rf: dict | None = None,
    ) -> SearchExplanation:
        """Search with the full score breakdown. ``POST /viz/search-explain``.

        **With the default ``rehearse=True`` this is a production search.** It
        strengthens the memories it returns and logs the query, exactly like
        :meth:`search_memories`. Calling it in a loop to poke at rankings will
        distort the rankings you are poking at.

        Pass ``rehearse=False`` for the side-effect-free what-if: nothing is
        strengthened, nothing is logged. ``query_rf`` supplies a pre-decomposed
        query to skip the LLM call; it is ignored when ``rehearse=True``.
        """
        body = clean(
            {
                "query": query,
                "top_k": top_k,
                "agent_id": self._agent(agent_id),
                "namespace_id": self._namespace(namespace_id),
                "rehearse": rehearse,
                "max_candidates": max_candidates,
                "session_id": session_id,
                "query_rf": query_rf,
            }
        )
        return SearchExplanation.from_json(
            self._transport.request("POST", "/viz/search-explain", json=body)
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._transport.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        scope = f"agent_id={self.agent_id!r}"
        if self.namespace_id:
            scope += f", namespace_id={self.namespace_id!r}"
        return f"Client(base_url={self.base_url!r}, {scope})"
