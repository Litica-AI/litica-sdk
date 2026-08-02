"""Fixtures for the SDK test suite.

Request-scripting helpers live in ``helpers.py`` (imported directly by the test
modules) so this file stays fixtures-only.
"""

from __future__ import annotations

import pytest
from helpers import build_client


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """No test should inherit a developer's real credentials or endpoint."""
    for var in (
        "LITICA_API_KEY",
        "LITICA_BASE_URL",
        "LITICA_AGENT_ID",
        "LITICA_NAMESPACE_ID",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def make_client():
    return build_client


@pytest.fixture
def anyio_backend():
    """Run ``@pytest.mark.anyio`` tests on asyncio only — the SDK adds no
    trio support and httpx's asyncio backend is what users get."""
    return "asyncio"
