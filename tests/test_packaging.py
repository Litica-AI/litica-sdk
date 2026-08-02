"""The engine must never ride along in a published artifact.

``litica_core`` is closed source; ``litica`` is publishable. That separation is
enforced by ``[tool.pdm.build] includes`` in ``sdk/pyproject.toml``, which is a
config line someone could widen by accident. This test builds the real
distributions and asserts what is actually inside them, so the guarantee is
checked rather than trusted.

Skipped when the ``build`` package is unavailable.
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

SDK_ROOT = Path(__file__).resolve().parents[1]

# Anything from the closed-source side of the house.
FORBIDDEN_PREFIXES = ("litica_core", "litica_server", "migrations", "evals", "demo")

EXPECTED_MODULES = {
    "litica/__init__.py",
    "litica/client.py",
    "litica/async_client.py",
    "litica/models.py",
    "litica/errors.py",
    "litica/_transport.py",
    "litica/_ops.py",
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build sdist + wheel into a throwaway directory."""
    pytest.importorskip("build", reason="needs the `build` package to make artifacts")
    outdir = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(outdir), str(SDK_ROOT)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"build failed:\n{result.stdout}\n{result.stderr}")
    wheels = list(outdir.glob("*.whl"))
    sdists = list(outdir.glob("*.tar.gz"))
    assert wheels and sdists, (
        f"expected a wheel and an sdist, got {list(outdir.iterdir())}"
    )
    return wheels[0], sdists[0]


def _wheel_names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def _sdist_names(sdist: Path) -> list[str]:
    with tarfile.open(sdist) as archive:
        # strip the leading "litica-0.1.0/" component
        return ["/".join(n.split("/")[1:]) for n in archive.getnames()]


def test_wheel_contains_no_engine_source(built):
    wheel, _ = built
    leaked = [
        name for name in _wheel_names(wheel) if name.startswith(FORBIDDEN_PREFIXES)
    ]
    assert not leaked, f"closed-source files found in the published wheel: {leaked}"


def test_sdist_contains_no_engine_source(built):
    _, sdist = built
    leaked = [
        name for name in _sdist_names(sdist) if name.startswith(FORBIDDEN_PREFIXES)
    ]
    assert not leaked, f"closed-source files found in the published sdist: {leaked}"


def test_wheel_ships_exactly_the_client_modules(built):
    wheel, _ = built
    modules = {n for n in _wheel_names(wheel) if n.endswith(".py")}
    assert modules == EXPECTED_MODULES, (
        "the wheel's Python modules changed. Confirm the new file is meant to be "
        f"public, then update EXPECTED_MODULES.\nGot: {sorted(modules)}"
    )


def test_py_typed_marker_ships(built):
    """PEP 561: without this file, type checkers ignore every annotation in the
    installed package. The SDK is fully annotated, so losing it would silently
    strip all type safety for every user."""
    wheel, sdist = built
    assert "litica/py.typed" in _wheel_names(wheel), "py.typed missing from the wheel"
    assert "litica/py.typed" in _sdist_names(sdist), "py.typed missing from the sdist"


def test_tests_are_not_published(built):
    wheel, sdist = built
    for names in (_wheel_names(wheel), _sdist_names(sdist)):
        assert not [n for n in names if n.startswith("tests/")]


def test_only_httpx_is_required(built):
    """A heavy or private dependency would drag the engine back in sideways."""
    wheel, _ = built
    with zipfile.ZipFile(wheel) as archive:
        metadata = next(n for n in archive.namelist() if n.endswith("METADATA"))
        content = archive.read(metadata).decode()
    required = [
        line.split(":", 1)[1].strip()
        for line in content.splitlines()
        if line.startswith("Requires-Dist:") and "extra ==" not in line
    ]
    assert required == ["httpx>=0.28"], f"unexpected runtime dependencies: {required}"
