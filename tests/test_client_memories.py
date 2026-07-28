"""Memories, queries, agents, tenant — verb, path, params, body, and parsing."""

from __future__ import annotations

import dataclasses
import json as jsonlib

import httpx
import pytest
from helpers import build_client, ok

import litica

SEARCH_ROW = {
    "id": 12,
    "text": "Sam owns the Atlas pricing page.",
    "created_at": "2026-07-26T10:00:00+00:00",
    "source_agent_id": "support-bot",
}


# --------------------------------------------------------------------------
# search_memories
# --------------------------------------------------------------------------


def test_search_hits_the_route():
    client, rec = build_client(ok([SEARCH_ROW]))
    client.search_memories("who owns pricing?")
    assert rec.last.method == "GET"
    assert rec.last.url.path == "/memories/search"
    assert rec.param("query") == "who owns pricing?"
    assert rec.param("top_k") == "5"


def test_search_returns_a_bare_array_not_an_envelope():
    """The route returns a bare JSON array — the SDK must not invent a wrapper."""
    client, _ = build_client(ok([SEARCH_ROW, {"id": 2, "text": "b"}]))
    results = client.search_memories("q")
    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0].id == 12
    assert results[0].text == "Sam owns the Atlas pricing page."
    assert results[0].source_agent_id == "support-bot"


def test_search_empty_result():
    client, _ = build_client(ok([]))
    assert client.search_memories("q") == []


def test_search_passes_top_k_and_session_id():
    client, rec = build_client(ok([]))
    client.search_memories("q", top_k=25, session_id="sess-1")
    assert rec.param("top_k") == "25"
    assert rec.param("session_id") == "sess-1"


def test_omitted_optional_params_are_not_sent():
    """None must be dropped, never sent as an empty string."""
    client, rec = build_client(ok([]))
    client.search_memories("q")
    assert "session_id" not in rec.param_names
    assert "namespace_id" not in rec.param_names


# --------------------------------------------------------------------------
# Client-level defaults
# --------------------------------------------------------------------------


def test_agent_id_default_is_applied():
    client, rec = build_client(ok([]), agent_id="support-bot")
    client.search_memories("q")
    assert rec.param("agent_id") == "support-bot"


def test_namespace_id_default_is_applied():
    client, rec = build_client(ok([]), namespace_id="team-shared")
    client.search_memories("q")
    assert rec.param("namespace_id") == "team-shared"


def test_per_call_override_beats_the_client_default():
    client, rec = build_client(ok([]), agent_id="support-bot")
    client.search_memories("q", agent_id="research-bot")
    assert rec.param("agent_id") == "research-bot"


def test_explicit_none_namespace_overrides_the_client_default():
    """Explicit namespace_id=None means agent-scoped and must beat the default.

    The namespace-scoping invariant makes NULL a real scope, not an absence,
    so the sentinel for 'not specified' cannot be None.
    """
    client, rec = build_client(ok([]), namespace_id="team-shared")
    client.search_memories("q", namespace_id=None)
    assert "namespace_id" not in rec.param_names


def test_defaults_read_from_environment(monkeypatch):
    monkeypatch.setenv("LITICA_AGENT_ID", "env-bot")
    monkeypatch.setenv("LITICA_NAMESPACE_ID", "env-ns")
    monkeypatch.setenv("LITICA_API_KEY", "lk_x")
    client = litica.Client(transport=httpx.MockTransport(lambda r: ok({})))
    assert client.agent_id == "env-bot"
    assert client.namespace_id == "env-ns"


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


def test_add_memory_posts_the_body():
    client, rec = build_client(ok({"queued": True}, status=202), agent_id="bot")
    result = client.add_memory("Sam owns pricing.")
    assert rec.last.method == "POST"
    assert rec.last.url.path == "/memories"
    assert rec.last_json == {"content": "Sam owns pricing.", "agent_id": "bot"}
    assert result.queued is True


def test_add_memory_omits_null_body_fields():
    client, rec = build_client(ok({"queued": True}, status=202))
    client.add_memory("x")
    assert "namespace_id" not in rec.last_json
    assert "session_id" not in rec.last_json


def test_add_memory_includes_scope_when_set():
    client, rec = build_client(ok({"queued": True}, status=202), namespace_id="ns-1")
    client.add_memory("x", session_id="s-1")
    assert rec.last_json["namespace_id"] == "ns-1"
    assert rec.last_json["session_id"] == "s-1"


def test_add_memory_issues_exactly_one_request():
    """No hidden round trips — a write is a write."""
    client, rec = build_client(ok({"queued": True}, status=202))
    client.add_memory("x")
    assert len(rec.requests) == 1


def test_add_memories_batch():
    client, rec = build_client(ok({"queued": 3}, status=202))
    result = client.add_memories_batch(["a", "b", "c"])
    assert rec.last.url.path == "/memories/batch"
    assert rec.last_json["contents"] == ["a", "b", "c"]
    assert result.queued == 3


def test_add_memories_batch_rejects_empty_locally():
    """The route requires min_length=1; failing before the round trip is kinder."""
    client, rec = build_client(ok({"queued": 0}, status=202))
    with pytest.raises(litica.LiticaValidationError):
        client.add_memories_batch([])
    assert not rec.requests


