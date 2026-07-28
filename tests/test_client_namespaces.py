"""Namespace management — the six routes, and the errors the server owns."""

from __future__ import annotations

import pytest
from helpers import build_client, ok

import litica

NS = {
    "namespace_id": "11111111-1111-1111-1111-111111111111",
    "name": "team-shared",
    "read_policy": "grant",
    "write_policy": "grant",
    "created_at": "2026-07-26T10:00:00+00:00",
    "agents": [{"agent_id": "bot", "can_read": True, "can_write": True}],
}


def test_list_namespaces_unwraps_the_envelope():
    client, rec = build_client(ok({"namespaces": [NS]}))
    result = client.list_namespaces()
    assert rec.last.url.path == "/namespaces"
    assert len(result) == 1
    assert result[0].name == "team-shared"
    assert result[0].agents[0]["agent_id"] == "bot"


def test_create_namespace_defaults_to_grant_policies():
    client, rec = build_client(ok(NS, status=201))
    result = client.create_namespace("team-shared")
    assert rec.last.method == "POST"
    assert rec.last_json == {
        "name": "team-shared",
        "read_policy": "grant",
        "write_policy": "grant",
        "agents": [],
    }
    assert result.namespace_id == NS["namespace_id"]


def test_create_namespace_with_agents_and_open_policy():
    client, rec = build_client(ok(NS, status=201))
    client.create_namespace(
        "team-shared", read_policy="open", write_policy="open", agents=["a", "b"]
    )
    assert rec.last_json["read_policy"] == "open"
    assert rec.last_json["agents"] == ["a", "b"]


def test_agent_cap_is_the_server_rule_not_ours():
    """A 422 from the server surfaces as-is — the SDK does not duplicate the cap."""
    client, _ = build_client(
        ok({"detail": "A namespace may have at most 5 agents"}, status=422)
    )
    with pytest.raises(litica.LiticaValidationError) as caught:
        client.create_namespace("x", agents=["a", "b", "c", "d", "e", "f"])
    assert "at most 5" in caught.value.detail


def test_duplicate_name_is_a_conflict():
    client, _ = build_client(
        ok({"detail": "Namespace name already exists"}, status=409)
    )
    with pytest.raises(litica.LiticaConflictError):
        client.create_namespace("team-shared")


def test_bad_uuid_is_a_server_side_422():
    client, _ = build_client(ok({"detail": "Invalid namespace_id"}, status=422))
    with pytest.raises(litica.LiticaValidationError):
        client.list_namespace_agents("not-a-uuid")


def test_list_namespace_agents():
    client, rec = build_client(
        ok({"agents": [{"agent_id": "bot", "can_read": True, "can_write": False}]})
    )
    agents = client.list_namespace_agents(NS["namespace_id"])
    assert rec.last.url.path == f"/namespaces/{NS['namespace_id']}/agents"
    assert agents[0].agent_id == "bot"
    assert agents[0].can_write is False


def test_grant_namespace_agent():
    client, rec = build_client(
        ok(
            {
                "namespace_id": NS["namespace_id"],
                "agent_id": "bot",
                "can_read": True,
                "can_write": True,
            }
        )
    )
    result = client.grant_namespace_agent(NS["namespace_id"], "bot")
    assert rec.last.method == "POST"
    assert rec.last.url.path == f"/namespaces/{NS['namespace_id']}/agents"
    assert rec.last_json == {"agent_id": "bot", "can_read": True, "can_write": True}
    assert result.can_read is True


def test_grant_namespace_agent_read_only():
    client, rec = build_client(
        ok(
            {
                "namespace_id": NS["namespace_id"],
                "agent_id": "bot",
                "can_read": True,
                "can_write": False,
            }
        )
    )
    client.grant_namespace_agent(NS["namespace_id"], "bot", can_write=False)
    assert rec.last_json["can_write"] is False


def test_remove_namespace_agent():
    client, rec = build_client(ok({"removed": "bot"}))
    assert client.remove_namespace_agent(NS["namespace_id"], "bot") == "bot"
    assert rec.last.method == "DELETE"
    assert rec.last.url.path == f"/namespaces/{NS['namespace_id']}/agents/bot"


def test_delete_namespace():
    client, rec = build_client(ok({"deleted": NS["namespace_id"]}))
    assert client.delete_namespace(NS["namespace_id"]) == NS["namespace_id"]
    assert rec.last.method == "DELETE"
    assert rec.last.url.path == f"/namespaces/{NS['namespace_id']}"


def test_unknown_namespace_is_not_found():
    client, _ = build_client(ok({"detail": "Namespace not found"}, status=404))
    with pytest.raises(litica.LiticaNotFoundError):
        client.delete_namespace(NS["namespace_id"])


def test_namespace_methods_do_not_inherit_the_client_namespace_default():
    """create/list/delete take an explicit id — the client default is irrelevant
    and must not leak into the path or body."""
    client, rec = build_client(ok(NS, status=201), namespace_id="some-other-ns")
    client.create_namespace("team-shared")
    assert "namespace_id" not in rec.last_json
