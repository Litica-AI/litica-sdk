"""Contract tests against a live Litica deployment.

Scope is deliberately thin. These prove *this client talks correctly to the
real service* — that requests serialize, auth works, and responses parse. They
do not judge retrieval quality; that belongs to the engine's own evals.

Skipped unless ``LITICA_TEST_API_KEY`` is set, so they are inert locally and
for outside contributors. In CI they run on a schedule and before a release,
never on a pull request.

Every test tags its data with a unique run id and cleans up after itself. The
key must belong to the dedicated SDK test tenant, never a customer tenant.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

import litica

API_KEY = os.environ.get("LITICA_TEST_API_KEY")
BASE_URL = os.environ.get("LITICA_TEST_BASE_URL", "https://mcp.litica.org")

pytestmark = pytest.mark.skipif(
    not API_KEY, reason="LITICA_TEST_API_KEY not set — live contract tests skipped"
)

# Writes are fast-ack: accepted long before they are searchable. Poll, do not
# sleep-and-hope. Mirrors deploy/smoke_test.py's proven approach.
POLL_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 3


def wait_until_searchable(
    client, query: str, token: str, *, timeout=POLL_TIMEOUT_SECONDS
):
    """Search until a planted token appears. Returns the hits, or fails.

    The token is a random string embedded in the written text, so a match is
    unambiguous — no guessing whether some pre-existing memory satisfied the
    query.
    """
    deadline = time.monotonic() + timeout
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        hits = client.search_memories(query, top_k=10)
        if any(token in hit.text for hit in hits):
            return hits
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(
        f"planted token {token!r} not retrievable within {timeout}s "
        f"({attempts} polls) — the add→encode→persist pipeline may be stuck"
    )


@pytest.fixture(scope="module")
def run_id() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture
def client(run_id):
    """A client on a throwaway agent, cleaned out afterwards."""
    agent_id = f"sdk_contract_{run_id}_{uuid.uuid4().hex[:6]}"
    c = litica.Client(api_key=API_KEY, base_url=BASE_URL, agent_id=agent_id, timeout=60)
    try:
        yield c
    finally:
        try:
            c.clear_memories()
        finally:
            c.close()


# --------------------------------------------------------------------------
# Reachability
# --------------------------------------------------------------------------


def test_health(client):
    assert client.health() is True


def test_get_tenant(client):
    assert isinstance(client.get_tenant(), str)


def test_bad_key_is_rejected():
    with litica.Client(api_key="lk_definitely_not_valid", base_url=BASE_URL) as bad:
        with pytest.raises(litica.LiticaAuthError) as caught:
            bad.get_tenant()
    assert caught.value.status_code == 401


def test_unknown_memory_is_not_found(client):
    with pytest.raises(litica.LiticaNotFoundError) as caught:
        client.delete_memory(2_000_000_000)
    assert caught.value.status_code == 404
    assert caught.value.detail


# --------------------------------------------------------------------------
# The quickstart, against production
# --------------------------------------------------------------------------


def test_write_then_search_round_trip(client, run_id):
    """The exact promise the README makes."""
    token = f"zt{uuid.uuid4().hex[:8]}"
    client.add_memory(f"Sam owns the Atlas pricing page. Ref {token}.")
    hits = wait_until_searchable(client, "who owns pricing?", token)
    assert any(isinstance(h.id, int) for h in hits)


def test_list_and_delete(client):
    token = f"zt{uuid.uuid4().hex[:8]}"
    client.add_memory(f"Billing note {token}.")
    wait_until_searchable(client, "billing note", token)

    rows = client.list_memories(top_k=20)
    assert rows
    target = rows[0]
    assert client.delete_memory(target.id) == target.id
    assert target.id not in {r.id for r in client.list_memories(top_k=20)}


def test_batch_write(client):
    token = f"zt{uuid.uuid4().hex[:8]}"
    result = client.add_memories_batch(
        [f"Atlas ships on Tuesday. Ref {token}.", f"Launch is in March. Ref {token}."]
    )
    assert result.queued == 2
    wait_until_searchable(client, "when does Atlas ship?", token)


def test_document_upload(client, tmp_path):
    token = f"zt{uuid.uuid4().hex[:8]}"
    doc = tmp_path / "handbook.txt"
    doc.write_text(
        f"The Atlas team meets on Mondays. Priya is the engineering lead. "
        f"Reference code {token}."
    )
    result = client.add_document(doc)
    assert result.queued is True
    assert result.filename == "handbook.txt"
    assert result.chars > 0
    wait_until_searchable(client, "who is the engineering lead?", token)


def test_trace_and_explain(client):
    token = f"zt{uuid.uuid4().hex[:8]}"
    client.add_memory(f"Sam owns the Atlas pricing page. Ref {token}.")
    hits = wait_until_searchable(client, "who owns pricing?", token)

    trace = client.get_memory_trace(hits[0].id)
    assert trace.id == hits[0].id
    assert isinstance(trace.reference_frame, dict)

    explanation = client.search_explain("who owns pricing?", top_k=3)
    assert explanation.results
    assert explanation.results[0].rank == 1  # 1-based here, 0-based in trace
    assert explanation.rehearsed is True


def test_viz_graph(client):
    token = f"zt{uuid.uuid4().hex[:8]}"
    client.add_memory(f"Sam owns the Atlas pricing page. Ref {token}.")
    wait_until_searchable(client, "who owns pricing?", token)

    graph = client.viz_graph(limit=50)
    assert graph.nodes
    assert graph.scope["agent_id"] == client.agent_id


# --------------------------------------------------------------------------
# Namespaces
# --------------------------------------------------------------------------


def test_namespace_round_trip(run_id):
    """Create, grant, write as one agent, read as another, revoke, verify denial."""
    writer_id = f"sdk_w_{run_id}_{uuid.uuid4().hex[:5]}"
    reader_id = f"sdk_r_{run_id}_{uuid.uuid4().hex[:5]}"
    admin = litica.Client(api_key=API_KEY, base_url=BASE_URL, timeout=60)
    namespace = admin.create_namespace(
        f"sdk_contract_{run_id}_{uuid.uuid4().hex[:5]}", agents=[writer_id, reader_id]
    )
    ns_id = namespace.namespace_id

    writer = reader = None
    try:
        assert {writer_id, reader_id} <= {
            a.agent_id for a in admin.list_namespace_agents(ns_id)
        }

        writer = litica.Client(
            api_key=API_KEY,
            base_url=BASE_URL,
            agent_id=writer_id,
            namespace_id=ns_id,
            timeout=60,
        )
        reader = litica.Client(
            api_key=API_KEY,
            base_url=BASE_URL,
            agent_id=reader_id,
            namespace_id=ns_id,
            timeout=60,
        )

        token = f"zt{uuid.uuid4().hex[:8]}"
        writer.add_memory(f"Sam owns the Atlas pricing page. Ref {token}.")

        # Visible to a *different* agent only because the namespace is shared.
        wait_until_searchable(reader, "who owns pricing?", token)

        # ...and invisible in that same agent's private scope.
        private = reader.search_memories(
            "who owns pricing?", top_k=10, namespace_id=None
        )
        assert not any(token in h.text for h in private), (
            "namespace-scoped memory leaked into agent-private scope"
        )

        assert admin.remove_namespace_agent(ns_id, reader_id) == reader_id
        with pytest.raises(litica.LiticaError) as caught:
            reader.search_memories("who owns pricing?")
        assert caught.value.status_code in (403, 404, 422)
    finally:
        if writer is not None:
            writer.clear_memories()
            writer.close()
        if reader is not None:
            reader.close()
        admin.delete_namespace(ns_id)
        admin.close()


def test_duplicate_namespace_name_conflicts(run_id):
    client = litica.Client(api_key=API_KEY, base_url=BASE_URL, timeout=60)
    name = f"sdk_dupe_{run_id}_{uuid.uuid4().hex[:5]}"
    ns = client.create_namespace(name)
    try:
        with pytest.raises(litica.LiticaConflictError):
            client.create_namespace(name)
    finally:
        client.delete_namespace(ns.namespace_id)
        client.close()
