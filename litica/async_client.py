"""``litica.AsyncClient`` — the same methods as ``Client``, awaitable.

Method bodies are not forked: both clients build and parse every request
through ``litica._ops`` and differ only at the await (LIT-082). Docstrings
here state the route and anything async-specific; the full behaviour story
for each call lives on the matching :class:`litica.Client` method, and a
parity test asserts the two surfaces stay identical.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from . import _ops
from ._transport import AsyncTransport
from .client import UNSET, _ScopedConfig
from .errors import LiticaConnectionError, LiticaTimeout
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

__all__ = ["AsyncClient"]


class AsyncClient(_ScopedConfig):
    """An asynchronous client for the Litica HTTP API.

    The async twin of :class:`litica.Client`: same methods, same signatures,
    same responses — every call is awaitable and the connection pool is
    ``httpx.AsyncClient``. Reach for this inside an ``asyncio`` service (a
    FastAPI handler, an async agent loop); reach for :class:`litica.Client`
    everywhere else — scripts, notebooks, workers.

    ::

        import litica

        async with litica.AsyncClient(api_key="lk_...") as client:
            await client.add_memory("Sam owns the Atlas pricing page.")
            for hit in await client.search_memories("who owns pricing?"):
                print(hit.text)

    Configuration precedence (argument, then environment variable, then
    built-in default) matches :class:`litica.Client` exactly.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        agent_id: str | None = None,
        namespace_id: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            agent_id=agent_id,
            namespace_id=namespace_id,
            timeout=timeout,
        )
        self._transport = AsyncTransport(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
            user_agent=self._user_agent(),
            transport=transport,
        )

    async def _run(self, op: _ops.Op) -> Any:
        return op.parse(
            await self._transport.request(
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

    async def add_memory(
        self,
        content: str,
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
    ) -> QueuedWrite:
        """Queue one memory. ``POST /memories`` (202).

        Accepted is not searchable: the write lands in the background, so
        poll — ``await asyncio.sleep(...)`` between searches — until your
        content appears. See :meth:`litica.Client.add_memory` for the full
        story.
        """
        return await self._run(
            _ops.add_memory(
                content,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                session_id=session_id,
            )
        )

    async def add_memories_batch(
        self,
        contents: list[str],
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
    ) -> QueuedBatch:
        """Queue several memories in one call. ``POST /memories/batch`` (202).

        Queued, not yet searchable — same as :meth:`add_memory`. See
        :meth:`litica.Client.add_memories_batch`.
        """
        return await self._run(
            _ops.add_memories_batch(
                contents,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                session_id=session_id,
            )
        )

    async def add_document(
        self,
        file_path: str | Path,
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
        timeout: float = 120.0,
    ) -> QueuedDocument:
        """Upload a document to ingest as memories. ``POST /documents`` (202).

        The file is read from disk synchronously (stdlib file I/O); the upload
        itself is async. See :meth:`litica.Client.add_document` for formats
        and error codes.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")

        with path.open("rb") as handle:
            return await self._run(
                _ops.add_document(
                    path.name,
                    handle,
                    agent_id=self._agent(agent_id),
                    namespace_id=self._namespace(namespace_id),
                    session_id=session_id,
                    timeout=timeout,
                )
            )

    async def search_memories(
        self,
        query: str,
        *,
        top_k: int = 5,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        session_id: str | None = None,
    ) -> list[SearchResult]:
        """Search memories. ``GET /memories/search``.

        Returns a plain list, mirroring the route's bare JSON array — see
        :meth:`litica.Client.search_memories`.
        """
        return await self._run(
            _ops.search_memories(
                query,
                top_k=top_k,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                session_id=session_id,
            )
        )

    async def list_memories(
        self,
        *,
        top_k: int = 10,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        include_archived: bool = False,
    ) -> list[MemoryRow]:
        """Recent memories, newest first. ``GET /memories``.

        ``include_archived=True`` is the explicit window into the archive —
        see :meth:`litica.Client.list_memories`.
        """
        return await self._run(
            _ops.list_memories(
                top_k=top_k,
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                include_archived=include_archived,
            )
        )

    async def get_memory_trace(self, memory_id: int) -> MemoryTrace:
        """Retrieval lineage for one memory. ``GET /memories/{id}/trace``.

        ``rank`` inside ``retrievals`` is **0-based** — it is 1-based in
        ``search_explain``. Both are mirrored as the server sends them.
        """
        return await self._run(_ops.get_memory_trace(memory_id))

    async def delete_memory(self, memory_id: int) -> int:
        """Delete one memory. ``DELETE /memories/{id}``. Returns its id."""
        return await self._run(_ops.delete_memory(memory_id))

    async def clear_memories(self, *, agent_id: Any = UNSET) -> int:
        """Delete every memory for one agent. ``DELETE /memories``.

        Returns how many were removed. There is no undo.
        """
        return await self._run(_ops.clear_memories(agent_id=self._agent(agent_id)))

    async def list_queries(self, limit: int = 50) -> list[QueryRow]:
        """Recent logged queries, newest first. ``GET /queries``."""
        return await self._run(_ops.list_queries(limit))

    async def list_agents(self) -> list[str]:
        """Agent ids that have memories under this tenant. ``GET /agents``."""
        return await self._run(_ops.list_agents())

    async def get_tenant(self) -> str:
        """The tenant id this API key resolves to. ``GET /tenant``."""
        return await self._run(_ops.get_tenant())

    async def health(self) -> bool:
        """Whether the server is reachable and healthy. ``GET /health``.

        The one unauthenticated route. Returns ``False`` rather than raising
        when the server cannot be reached — matching
        :meth:`litica.Client.health`.
        """
        try:
            return await self._run(_ops.health())
        except (LiticaConnectionError, LiticaTimeout):
            return False

    # -- namespaces --------------------------------------------------------

    async def list_namespaces(self) -> list[Namespace]:
        """Every namespace under this tenant. ``GET /namespaces``."""
        return await self._run(_ops.list_namespaces())

    async def create_namespace(
        self,
        name: str,
        *,
        read_policy: str = "grant",
        write_policy: str = "grant",
        agents: list[str] | None = None,
    ) -> Namespace:
        """Create a shared namespace. ``POST /namespaces`` (201).

        Policies are ``"grant"`` or ``"open"`` — see
        :meth:`litica.Client.create_namespace`.
        """
        return await self._run(
            _ops.create_namespace(
                name,
                read_policy=read_policy,
                write_policy=write_policy,
                agents=agents,
            )
        )

    async def delete_namespace(self, namespace_id: str) -> str:
        """Delete a namespace. ``DELETE /namespaces/{id}``. Returns its id."""
        return await self._run(_ops.delete_namespace(namespace_id))

    async def list_namespace_agents(self, namespace_id: str) -> list[NamespaceAgent]:
        """Agents granted access to a namespace. ``GET /namespaces/{id}/agents``."""
        return await self._run(_ops.list_namespace_agents(namespace_id))

    async def grant_namespace_agent(
        self,
        namespace_id: str,
        agent_id: str,
        *,
        can_read: bool = True,
        can_write: bool = True,
    ) -> NamespaceAgent:
        """Grant an agent access. ``POST /namespaces/{id}/agents``. Upserts."""
        return await self._run(
            _ops.grant_namespace_agent(
                namespace_id, agent_id, can_read=can_read, can_write=can_write
            )
        )

    async def remove_namespace_agent(self, namespace_id: str, agent_id: str) -> str:
        """Revoke an agent's access. ``DELETE /namespaces/{id}/agents/{agent_id}``."""
        return await self._run(_ops.remove_namespace_agent(namespace_id, agent_id))

    # -- viz / explain -----------------------------------------------------

    async def viz_graph(
        self,
        *,
        agent_id: Any = UNSET,
        namespace_id: Any = UNSET,
        limit: int = 300,
    ) -> Graph:
        """Memory graph for one scope. ``GET /viz/graph``.

        ``truncated`` flags that ``limit`` cut the result short.
        """
        return await self._run(
            _ops.viz_graph(
                agent_id=self._agent(agent_id),
                namespace_id=self._namespace(namespace_id),
                limit=limit,
            )
        )

    async def viz_add_events(
        self,
        *,
        since_id: int = 0,
        limit: int = 100,
        order: str = "asc",
        agent_id: str | None = None,
        namespace_id: str | None = None,
    ) -> AddEventPage:
        """Cursor feed over the write-side audit trail. ``GET /viz/add-events``.

        Deliberately does **not** inherit the client's ``agent_id`` /
        ``namespace_id`` defaults — an audit feed must not be silently
        narrowed. See :meth:`litica.Client.viz_add_events`.
        """
        return await self._run(
            _ops.viz_add_events(
                since_id=since_id,
                limit=limit,
                order=order,
                agent_id=agent_id,
                namespace_id=namespace_id,
            )
        )

    async def viz_pending(self, *, agent_id: Any = UNSET) -> int:
        """Write-queue depth for one agent. ``GET /viz/pending``."""
        return await self._run(_ops.viz_pending(agent_id=self._agent(agent_id)))

    async def search_explain(
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

        **With the default ``rehearse=True`` this is a production search** —
        it strengthens what it returns and logs the query. Pass
        ``rehearse=False`` for the side-effect-free what-if. See
        :meth:`litica.Client.search_explain`.
        """
        return await self._run(
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

    async def close(self) -> None:
        """Close the underlying connection pool."""
        await self._transport.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
