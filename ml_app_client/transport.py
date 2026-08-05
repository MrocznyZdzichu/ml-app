"""Shared HTTP transport used by the public client facade."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

import requests

from .errors import (
    ApiError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
)


class Response(Protocol):
    """Minimal response contract required by the client and its test doubles."""

    status_code: int
    text: str

    def json(self) -> Any: ...

    def iter_content(self, chunk_size: int) -> Any: ...


class Session(Protocol):
    """Minimal requests-compatible session contract."""

    headers: dict[str, str]

    def request(self, method: str, url: str, **kwargs: Any) -> Response: ...

    def close(self) -> None: ...


class TransportClientMixin:
    """Bounded JSON request handling shared by all domain clients."""

    base_url: str
    timeout: float
    _session: Session

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self._session.request(method, f"{self.base_url}{path}", **kwargs)
        except requests.RequestException as exc:
            raise ApiError(f"{method} {path} failed: {exc}") from exc
        self._raise_for_status(response, method, path)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(f"{method} {path} returned invalid JSON") from exc

    @staticmethod
    def _format_error_detail(detail: Any) -> str:
        """Turn FastAPI validation arrays into a compact actionable message."""
        if not isinstance(detail, list):
            return str(detail)
        messages: list[str] = []
        for item in detail:
            if not isinstance(item, Mapping):
                messages.append(str(item))
                continue
            location = item.get("loc", ())
            label = ".".join(str(part) for part in location if part not in {"query", "body"})
            message = str(item.get("msg") or "invalid value")
            messages.append(f"{label}: {message}" if label else message)
        return "; ".join(messages)

    @staticmethod
    def _raise_for_status(response: Response, method: str, path: str) -> None:
        if response.status_code < 400:
            return
        try:
            body = response.json()
            detail = body.get("detail", body) if isinstance(body, dict) else body
        except (ValueError, TypeError):
            detail = response.text[:500]
        error = (
            AuthenticationError if response.status_code == 401
            else AuthorizationError if response.status_code == 403
        else ResourceNotFoundError if response.status_code == 404
            else ConflictError if response.status_code == 409
            else ApiError
        )
        raise error(
            f"{method} {path} returned HTTP {response.status_code}: "
            f"{TransportClientMixin._format_error_detail(detail)}"
        )
