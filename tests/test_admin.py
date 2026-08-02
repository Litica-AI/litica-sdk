"""AdminClient: the separate provisioning surface behind a separate credential.

The security property under test is separation, not just correctness: the
admin credential travels in ``X-Admin-Key`` (never ``X-API-Key``), ordinary
clients cannot reach ``provision``, and the admin client exposes nothing but
provisioning.
"""

from __future__ import annotations

import httpx
import pytest
from helpers import Recorder, ok

import litica


def build_admin(responses, **kwargs) -> tuple[litica.AdminClient, Recorder]:
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return responses(request) if callable(responses) else responses

    kwargs.setdefault("admin_key", "admin_test_secret")
    kwargs.setdefault("base_url", "https://api.test")
    client = litica.AdminClient(transport=httpx.MockTransport(handler), **kwargs)
    return client, recorder


def test_provision_posts_tenant_and_label_with_the_admin_header():
    client, rec = build_admin(ok({"api_key": "lk_first_key"}, status=201))
    result = client.provision(tenant_id="acme", label="production")
    assert rec.last.method == "POST"
    assert rec.last.url.path == "/provision"
    assert rec.last_json == {"tenant_id": "acme", "label": "production"}
    assert rec.last.headers["X-Admin-Key"] == "admin_test_secret"
    assert "X-API-Key" not in rec.last.headers
    assert result.api_key == "lk_first_key"


def test_omitted_label_leaves_the_server_default_authoritative():
    """No label sent when unset — the SDK does not copy the server's default,
    so the two can never drift (PR review nit)."""
    client, rec = build_admin(ok({"api_key": "lk_x"}, status=201))
    client.provision(tenant_id="acme")
    assert rec.last_json == {"tenant_id": "acme"}


def test_dead_can_read_can_write_fields_are_never_sent():
    """The route accepts can_read/can_write and ignores them; the SDK does
    not expose parameters that do nothing."""
    client, rec = build_admin(ok({"api_key": "lk_x"}, status=201))
    client.provision(tenant_id="acme", label="ops")
    assert set(rec.last_json) == {"tenant_id", "label"}


def test_wrong_admin_key_maps_to_auth_error():
    client, _ = build_admin(ok({"detail": "invalid admin key"}, status=401))
    with pytest.raises(litica.LiticaAuthError) as caught:
        client.provision(tenant_id="acme")
    assert caught.value.status_code == 401
    assert caught.value.detail == "invalid admin key"


def test_missing_admin_key_is_a_config_error(monkeypatch):
    monkeypatch.delenv("LITICA_ADMIN_KEY", raising=False)
    with pytest.raises(litica.LiticaConfigError):
        litica.AdminClient()


def test_admin_key_resolves_from_the_environment(monkeypatch):
    monkeypatch.setenv("LITICA_ADMIN_KEY", "admin_from_env")
    client, rec = build_admin(ok({"api_key": "lk_x"}, status=201), admin_key=None)
    client.provision(tenant_id="acme")
    assert rec.last.headers["X-Admin-Key"] == "admin_from_env"


def test_ordinary_api_key_env_is_ignored(monkeypatch):
    """LITICA_API_KEY must never quietly become an admin credential."""
    monkeypatch.setenv("LITICA_API_KEY", "lk_ordinary")
    monkeypatch.delenv("LITICA_ADMIN_KEY", raising=False)
    with pytest.raises(litica.LiticaConfigError):
        litica.AdminClient()


def test_repr_does_not_leak_the_credential():
    client, _ = build_admin(ok({"api_key": "lk_x"}))
    assert "admin_test_secret" not in repr(client)


def test_provisioned_key_never_leaks_through_repr():
    """A provisioning script that logs its result must not print the tenant's
    first key (PR #8 review)."""
    client, _ = build_admin(ok({"api_key": "lk_first_key"}, status=201))
    result = client.provision(tenant_id="acme")
    assert result.api_key == "lk_first_key"  # still fully readable
    assert "lk_first_key" not in repr(result)


def test_ordinary_clients_cannot_provision():
    """The separation the design demands: no provisioning from
    Client/AsyncClient, no memory access from AdminClient."""
    assert not hasattr(litica.Client, "provision")
    assert not hasattr(litica.AsyncClient, "provision")
    for method in ("search_memories", "add_memory", "list_memories"):
        assert not hasattr(litica.AdminClient, method)


def test_context_manager_closes_the_pool():
    client, _ = build_admin(ok({"api_key": "lk_x"}, status=201))
    with client as admin:
        admin.provision(tenant_id="acme")
    assert client._transport._client.is_closed