def test_add_document_sends_multipart(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("Sam owns pricing.")
    client, rec = build_client(
        ok({"queued": True, "filename": "notes.txt", "chars": 17}, status=202),
        agent_id="bot",
    )
    result = client.add_document(doc)
    assert rec.last.url.path == "/documents"
    body = rec.last.content
    assert b"notes.txt" in body
    assert b"Sam owns pricing." in body
    assert b"bot" in body
    assert result.filename == "notes.txt"
    assert result.chars == 17


def test_add_document_missing_file_raises_before_the_request(tmp_path):
    client, rec = build_client(ok({}, status=202))
    with pytest.raises(FileNotFoundError):
        client.add_document(tmp_path / "nope.pdf")
    assert not rec.requests


# --------------------------------------------------------------------------
# Reads and deletes
# --------------------------------------------------------------------------


def test_list_memories():
    client, rec = build_client(
        ok([{"id": 1, "text": "a", "created_at": None}]),
    )
    rows = client.list_memories(top_k=3, include_archived=True)
    assert rec.last.url.path == "/memories"
    assert rec.param("top_k") == "3"
    assert rec.param("include_archived") == "true"
    assert rows[0].id == 1
    assert rows[0].created_at is None


def test_get_memory_trace():
    payload = {
        "id": 5,
        "text": "Sam owns pricing.",
        "agent_id": "bot",
        "namespace_id": None,
        "field": "work",
        "reference_frame": {"entities": ["Sam"]},
        "created_at": "2026-07-26T10:00:00+00:00",
        "retrieval_count": 2,
        "salience": 0.7,
        "last_retrieved_at": None,
        "retrievals": [{"query_log_id": 1, "rank": 0, "final_score": 0.9}],
        "linked_memories": [{"id": 6, "text": "b"}],
    }
    client, rec = build_client(ok(payload))
    trace = client.get_memory_trace(5)
    assert rec.last.url.path == "/memories/5/trace"
    assert trace.id == 5
    assert trace.retrieval_count == 2
    assert trace.retrievals[0]["rank"] == 0  # 0-based here; 1-based in explain
    assert trace.linked_memories[0]["id"] == 6


def test_delete_memory_returns_the_id():
    client, rec = build_client(ok({"deleted": 9}))
    assert client.delete_memory(9) == 9
    assert rec.last.method == "DELETE"
    assert rec.last.url.path == "/memories/9"


def test_clear_memories_returns_the_count():
    client, rec = build_client(ok({"cleared": 12}), agent_id="bot")
    assert client.clear_memories() == 12
    assert rec.last.method == "DELETE"
    assert rec.last.url.path == "/memories"
    assert rec.param("agent_id") == "bot"


def test_list_queries():
    client, rec = build_client(
        ok(
            [
                {
                    "id": 1,
                    "agent_id": "bot",
                    "namespace_id": None,
                    "query_text": "q",
                    "top_k": 5,
                    "result_count": 2,
                    "created_at": None,
                }
            ]
        )
    )
    rows = client.list_queries(limit=10)
    assert rec.param("limit") == "10"
    assert rows[0].query_text == "q"


def test_list_agents_unwraps_the_envelope():
    client, rec = build_client(ok({"agents": ["bot", "other"]}))
    assert client.list_agents() == ["bot", "other"]
    assert rec.last.url.path == "/agents"


def test_get_tenant_unwraps_the_envelope():
    client, _ = build_client(ok({"tenant_id": "acme"}))
    assert client.get_tenant() == "acme"


def test_health_is_true_when_ok():
    client, rec = build_client(ok({"status": "ok"}))
    assert client.health() is True
    assert rec.last.url.path == "/health"


def test_health_is_false_when_the_server_is_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    client, _ = build_client(handler)
    assert client.health() is False


# --------------------------------------------------------------------------
# Tolerant parsing
# --------------------------------------------------------------------------


def test_unknown_fields_are_kept_in_raw_not_rejected():
    row = {**SEARCH_ROW, "brand_new_field": "surprise"}
    client, _ = build_client(ok([row]))
    result = client.search_memories("q")[0]
    assert result.raw["brand_new_field"] == "surprise"
    assert result.id == 12


def test_missing_enrichment_field_defaults_to_none():
    client, _ = build_client(ok([{"id": 1, "text": "a"}]))
    result = client.search_memories("q")[0]
    assert result.created_at is None
    assert result.source_agent_id is None


def test_missing_identity_field_raises():
    client, _ = build_client(ok([{"text": "no id here"}]))
    with pytest.raises(litica.LiticaResponseError):
        client.search_memories("q")


def test_non_json_success_body_raises_response_error():
    client, _ = build_client(httpx.Response(200, text="not json"))
    with pytest.raises(litica.LiticaResponseError):
        client.get_tenant()


def test_raw_holds_the_untouched_body():
    client, _ = build_client(ok([SEARCH_ROW]))
    result = client.search_memories("q")[0]
    assert result.raw == SEARCH_ROW


def test_models_are_frozen():
    client, _ = build_client(ok([SEARCH_ROW]))
    result = client.search_memories("q")[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.id = 99


def test_json_content_type_on_writes():
    client, rec = build_client(ok({"queued": True}, status=202))
    client.add_memory("x")
    assert rec.last.headers["Content-Type"] == "application/json"
    jsonlib.loads(rec.last.content)
