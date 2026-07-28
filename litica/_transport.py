"""HTTP plumbing: auth header, parameter cleaning, status -> exception mapping.

Kept behind a seam so an ``AsyncClient`` can be added later (its own ticket)
without touching ``client.py``'s method bodies.
"""

from __future__ import annotations

from typing import Any

import httpx

from .errors import (
    LiticaConnectionError,
    LiticaRateLimitError,
    LiticaResponseError,
    LiticaTimeout,
    exception_for_status,
)

__all__ = ["Transport", "clean"]


def clean(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values.

    Not sending a parameter is how the API expresses "unset", and it is also
    how an explicit ``namespace_id=None`` reaches the server as agent scope.
    Sending ``None`` would serialize to an empty string and mean something else
    entirely.
    """
    return {k: v for k, v in mapping.items() if v is not None}


def _detail_from(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return response.text.strip()[:500] or response.reason_phrase
    if isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
        return detail if isinstance(detail, str) else repr(detail)
    return response.text.strip()[:500] or response.reason_phrase


class Transport:
    """Thin wrapper over ``httpx.Client``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"X-API-Key": api_key, "User-Agent": user_agent},
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Issue one request and return its parsed JSON body."""
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json is not None:
            kwargs["json"] = json
        if files is not None:
            kwargs["files"] = files
        if data is not None:
            kwargs["data"] = data
        if timeout is not None:
            kwargs["timeout"] = timeout

        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise LiticaTimeout(f"{method} {path} timed out") from exc
        except httpx.HTTPError as exc:
            raise LiticaConnectionError(f"{method} {path} failed: {exc}") from exc

        if response.status_code >= 400:
            raise self._error(response)

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except Exception as exc:
            raise LiticaResponseError(
                f"{method} {path} returned a non-JSON body "
                f"(status {response.status_code}, "
                f"content-type {response.headers.get('content-type')!r})",
                status_code=response.status_code,
                response=response,
            ) from exc

    @staticmethod
    def _error(response: httpx.Response) -> Exception:
        detail = _detail_from(response)
        status = response.status_code
        exc_type = exception_for_status(status)
        message = f"{status} {response.reason_phrase}: {detail}"

        if exc_type is LiticaRateLimitError:
            raw = response.headers.get("Retry-After")
            try:
                retry_after = int(raw) if raw is not None else None
            except ValueError:
                retry_after = None
            return LiticaRateLimitError(
                message,
                status_code=status,
                detail=detail,
                response=response,
                retry_after=retry_after,
            )
        return exc_type(message, status_code=status, detail=detail, response=response)

    def close(self) -> None:
        self._client.close()
