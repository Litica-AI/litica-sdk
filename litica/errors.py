"""Exception hierarchy.

Everything the SDK raises inherits from :class:`LiticaError`, so
``except litica.LiticaError`` is a complete catch. HTTP failures carry the
status code, the server's ``detail`` string verbatim, and the raw response —
nothing is swallowed, nothing is reworded.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "LiticaError",
    "LiticaConfigError",
    "LiticaResponseError",
    "LiticaTimeout",
    "LiticaConnectionError",
    "LiticaAPIError",
    "LiticaAuthError",
    "LiticaNotFoundError",
    "LiticaConflictError",
    "LiticaValidationError",
    "LiticaUnsupportedMediaError",
    "LiticaRateLimitError",
    "LiticaServerError",
]


class LiticaError(Exception):
    """Base for every error this SDK raises."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
        response: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.response = response


class LiticaConfigError(LiticaError):
    """The client was constructed without something it needs (e.g. an API key)."""


class LiticaResponseError(LiticaError):
    """The server replied with a body the SDK could not read as expected.

    Raised for a non-JSON success body, or a response missing a field the SDK
    treats as part of the contract. Unknown *extra* fields never raise — they
    stay reachable through ``.raw``.
    """


class LiticaTimeout(LiticaError):
    """A request, or a ``wait=True`` poll loop, ran out of time."""


class LiticaConnectionError(LiticaError):
    """The server could not be reached at all."""


class LiticaAPIError(LiticaError):
    """A non-2xx response that has no more specific subclass."""


class LiticaAuthError(LiticaAPIError):
    """401 — missing or invalid ``X-API-Key``."""


class LiticaNotFoundError(LiticaAPIError):
    """404 — unknown memory, namespace, or namespace agent."""


class LiticaConflictError(LiticaAPIError):
    """409 — e.g. a namespace name that already exists."""


class LiticaValidationError(LiticaAPIError):
    """422 — the request was well-formed but the server rejected its contents."""


class LiticaUnsupportedMediaError(LiticaAPIError):
    """415 — a document type the server cannot parse."""


class LiticaRateLimitError(LiticaAPIError):
    """429 — over the per-key budget. ``retry_after`` is seconds, when sent."""

    def __init__(self, *args: Any, retry_after: int | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class LiticaServerError(LiticaAPIError):
    """5xx — including 503 when the server is missing an optional parser."""


STATUS_MAP: dict[int, type[LiticaAPIError]] = {
    401: LiticaAuthError,
    403: LiticaAuthError,
    404: LiticaNotFoundError,
    409: LiticaConflictError,
    415: LiticaUnsupportedMediaError,
    422: LiticaValidationError,
    429: LiticaRateLimitError,
}


def exception_for_status(status_code: int) -> type[LiticaAPIError]:
    if status_code in STATUS_MAP:
        return STATUS_MAP[status_code]
    if status_code >= 500:
        return LiticaServerError
    return LiticaAPIError
