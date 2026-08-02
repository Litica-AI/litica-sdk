"""Litica — human memory for AI agents.

A thin client for the Litica HTTP API. One method per route, in a synchronous
flavour (:class:`Client`) and an asynchronous one (:class:`AsyncClient`) with
identical surfaces.

::

    import litica

    client = litica.Client(api_key="lk_...")
    client.add_memory("Sam owns the Atlas pricing page.")
    for hit in client.search_memories("who owns pricing?"):
        print(hit.text)

Inside an ``asyncio`` service, same calls, awaited::

    async with litica.AsyncClient(api_key="lk_...") as client:
        await client.add_memory("Sam owns the Atlas pricing page.")

Or, with the conventional shorthand::

    import litica as lit

    client = lit.Client(api_key="lk_...")

Tenant provisioning is deliberately separate: :class:`AdminClient` takes the
server's admin credential (``LITICA_ADMIN_KEY``), and neither ordinary client
can reach it.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .admin import AdminClient
from .async_client import AsyncClient
from .client import Client
from .errors import (
    LiticaAPIError,
    LiticaAuthError,
    LiticaConfigError,
    LiticaConflictError,
    LiticaConnectionError,
    LiticaError,
    LiticaNotFoundError,
    LiticaRateLimitError,
    LiticaResponseError,
    LiticaServerError,
    LiticaTimeout,
    LiticaUnsupportedMediaError,
    LiticaValidationError,
)
from .models import (
    AddEventPage,
    ApiKey,
    ExplainResult,
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

#: Deprecated alias for :class:`Client`, kept for one release so the original
#: pre-release examples keep running. ``litica.Client`` is the supported name —
#: ``lit.LiticaClient(...)`` stutters under the usual ``import litica as lit``.
LiticaClient = Client

__all__ = [
    "__version__",
    "Client",
    "AsyncClient",
    "AdminClient",
    "LiticaClient",
    # errors
    "LiticaError",
    "LiticaConfigError",
    "LiticaResponseError",
    "LiticaTimeout",
    "LiticaConnectionError",
    "LiticaAPIError",
    "LiticaAuthError",
    "LiticaNotFoundError",
    "LiticaConflictError",
    "LiticaValidationError",
    "LiticaUnsupportedMediaError",
    "LiticaRateLimitError",
    "LiticaServerError",
    # models
    "SearchResult",
    "MemoryRow",
    "MemoryTrace",
    "QueryRow",
    "Namespace",
    "NamespaceAgent",
    "QueuedWrite",
    "QueuedBatch",
    "QueuedDocument",
    "Graph",
    "AddEventPage",
    "ExplainResult",
    "SearchExplanation",
    "ApiKey",
    "MintedKey",
    "ProvisionedTenant",
]
