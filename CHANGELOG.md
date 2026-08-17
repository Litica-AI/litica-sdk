# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/). While
the version is `0.x` the public surface may still change between minor
versions; anything breaking is called out explicitly.

## [Unreleased]

### Fixed

- **`except litica.LiticaError` is a complete catch again.** Eleven routes
  answer with a one-key envelope (`delete_memory`, `clear_memories`,
  `list_agents`, `get_tenant`, `list_namespaces`, `delete_namespace`,
  `list_namespace_agents`, `remove_namespace_agent`, `list_keys`,
  `revoke_key`, `viz_pending`) and read that key straight off the decoded
  body. A missing key raised a bare `KeyError`, and a `204`/empty body — which
  the transport decodes to `None` — raised `TypeError: 'NoneType' object is
  not subscriptable`. Neither inherits from `LiticaError`, so the catch-all
  the README and `litica.errors` both document silently failed to catch them.
  These envelopes now go through the same `_require` the models use, so a
  broken body raises `LiticaResponseError` naming the route, the missing key,
  and the keys actually received.
- `health()` no longer raises on a malformed body. It promises a `bool` for an
  unreachable *or* misbehaving server, but a non-empty JSON array reached
  `.get` and raised `AttributeError`; anything that is not a
  `{"status": "ok"}` object now reads as unhealthy.

### Documentation

- `QueuedWrite` and `LiticaTimeout` no longer refer to a `wait=` parameter.
  There has never been one — `Client.add_memory` and the README both say so
  explicitly and point at a polling loop instead.

## [0.2.0] — 2026-08-04

### Added

- `litica.AsyncClient` — the async twin of `Client`: the same methods with
  identical signatures, awaitable, over `httpx.AsyncClient`. Use it inside
  `asyncio` services; `Client` remains the right choice everywhere else.
- API-key self-service on both clients: `mint_key`, `list_keys`, `revoke_key`
  (`POST /keys`, `GET /keys`, `DELETE /keys/{key_id}`), with `MintedKey` and
  `ApiKey` models. The minted plaintext is returned once, is never
  recoverable afterwards, and is excluded from `repr` so logging the object
  cannot leak it.
- `viz_config` on both clients (`GET /viz/config`), with a `VizConfig` model —
  the public, unauthenticated bootstrap for playground-style clients. A
  present `clerk_publishable_key` means the deployment offers Clerk sign-in;
  the response never carries a secret.

### Changed

- Internal only: request building and response parsing moved into a shared
  private module (`litica._ops`) used by both clients, so the sync and async
  surfaces cannot drift. No public behaviour changed; the sync client's
  signatures, docstrings, and wire format are unchanged.

### Known limitations

- **Still no retries.** Transient failures surface as exceptions; wrap calls
  in your own retry policy if you need one.
- **Tenant provisioning is absent by design, not omission.** Tenants are
  created through the Litica account flow (one per account), and a tenant's
  first API key is minted in the Playground while signed in. From there, key
  self-service (`mint_key`, `list_keys`, `revoke_key`) is the supported
  surface.
- The `rank` inconsistency noted in 0.1.0 (0-based in `get_memory_trace`,
  1-based in `search_explain`) is unchanged and still mirrored as sent.

## [0.1.0] — 2026-08-01

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

[Unreleased]: https://github.com/Litica-AI/litica-sdk/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Litica-AI/litica-sdk/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Litica-AI/litica-sdk/releases/tag/v0.1.0
