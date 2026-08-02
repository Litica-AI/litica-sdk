"""Typed responses — frozen dataclasses mirroring the JSON as the server sends it.

No renaming, no re-nesting, no computed fields, no unit conversions.
``created_at`` stays the ISO-8601 string the server emits rather than becoming a
``datetime``, because the server sends ``null`` for rows without one and a
silent ``None``-vs-``datetime`` union is worse than a string.

Parsing is deliberately asymmetric:

* **Unknown keys never raise.** Every model keeps the untouched body on
  ``.raw``, so a server that grows a field does not break an older SDK and a
  caller can reach the new field before the SDK catches up.
* **Missing identity keys raise** (:class:`~litica.errors.LiticaResponseError`)
  — a response with no ``id`` is a real contract break worth failing loudly on.
* **Missing enrichment keys default to ``None``** — fields like
  ``source_agent_id`` are not present on every path, and demanding them would
  make the SDK brittle for no gain.

Deeply nested viz payloads (graph nodes, trace candidates, audit events) stay as
plain dicts. They are large, UI-shaped, and change with the retrieval internals;
typing them would buy fragility rather than safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import LiticaResponseError

__all__ = [
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
]


def _require(data: Any, key: str, model: str) -> Any:
    if not isinstance(data, dict):
        raise LiticaResponseError(
            f"Expected a JSON object for {model}, got {type(data).__name__}"
        )
    if key not in data:
        raise LiticaResponseError(
            f"{model} response is missing the required field {key!r}. "
            f"Received keys: {sorted(data)}"
        )
    return data[key]


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One hit from ``search_memories``."""

    id: int
    text: str
    created_at: str | None = None
    source_agent_id: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> SearchResult:
        return cls(
            id=_require(data, "id", "SearchResult"),
            text=_require(data, "text", "SearchResult"),
            created_at=data.get("created_at"),
            source_agent_id=data.get("source_agent_id"),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class MemoryRow:
    """One row from ``list_memories``."""

    id: int
    text: str
    created_at: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> MemoryRow:
        return cls(
            id=_require(data, "id", "MemoryRow"),
            text=_require(data, "text", "MemoryRow"),
            created_at=data.get("created_at"),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class MemoryTrace:
    """Full retrieval lineage for one memory.

    ``retrievals`` entries carry a **0-based** ``rank`` — unlike
    ``search_explain``, where rank is 1-based. Mirrored as sent; a renumbering
    fix belongs on the server.
    """

    id: int
    text: str
    agent_id: str | None = None
    namespace_id: str | None = None
    field_: str | None = None
    reference_frame: dict = field(default_factory=dict)
    created_at: str | None = None
    retrieval_count: int = 0
    salience: float | None = None
    last_retrieved_at: str | None = None
    retrievals: list[dict] = field(default_factory=list)
    linked_memories: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> MemoryTrace:
        return cls(
            id=_require(data, "id", "MemoryTrace"),
            text=_require(data, "text", "MemoryTrace"),
            agent_id=data.get("agent_id"),
            namespace_id=data.get("namespace_id"),
            field_=data.get("field"),
            reference_frame=data.get("reference_frame") or {},
            created_at=data.get("created_at"),
            retrieval_count=data.get("retrieval_count", 0),
            salience=data.get("salience"),
            last_retrieved_at=data.get("last_retrieved_at"),
            retrievals=data.get("retrievals") or [],
            linked_memories=data.get("linked_memories") or [],
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class QueryRow:
    """One logged query from ``list_queries``."""

    id: int
    query_text: str
    agent_id: str | None = None
    namespace_id: str | None = None
    top_k: int | None = None
    result_count: int | None = None
    created_at: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> QueryRow:
        return cls(
            id=_require(data, "id", "QueryRow"),
            query_text=_require(data, "query_text", "QueryRow"),
            agent_id=data.get("agent_id"),
            namespace_id=data.get("namespace_id"),
            top_k=data.get("top_k"),
            result_count=data.get("result_count"),
            created_at=data.get("created_at"),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class NamespaceAgent:
    """One agent's grant within a namespace."""

    agent_id: str
    can_read: bool = False
    can_write: bool = False
    namespace_id: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> NamespaceAgent:
        return cls(
            agent_id=_require(data, "agent_id", "NamespaceAgent"),
            can_read=data.get("can_read", False),
            can_write=data.get("can_write", False),
            namespace_id=data.get("namespace_id"),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class Namespace:
    """A shared memory space."""

    namespace_id: str
    name: str
    read_policy: str | None = None
    write_policy: str | None = None
    created_at: str | None = None
    agents: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> Namespace:
        return cls(
            namespace_id=_require(data, "namespace_id", "Namespace"),
            name=_require(data, "name", "Namespace"),
            read_policy=data.get("read_policy"),
            write_policy=data.get("write_policy"),
            created_at=data.get("created_at"),
            agents=data.get("agents") or [],
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class ApiKey:
    """Metadata for one API key — never the key material itself.

    The server stores only a hash, so neither the plaintext nor the hash ever
    appears here. ``revoked_at`` set means the key is dead.
    """

    id: int
    label: str | None = None
    created_at: str | None = None
    revoked_at: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> ApiKey:
        return cls(
            id=_require(data, "id", "ApiKey"),
            label=data.get("label"),
            created_at=data.get("created_at"),
            revoked_at=data.get("revoked_at"),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class MintedKey:
    """A freshly minted API key.

    ``api_key`` is the plaintext, shown **once** — the server keeps only a
    hash, so it can never be recovered. ``key`` is the same key's metadata
    row (``None`` if the server could not echo it back).
    """

    api_key: str
    key: ApiKey | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> MintedKey:
        key_row = data.get("key") if isinstance(data, dict) else None
        return cls(
            api_key=_require(data, "api_key", "MintedKey"),
            key=ApiKey.from_json(key_row) if key_row else None,
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class QueuedWrite:
    """Ack for a single queued memory. ``queued=True`` means *accepted*, not
    *searchable* — see ``Client.add_memory`` and the ``wait=`` parameter."""

    queued: bool
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> QueuedWrite:
        return cls(queued=_require(data, "queued", "QueuedWrite"), raw=data)


@dataclass(frozen=True, slots=True)
class QueuedBatch:
    """Ack for a batch. ``queued`` is how many were accepted."""

    queued: int
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> QueuedBatch:
        return cls(queued=_require(data, "queued", "QueuedBatch"), raw=data)


@dataclass(frozen=True, slots=True)
class QueuedDocument:
    """Ack for a document upload, with what the server extracted at the edge."""

    queued: bool
    filename: str | None = None
    chars: int | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> QueuedDocument:
        return cls(
            queued=_require(data, "queued", "QueuedDocument"),
            filename=data.get("filename"),
            chars=data.get("chars"),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class Graph:
    """Memory graph for one scope. ``nodes``/``links`` stay as plain dicts."""

    nodes: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    scope: dict = field(default_factory=dict)
    truncated: bool = False
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> Graph:
        return cls(
            nodes=_require(data, "nodes", "Graph") or [],
            links=_require(data, "links", "Graph") or [],
            scope=data.get("scope") or {},
            truncated=data.get("truncated", False),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class AddEventPage:
    """One page of the write-side audit feed. Pass ``cursor`` back as
    ``since_id`` to continue."""

    events: list[dict] = field(default_factory=list)
    cursor: int = 0
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> AddEventPage:
        return cls(
            events=_require(data, "events", "AddEventPage") or [],
            cursor=data.get("cursor", 0),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class ExplainResult:
    """One ranked hit from ``search_explain``. ``rank`` is **1-based** here —
    unlike ``MemoryTrace.retrievals``, where it is 0-based."""

    id: int
    text: str
    rank: int | None = None
    final_score: float | None = None
    source_agent_id: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: Any) -> ExplainResult:
        return cls(
            id=_require(data, "id", "ExplainResult"),
            text=_require(data, "text", "ExplainResult"),
            rank=data.get("rank"),
            final_score=data.get("final_score"),
            source_agent_id=data.get("source_agent_id"),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class SearchExplanation:
    """Ranked results plus the full score breakdown.

    ``trace`` stays a dict: it echoes retrieval internals (domain weights,
    scoring constants, per-candidate maths) that move with the ranker.
    ``rehearsed`` reports whether this call was a real, memory-strengthening
    search or a side-effect-free what-if.
    """

    results: list[ExplainResult] = field(default_factory=list)
    trace: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def rehearsed(self) -> bool | None:
        return self.trace.get("rehearsed")

    @property
    def candidates(self) -> list[dict]:
        """Every candidate considered, not just the returned head."""
        return self.trace.get("candidates") or []

    @classmethod
    def from_json(cls, data: Any) -> SearchExplanation:
        results = _require(data, "results", "SearchExplanation") or []
        return cls(
            results=[ExplainResult.from_json(r) for r in results],
            trace=data.get("trace") or {},
            raw=data,
        )
