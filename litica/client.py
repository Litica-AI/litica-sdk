"""``litica.Client`` — one method per route over the Litica HTTP API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from . import _ops
from ._transport import Transport
from .errors import (
    LiticaConfigError,
    LiticaConnectionError,
    LiticaTimeout,
)
from .models import (
    AddEventPage,
    ApiKey,
    Graph,
    MemoryRow,
    MemoryTrace,
    MintedKey,
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


class _ScopedConfig:
    """Configuration and scope resolution shared by ``Client`` and ``AsyncClient``.

    Everything except the transport: API-key/base-URL/scope resolution follows
    the same argument → environment → default precedence in both clients, and
    ``_agent``/``_namespace`` apply the connection-level defaults that every
    scoped method inherits.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        agent_id: str | None = None,
        namespace_id: str | None = None,
        timeout: float = 30.0,
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

    # -- scope resolution --------------------------------------------------

    def _agent(self, value: Any) -> str:
        return self.agent_id if value is UNSET else value

    def _namespace(self, value: Any) -> str | None:
        return self.namespace_id if value is UNSET else value

    def _user_agent(self) -> str:
        from . import __version__

        return f"litica-python/{__version__}"

    def __repr__(self) -> str:
        scope = f"agent_id={self.agent_id!r}"
        if self.namespace_id:
            scope += f", namespace_id={self.namespace_id!r}"
        return f"{type(self).__name__}(base_url={self.base_url!r}, {scope})"


