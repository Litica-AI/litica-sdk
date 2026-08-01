# litica

Python client for [Litica](https://litica.org) — shared human memory for AI agents.

A thin, synchronous wrapper over the Litica HTTP API. Each method is one route in the API.

An API key is required to use this SDK. Sign up here -> https://mcp.litica.org/playground/

```bash
pip install litica
```

Requires Python 3.10+. The only dependency is `httpx`.

## Quickstart

```python
import time
import litica

client = litica.Client(api_key="lk_...")

client.add_memory("Sam owns the Atlas pricing page.")

# Writes are queued, so poll until it shows up (see below).
for _ in range(20):
    hits = client.search_memories("who owns pricing?")
    if hits:
        break
    time.sleep(3)

for hit in hits:
    print(hit.id, hit.text)
```

The conventional shorthand is `lit`, which is why the class is `Client` rather
than `LiticaClient`:

```python
import litica as lit

client = lit.Client(api_key="lk_...")
```

## Configuration

Precedence is **argument → environment variable → default**.

| Argument | Environment variable | Default |
|---|---|---|
| `api_key` | `LITICA_API_KEY` | *required* |
| `base_url` | `LITICA_BASE_URL` | `https://mcp.litica.org` |
| `agent_id` | `LITICA_AGENT_ID` | `"default"` |
| `namespace_id` | `LITICA_NAMESPACE_ID` | `None` |

### Scope

`agent_id` and `namespace_id` are connection-level defaults applied to every
call that takes them. Any call can override them.

```python
client = litica.Client(
    api_key="lk_...",
    agent_id="support-bot",
    namespace_id="team-shared",
)

client.search_memories("who owns pricing?")                # support-bot / team-shared
client.search_memories("...", agent_id="research-bot")     # override for one call
client.search_memories("...", namespace_id=None)           # this agent's private memories
```

Passing `namespace_id=None` **explicitly** means agent-private scope and
overrides the client default — a namespace of `NULL` is a real scope in Litica,
not an absence.

## Writes are queued, not instant

Due to the nature of human-inspired memory, there is a short-term memory queue that has a wait time for ingestion.

`add_memory` returns as soon as the server **accepts** the write (HTTP 202).
However, the memory is not searchable yet. It takes time for Litica to decompose, embed, and store it. 
A naive write-then-read will not produce expected behavior:

```python
client.add_memory("Sam owns pricing.")
client.search_memories("pricing")   # probably []
```

There is no `wait=` flag at the moment. 
So poll for what you actually care about:

```python
import time

def wait_for(client, query, needle, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hits = client.search_memories(query, top_k=10)
        if any(needle in h.text for h in hits):
            return hits
        time.sleep(3)
    raise TimeoutError(f"{needle!r} never became searchable")

client.add_memory("Sam owns the Atlas pricing page.")
hits = wait_for(client, "who owns pricing?", "Sam")
```

Two practical notes:

- **Documents take longest.** One upload fans out into many memories, so allow
  a generous timeout after `add_document`.
- **Searching is not free of side effects.** Each search strengthens the
  memories it returns and is recorded in your query log. That is by design.

## Errors

Every exception inherits from `litica.LiticaError` and carries `.status_code`,
`.detail` (the server's message, verbatim), and `.response`.

```python
try:
    client.add_memory("...")
except litica.LiticaRateLimitError as e:
    time.sleep(e.retry_after or 60)
except litica.LiticaError as e:
    print(e.status_code, e.detail)
```

`LiticaAuthError` (401) · `LiticaNotFoundError` (404) · `LiticaConflictError`
(409) · `LiticaUnsupportedMediaError` (415) · `LiticaValidationError` (422) ·
`LiticaRateLimitError` (429) · `LiticaServerError` (5xx) · `LiticaAPIError`
(anything else) · `LiticaTimeout` · `LiticaConnectionError` ·
`LiticaResponseError` · `LiticaConfigError`

## What you can call

### Memories

```python
client.add_memory(content, *, agent_id, namespace_id, session_id)
client.add_memories_batch(contents, *, ...)         # several at once
client.add_document("report.pdf", *, ...)           # PDF / DOCX / PPTX / text
client.search_memories(query, *, top_k, ...)
client.list_memories(*, top_k, include_archived, ...)
client.get_memory_trace(memory_id)                  # why this memory surfaced
client.delete_memory(memory_id)
client.clear_memories(*, agent_id)                  # no undo
client.list_queries(limit)
client.list_agents()
client.get_tenant()
client.health()
```

### Namespaces (shared memory between agents)

```python
ns = client.create_namespace("team-shared", agents=["support-bot"])
client.grant_namespace_agent(ns.namespace_id, "research-bot", can_write=False)
client.list_namespace_agents(ns.namespace_id)
client.remove_namespace_agent(ns.namespace_id, "research-bot")
client.list_namespaces()
client.delete_namespace(ns.namespace_id)
```

### Inspection

```python
client.viz_graph(limit=300)                # memories and their links
client.viz_add_events(since_id=0)          # write-side audit feed
client.viz_pending()                       # queue depth
client.search_explain("who owns pricing?") # search, with the score breakdown
```

> **`search_explain` is a real search by default.** With `rehearse=True` it
> strengthens the memories it returns and logs the query, exactly like
> `search_memories`. Poking at rankings in a loop will move the rankings you are
> poking at. Pass `rehearse=False` for a side-effect-free what-if.

## Responses

Frozen dataclasses mirroring the JSON as the server sends it. Unknown fields
never break parsing. Every model keeps the untouched body on `.raw`:

```python
hit = client.search_memories("pricing")[0]
hit.id, hit.text, hit.created_at, hit.source_agent_id
hit.raw          # everything the server sent
```

Timestamps stay ISO-8601 strings rather than `datetime` objects, because the
server sends `null` for rows that have none.

## Known gaps

- **No provenance on writes.** The MCP tools let you record where a fact came
  from; the HTTP route this SDK wraps does not accept it yet, so memories
  written through the SDK carry no source attribution. Tracked as a follow-up.
- **`rank` is inconsistent across routes** — 0-based in `get_memory_trace`,
  1-based in `search_explain`. Both are mirrored as the server sends them
  rather than quietly renumbered.
- **No read-your-writes signal.** See "Writes are queued" above — you poll.
- **No async client, no retries.** Deliberately out of scope for this version.
- **No tenant provisioning.** That route uses a separate admin credential and
  is intentionally absent from this client.

## Contributing

Bug reports, typing improvements, and documentation fixes are welcome. New
endpoints are not — this client mirrors the API one-to-one, so a method cannot
exist before the route does. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
full picture, and [SECURITY.md](SECURITY.md) to report a vulnerability
privately.

## License

[Apache License 2.0](LICENSE). © 2026 Litica, Inc.

This licence covers **this client library only**. It grants no right to access
or use the Litica service, which is a separate proprietary hosted service with
its own terms; an API key is issued separately. See [NOTICE](NOTICE).
