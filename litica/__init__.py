"""Litica — human memory for AI agents.

A thin, synchronous client for the Litica HTTP API. One method per route.

::

    import litica

    client = litica.Client(api_key="lk_...")
    client.add_memory("Sam owns the Atlas pricing page.")
    for hit in client.search_memories("who owns pricing?"):
        print(hit.text)

Or, with the common shorthand::

    import litica as lc

    client = lc.Client(api_key="lk_...")
"""

from __future__ import annotations

__version__ = "0.1.0"

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
    ExplainResult,
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

#: Deprecated alias for :class:`Client`, kept for one release so the original
#: LIT-073 examples keep running. ``litica.Client`` is the supported name —
#: ``lc.LiticaClient(...)`` stutters under the usual ``import litica as lc``.
LiticaClient = Client

__all__ = [
    "__version__",
    "Client",
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
]
