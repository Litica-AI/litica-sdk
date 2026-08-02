# Contributing to the Litica Python SDK

Thanks for your interest. This document covers what this repository is, what
kinds of changes can be accepted here, and how to get a change merged.

## What this repository is

`litica` is a **thin HTTP client** for the Litica API, in synchronous
(`Client`) and asynchronous (`AsyncClient`) flavours with identical surfaces.
It contains no memory logic of its own — every method maps to exactly one HTTP
route, and the package's whole job is auth, serialization, typing, and error
shape.

The Litica service itself is a separate, closed-source product. It is not in
this repository, and issues about service behaviour belong with support rather
than here.

That distinction determines what can be accepted below.

## What we can accept

- **Bug fixes** — a method sends the wrong parameter, a response fails to parse,
  an error maps to the wrong exception
- **Typing improvements** — more precise annotations, generics, overloads
- **Documentation** — README, docstrings, examples, corrections
- **Ergonomics** that do not change what goes over the wire
- **Python version support** — making the package work on a version we do not
  currently test
- **Test coverage** for existing behaviour

## What we cannot accept here

- **New endpoints or parameters.** The client mirrors the API one-to-one. A
  method cannot exist before the route does. If you need a capability the API
  does not expose, open an issue describing the use case — the change has to
  happen service-side first.
- **Retries, caching, connection pooling, or batching helpers.** Deliberately
  out of scope for now. Each is its own design discussion; open an issue before
  writing code.
- **Renaming or restructuring the public surface.** Method names deliberately
  match the API's own vocabulary.
- **New runtime dependencies.** `httpx` is the only one, and a packaging test
  enforces that. Keeping the install light is a feature.

If you are unsure which bucket your idea falls in, open an issue and ask. That
is always cheaper than writing code that cannot be merged.

## Reporting bugs

Open an issue with:

- what you did, what you expected, what happened
- the SDK version (`python -c "import litica; print(litica.__version__)"`) and
  your Python version
- a minimal snippet that reproduces it

**Never include your API key, memory contents, or anything else sensitive.**
Redact them before pasting. If a traceback contains a key, edit it out.

## Reporting security issues

Do **not** open a public issue. See [SECURITY.md](SECURITY.md).

## Development setup

```bash
git clone https://github.com/Litica-AI/litica-sdk.git
cd litica-sdk
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the tests:

```bash
pytest                       # unit + packaging; no network, no API key needed
ruff check litica tests      # lint
ruff format litica tests     # format
```

The unit suite uses a mock HTTP transport, so it is fast and offline. It should
stay that way — a test that needs the network belongs in the contract suite.

### The contract tests

`tests/test_production_contract.py` runs against a live deployment and is
skipped unless `LITICA_TEST_API_KEY` is set. Those run in our CI on a schedule;
you do not need to run them, and they will skip silently for you.

## Code style

- **Line length 88**, enforced by ruff. Run `ruff format` before committing.
- **Type annotations on everything public.** The package ships `py.typed`, so
  users' type checkers rely on our annotations being right.
- **Docstrings on every public method**, stating the route it calls and any
  behaviour that would surprise someone — an odd response shape, a side effect,
  a base-0 vs base-1 difference.
- **Mirror the API, do not improve it.** Where the API is inconsistent, the SDK
  reproduces the inconsistency and documents it. A client that quietly "fixes"
  the API becomes a second, divergent description of it, and the divergence is
  always discovered at the worst moment.
- **`lit` is the conventional shorthand** in examples and documentation —
  `import litica as lit`. Please keep examples consistent with it.

## Tests

Every behaviour change needs a test. In practice:

- A new or changed method: assert the verb, path, query parameters, and body
- A route method exists on **both** `Client` and `AsyncClient` — the request
  logic is written once in `litica/_ops.py`, and the parity test in
  `tests/test_async_client.py` fails if the two surfaces diverge
- An error path: assert the exception type and that `detail` survives intact
- A parsing change: cover both the present and absent field

Name tests for the behaviour, not the function — `test_explicit_none_namespace_
overrides_the_client_default` beats `test_search_2`.

## Commits and pull requests

Commit messages use [Conventional Commits](https://www.conventionalcommits.org/):

```
fix(client): send include_archived as a query param, not a body field
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `ci`.

For the pull request:

- One logical change per PR. Split unrelated fixes.
- Explain **why**, not just what. The diff shows what changed.
- Make sure `pytest` and `ruff check` pass — CI runs them on Python 3.10–3.13.
- Update the README if you changed user-facing behaviour.
- Add a line to [CHANGELOG.md](CHANGELOG.md) under `Unreleased`.

## Sign-off (DCO)

Contributions must be signed off under the
[Developer Certificate of Origin](https://developercertificate.org/). This is a
statement that you wrote the contribution, or otherwise have the right to submit
it under the project's licence. Add `-s` when committing:

```bash
git commit -s -m "fix(client): ..."
```

which appends:

```
Signed-off-by: Your Name <your.email@example.com>
```

## Licence

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE), the same licence that covers this repository.

## Code of conduct

Participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Releases

Maintainers only. Releases are tagged `vX.Y.Z`, which triggers a build and a
publish to PyPI via Trusted Publishing. The tag must match the version in
`pyproject.toml` — CI checks this and refuses to publish otherwise.

We follow [semantic versioning](https://semver.org/). While the version is
`0.x`, the public surface may still change between minor versions; anything
breaking will be called out in the changelog.