class Client(_ScopedConfig):
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
        super().__init__(
            api_key,
            base_url=base_url,
            agent_id=agent_id,
            namespace_id=namespace_id,
            timeout=timeout,
        )
        self._transport = Transport(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
            user_agent=self._user_agent(),
            transport=transport,
        )

    def _run(self, op: _ops.Op) -> Any:
        return op.parse(
            self._transport.request(
                op.method,
                op.path,
                params=op.params,
                json=op.json,
                files=op.files,
                data=op.data,
                timeout=op.timeout,
            )
        )

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
        return self._run(
            _ops.add_memory(
                content,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                session_id=session_id,
            )
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
        return self._run(
            _ops.add_memories_batch(
                contents,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                session_id=session_id,
            )
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

        with path.open("rb") as handle:
            return self._run(
                _ops.add_document(
                    path.name,
                    handle,
                    agent_id=self._agent(agent_id),
                    namespace_id=self._namespace(namespace_id),
                    session_id=session_id,
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
        return self._run(
            _ops.search_memories(
                query,
                top_k=top_k,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                session_id=session_id,
            )
        )

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
        return self._run(
            _ops.list_memories(
                top_k=top_k,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                include_archived=include_archived,
            )
        )

    def get_memory_trace(self, memory_id: int) -> MemoryTrace:
        """Retrieval lineage for one memory. ``GET /memories/{id}/trace``.

        ``rank`` inside ``retrievals`` is **0-based** — it is 1-based in
        ``search_explain``. Both are mirrored as the server sends them.
        """
        return self._run(_ops.get_memory_trace(memory_id))

    def delete_memory(self, memory_id: int) -> int:
        """Delete one memory. ``DELETE /memories/{id}``. Returns its id."""
        return self._run(_ops.delete_memory(memory_id))

    def clear_memories(self, *, agent_id: Any = UNSET) -> int:
        """Delete every memory for one agent. ``DELETE /memories``.

        Returns how many were removed. There is no undo.
        """
        return self._run(_ops.clear_memories(agent_id=self._agent(agent_id)))

    def list_queries(self, limit: int = 50) -> list[QueryRow]:
        """Recent logged queries, newest first. ``GET /queries``."""
        return self._run(_ops.list_queries(limit))

    def list_agents(self) -> list[str]:
        """Agent ids that have memories under this tenant. ``GET /agents``."""
        return self._run(_ops.list_agents())

    def get_tenant(self) -> str:
        """The tenant id this API key resolves to. ``GET /tenant``."""
        return self._run(_ops.get_tenant())

    def health(self) -> bool:
        """Whether the server is reachable and healthy. ``GET /health``.

        The one unauthenticated route. Returns ``False`` rather than raising
        when the server cannot be reached — a health check that explodes is
        not much of a health check.
        """
        try:
            return self._run(_ops.health())
        except (LiticaConnectionError, LiticaTimeout):
            return False

    # -- namespaces --------------------------------------------------------

    def list_namespaces(self) -> list[Namespace]:
        """Every namespace under this tenant. ``GET /namespaces``."""
        return self._run(_ops.list_namespaces())

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
        return self._run(
            _ops.create_namespace(
                name,
                read_policy=read_policy,
                write_policy=write_policy,
                agents=agents,
            )
        )

    def delete_namespace(self, namespace_id: str) -> str:
        """Delete a namespace. ``DELETE /namespaces/{id}``. Returns its id."""
        return self._run(_ops.delete_namespace(namespace_id))

    def list_namespace_agents(self, namespace_id: str) -> list[NamespaceAgent]:
        """Agents granted access to a namespace. ``GET /namespaces/{id}/agents``."""
        return self._run(_ops.list_namespace_agents(namespace_id))

    def grant_namespace_agent(
        self,
        namespace_id: str,
        agent_id: str,
        *,
        can_read: bool = True,
        can_write: bool = True,
    ) -> NamespaceAgent:
        """Grant an agent access. ``POST /namespaces/{id}/agents``. Upserts."""
        return self._run(
            _ops.grant_namespace_agent(
                namespace_id, agent_id, can_read=can_read, can_write=can_write
            )
        )

    def remove_namespace_agent(self, namespace_id: str, agent_id: str) -> str:
        """Revoke an agent's access. ``DELETE /namespaces/{id}/agents/{agent_id}``."""
        return self._run(_ops.remove_namespace_agent(namespace_id, agent_id))

    # -- api keys ----------------------------------------------------------

    def mint_key(self, *, label: str = "") -> MintedKey:
        """Mint a new API key for this tenant. ``POST /keys`` (201).

        The plaintext comes back **once** on ``.api_key`` — the server keeps
        only a hash, so it can never be shown again. Store it immediately and
        treat it like a password.

        The server caps active keys per tenant; minting past the cap is a
        409. Keys mint with full tenant access — there is no per-key scoping
        beyond an optional rate limit set server-side.
        """
        return self._run(_ops.mint_key(label=label))

    def list_keys(self) -> list[ApiKey]:
        """Metadata for every key under this tenant, newest first. ``GET /keys``.

        Metadata only — never the plaintext or its hash. Revoked keys stay in
        the list with ``revoked_at`` set.
        """
        return self._run(_ops.list_keys())

    def revoke_key(self, key_id: int) -> int:
        """Revoke one API key. ``DELETE /keys/{key_id}``. Returns its id.

        404 if the id belongs to another tenant or the key is already
        revoked. Revoking the key this client authenticates with cuts off
        this client too — its next call will 401.
        """
        return self._run(_ops.revoke_key(key_id))

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
        return self._run(
            _ops.viz_graph(
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                limit=limit,
            )
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
        return self._run(
            _ops.viz_add_events(
                since_id=since_id,
                limit=limit,
                order=order,
                agent_id=agent_id,
                namespace_id=namespace_id,
            )
        )

    def viz_pending(self, *, agent_id: Any = UNSET) -> int:
        """Write-queue depth for one agent. ``GET /viz/pending``."""
        return self._run(_ops.viz_pending(agent_id=self._agent(agent_id)))

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
        return self._run(
            _ops.search_explain(
                query,
                top_k=top_k,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                rehearse=rehearse,
                max_candidates=max_candidates,
                session_id=session_id,
                query_rf=query_rf,
            )
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._transport.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
