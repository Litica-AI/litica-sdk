"""Test helpers: a real ``httpx`` client wired to a scripted mock transport.

Using ``httpx.MockTransport`` rather than a hand-rolled fake keeps real httpx
serialization in the loop — bool -> "true", None-dropping, multipart encoding —
so the tests catch encoding bugs a stub would hide.
"""

from __future__ import annotations

import json as jsonlib

import httpx

import litica


class Recorder:
    """Captures every request the client issues."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "no request was issued"
        return self.requests[-1]

    @property
    def last_json(self) -> dict:
        return jsonlib.loads(self.last.content)

    def param(self, name: str) -> str | None:
        return self.last.url.params.get(name)

    @property
    def param_names(self) -> set[str]:
        return set(self.last.url.params.keys())


def ok(payload, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _recording_transport(responses) -> tuple[httpx.MockTransport, Recorder]:
    """A ``MockTransport`` that records requests and replays ``responses``.

    ``responses`` is either a single ``httpx.Response``, a list replayed in
    order, or a callable taking the request and returning a response.
    """
    recorder = Recorder()

    if callable(responses):
        producer = responses
    elif isinstance(responses, list):
        queue = list(responses)

        def producer(_request):
            assert queue, "client made more requests than the test scripted"
            return queue.pop(0)
    else:

        def producer(_request):
            return responses

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return producer(request)

    return httpx.MockTransport(handler), recorder


def build_client(responses, **kwargs) -> tuple[litica.Client, Recorder]:
    """Client whose HTTP layer replays ``responses`` (see ``_recording_transport``)."""
    transport, recorder = _recording_transport(responses)
    kwargs.setdefault("api_key", "lk_test")
    kwargs.setdefault("base_url", "https://api.test")
    client = litica.Client(transport=transport, **kwargs)
    return client, recorder


def build_async_client(responses, **kwargs) -> tuple[litica.AsyncClient, Recorder]:
    """Async twin of :func:`build_client` — same scripting, same recorder."""
    transport, recorder = _recording_transport(responses)
    kwargs.setdefault("api_key", "lk_test")
    kwargs.setdefault("base_url", "https://api.test")
    client = litica.AsyncClient(transport=transport, **kwargs)
    return client, recorder
