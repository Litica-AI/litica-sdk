# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/). While
the version is `0.x` the public surface may still change between minor
versions; anything breaking is called out explicitly.

## [Unreleased]

## [0.1.0] — unreleased

First release.

### Added

- `litica.Client` — a synchronous client covering 22 API routes, one method per
  route. `LiticaClient` is available as a deprecated alias.
- **Memories:** `add_memory`, `add_memories_batch`, `add_document`,
  `search_memories`, `list_memories`, `get_memory_trace`, `delete_memory`,
  `clear_memories`, `list_queries`, `list_agents`, `get_tenant`, `health`.
- **Namespaces:** `list_namespaces`, `create_namespace`, `delete_namespace`,
  `list_namespace_agents`, `grant_namespace_agent`, `remove_namespace_agent`.
- **Inspection:** `viz_graph`, `viz_add_events`, `viz_pending`, `search_explain`.
- Connection-level `agent_id` and `namespace_id`, overridable per call. Passing
  `namespace_id=None` explicitly means agent-private scope.
- Configuration from arguments, then environment (`LITICA_API_KEY`,
  `LITICA_BASE_URL`, `LITICA_AGENT_ID`, `LITICA_NAMESPACE_ID`), then defaults.
- Frozen dataclass responses with tolerant parsing — unknown fields are kept on
  `.raw` rather than raising.
- An exception hierarchy rooted at `LiticaError`, carrying `.status_code`,
  the server's `.detail` verbatim, and `.response`.
- `py.typed` — the package ships its type information (PEP 561).

### Known limitations

- **No read-your-writes helper.** Writes are accepted asynchronously (HTTP 202)
  and are not immediately searchable. The service exposes no signal that
  reliably reports when a specific write has landed, so the README documents
  polling instead of shipping a convenience that can return too early.
- **No provenance on writes.** The API route this client wraps does not accept
  provenance, so memories written through the SDK carry no source attribution.
- **`rank` is inconsistent across routes** — 0-based in `get_memory_trace`,
  1-based in `search_explain`. Both are mirrored as the server sends them
  rather than quietly renumbered.
- **No async client, no retries, no tenant provisioning.** Out of scope for this
  release.

[Unreleased]: https://github.com/Litica-AI/litica-sdk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Litica-AI/litica-sdk/releases/tag/v0.1.0
