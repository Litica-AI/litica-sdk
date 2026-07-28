"""Viz / explain endpoints, including the deliberate scope-inheritance exception."""

from __future__ import annotations

from helpers import build_client, ok

GRAPH = {
    "scope": {"agent_id": "bot", "namespace_id": None},
    "truncated": False,
    "nodes": [{"id": 1, "text": "a", "salience": 0.5, "is_gist": False}],
    "links": [{"source": 1, "target": 2}],
}

EXPLAIN = {
    "results": [
        {"id": 1, "text": "a", "source_agent_id": "bot", "rank": 1, "final_score": 0.9}
    ],
    "trace": {
        "query_rf": {"entities": ["Sam"]},
        "domain_weights": {"entities": 0.4},
        "constants": {"gist_vote_weight": 0.3},
        "pool_sizes": {"entities": 20},
        "candidates": [{"id": 1, "rank": 1, "final_score": 0.9}],
        "rehearsed": True,
    },
}


def test_viz_graph():
    client, rec = build_client(ok(GRAPH), agent_id="bot")
    graph = client.viz_graph(limit=50)
    assert rec.last.url.path == "/viz/graph"
    assert rec.param("limit") == "50"
    assert rec.param("agent_id") == "bot"
    assert graph.truncated is False
    assert graph.nodes[0]["id"] == 1
    assert graph.links[0]["source"] == 1
    assert graph.scope["agent_id"] == "bot"


def test_viz_pending_unwraps_the_count():
    client, rec = build_client(ok({"pending": 4}), agent_id="bot")
    assert client.viz_pending() == 4
    assert rec.last.url.path == "/viz/pending"
    assert rec.param("agent_id") == "bot"


def test_viz_add_events():
    client, rec = build_client(
        ok({"events": [{"id": 7, "action_id": 1, "agent_id": "bot"}], "cursor": 7})
    )
    page = client.viz_add_events(since_id=3, limit=10, order="desc")
    assert rec.last.url.path == "/viz/add-events"
    assert rec.param("since_id") == "3"
    assert rec.param("order") == "desc"
    assert page.cursor == 7
    assert page.events[0]["id"] == 7


def test_add_events_does_not_inherit_client_scope_defaults():
    """An audit feed must not be silently narrowed by connection defaults.

    Every other scoped method inherits agent_id/namespace_id from the client.
    This one deliberately does not: the route treats None as 'all scopes', and
    quietly filtering an audit trail to one agent is the opposite of its job.
    """
    client, rec = build_client(
        ok({"events": [], "cursor": 0}),
        agent_id="support-bot",
        namespace_id="team-shared",
    )
    client.viz_add_events()
    assert "agent_id" not in rec.param_names
    assert "namespace_id" not in rec.param_names


def test_add_events_filters_when_asked_explicitly():
    client, rec = build_client(ok({"events": [], "cursor": 0}), agent_id="support-bot")
    client.viz_add_events(agent_id="support-bot")
    assert rec.param("agent_id") == "support-bot"


def test_search_explain_posts_and_defaults_to_rehearsing():
    client, rec = build_client(ok(EXPLAIN), agent_id="bot")
    explanation = client.search_explain("who owns pricing?")
    assert rec.last.method == "POST"
    assert rec.last.url.path == "/viz/search-explain"
    assert rec.last_json["query"] == "who owns pricing?"
    assert rec.last_json["rehearse"] is True
    assert rec.last_json["agent_id"] == "bot"
    assert explanation.results[0].rank == 1  # 1-based here; 0-based in trace
    assert explanation.results[0].final_score == 0.9
    assert explanation.rehearsed is True
    assert explanation.trace["candidates"][0]["id"] == 1


def test_search_explain_what_if_mode():
    client, rec = build_client(ok(EXPLAIN))
    client.search_explain("q", rehearse=False, query_rf={"entities": ["Sam"]})
    assert rec.last_json["rehearse"] is False
    assert rec.last_json["query_rf"] == {"entities": ["Sam"]}


def test_search_explain_omits_unset_optionals():
    client, rec = build_client(ok(EXPLAIN))
    client.search_explain("q")
    assert "query_rf" not in rec.last_json
    assert "session_id" not in rec.last_json


def test_search_explain_inherits_namespace_default():
    client, rec = build_client(ok(EXPLAIN), namespace_id="team-shared")
    client.search_explain("q")
    assert rec.last_json["namespace_id"] == "team-shared"
