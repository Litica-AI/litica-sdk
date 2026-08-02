"""``litica.AdminClient`` — tenant provisioning, behind a separate credential.

Deliberately a separate class taking a separate credential (``X-Admin-Key``,
a single master secret) so that no code path holding an ordinary API key can
reach tenant creation. ``Client`` and ``AsyncClient`` cannot provision; this
class cannot search or write memories. The blast radius of ``provision`` does
not belong one autocomplete keystroke away from ``search_memories``.

Sync only, on purpose: provisioning is a one-shot setup action that lives in
scripts and CI, not inside event loops. An async variant can follow if a real
caller needs one.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from . import _ops
from ._transport import Transport
from .client import DEFAULT_BASE_URL
from .errors import LiticaConfigError
from .models import ProvisionedTenant

__all__ = ["AdminClient"]


class AdminClient:
    """Administrative client for the Litica HTTP API.

    ::

        from litica import AdminClient

        admin = AdminClient(admin_key="admin_...")
        result = admin.provision(tenant_id="acme", label="production")
        print(result.api_key)   # shown once, never recoverable

    The credential is the server's master admin key — treat it accordingly:
    it creates tenants and mints their keys. It is never read from
    ``LITICA_API_KEY``, and an ordinary API key will not work here.

    Configuration precedence is argument, then environment variable, then
    built-in default:

    ==================  ==========================  =========================
    Argument            Environment variable        Default
    ==================  ==========================  =========================
    ``admin_key``       ``LITICA_ADMIN_KEY``        required
    ``base_url``        ``LITICA_BASE_URL``         ``https://mcp.litica.org``
    ==================  ==========================  =========================
    """

    def __init__(
        self,
        admin_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_key = admin_key or os.environ.get("LITICA_ADMIN_KEY")
        if not resolved_key:
            raise LiticaConfigError(
                "No admin key. Pass admin_key=... or set the LITICA_ADMIN_KEY "
                "environment variable. (This is the server's master "
                "credential, not an ordinary lk_ API key.)"
            )

        resolved_base = (
            base_url or os.environ.get("LITICA_BASE_URL") or DEFAULT_BASE_URL
        )
        self.base_url = resolved_base.rstrip("/")
        self.timeout = timeout

        from . import __version__

        self._transport = Transport(
            base_url=self.base_url,
            api_key=resolved_key,
            timeout=timeout,
            user_agent=f"litica-python/{__version__}",
            transport=transport,
            auth_header="X-Admin-Key",
        )

    def provision(
        self, tenant_id: str, *, label: str | None = None
    ) -> ProvisionedTenant:
        """Create a tenant and mint its first API key. ``POST /provision`` (201).

        Idempotent on the tenant: provisioning an existing ``tenant_id``
        creates no duplicate — it mints an additional key for it. The
        response carries only the plaintext key (``.api_key``), shown once
        and never recoverable; hand it to the tenant's owner immediately.

        ``label`` names the key, not the tenant. When omitted, the field is
        not sent and the server applies its own default — the SDK does not
        copy that default, so it cannot drift. 401 means the admin key is
        wrong — or that the server has no admin key configured at all, which
        it reports identically on purpose.
        """
        return self._run(_ops.provision(tenant_id, label=label))

    def _run(self, op: _ops.Op) -> Any:
        return op.parse(
            self._transport.request(
                op.method,
                op.path,
                params=op.params,
                json=op.json,
                files=op.files,
                data=op.data,
                timeout=op.timeout,
            )
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._transport.close()

    def __enter__(self) -> AdminClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"AdminClient(base_url={self.base_url!r})"
