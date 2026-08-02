"""API-key self-service: mint, list, revoke (tenant-scoped, ordinary auth).

These routes are covered on both clients through the shared ops layer; the
async parity test guarantees ``AsyncClient`` carries them, so the request
shapes are pinned once, here.

``GET /viz/config`` is deliberately NOT wrapped: it is unauthenticated
playground bootstrap (it serves the Clerk publishable key for the sign-in
widget) and has no meaning for an API-key caller. The exclusion is recorded
in the engine repo's route-coverage guard.
"""

from __future__ import annotations

import pytest
from helpers import build_client, ok

import litica

MINTED = {
    "api_key": "lk_new_plaintext",
    "key": {"id": 3, "label": "ci", "created_at": "2026-08-02T00:00:00Z"},
}

KEYS = {
    "keys": [
        {"id": 3, "label": "ci", "created_at": "2026-08-02T00:00:00Z"},
        {
            "id": 1,
            "label": "",
            "created_at": "2026-07-01T00:00:00Z",
            "revoked_at": "2026-07-30T00:00:00Z",
        },
    ]
}


def test_mint_key_posts_the_label():
    client, rec = build_client(ok(MINTED, status=201))
    minted = client.mint_key(label="ci")
    assert rec.last.method == "POST"
    assert rec.last.url.path == "/keys"
    assert rec.last_json == {"label": "ci"}
    assert minted.api_key == "lk_new_plaintext"
    assert minted.key.id == 3
    assert minted.key.label == "ci"


def test_mint_key_defaults_to_an_empty_label():
    client, rec = build_client(ok(MINTED, status=201))
    client.mint_key()
    assert rec.last_json == {"label": ""}


def test_mint_key_tolerates_a_missing_metadata_row():
    """The server sends ``key: null`` when it cannot echo the row back."""
    client, _ = build_client(ok({"api_key": "lk_x", "key": None}, status=201))
    minted = client.mint_key()
    assert minted.api_key == "lk_x"
    assert minted.key is None


def test_mint_key_never_reprs_the_plaintext_row():
    """``raw`` is repr-suppressed, so a logged model does not leak the key."""
    client, _ = build_client(ok(MINTED, status=201))
    minted = client.mint_key()
    assert "lk_new_plaintext" in repr(minted)  # api_key is the point of the call
    assert minted.key is not None
    assert "lk_new_plaintext" not in repr(minted.key)


def test_over_cap_mint_is_a_conflict():
    client, _ = build_client(ok({"detail": "active key limit reached (5)"}, status=409))
    with pytest.raises(litica.LiticaConflictError) as caught:
        client.mint_key(label="one too many")
    assert caught.value.status_code == 409
    assert "limit" in caught.value.detail


def test_list_keys_returns_metadata_newest_first():
    client, rec = build_client(ok(KEYS))
    keys = client.list_keys()
    assert rec.last.method == "GET"
    assert rec.last.url.path == "/keys"
    assert [k.id for k in keys] == [3, 1]
    assert keys[1].revoked_at == "2026-07-30T00:00:00Z"


def test_revoke_key_unwraps_the_id():
    client, rec = build_client(ok({"revoked": 3}))
    assert client.revoke_key(3) == 3
    assert rec.last.method == "DELETE"
    assert rec.last.url.path == "/keys/3"


def test_revoking_a_foreign_or_dead_key_is_not_found():
    client, _ = build_client(ok({"detail": "unknown key"}, status=404))
    with pytest.raises(litica.LiticaNotFoundError):
        client.revoke_key(999)
