"""Authentication and machine-credential operations."""

from __future__ import annotations

from typing import Any, Mapping

from .errors import AuthenticationError
from .transport import TransportClientMixin


class AuthenticationClientMixin(TransportClientMixin):
    """Authentication workflow composed into :class:`MLAppClient`."""

    def login(self, login: str, password: str) -> None:
        """Authenticate this client without persisting the password."""
        payload = self._request(
            "POST", "/auth/login", json={"login": login, "password": password}
        )
        token = str(payload.get("access_token") or "")
        if not token:
            raise AuthenticationError("Login response did not contain an access token")
        self._session.headers["Authorization"] = f"Bearer {token}"

    def me(self) -> Mapping[str, Any]:
        """Return the authenticated user's stable profile and platform roles."""
        return self._request("GET", "/auth/me")

    def create_api_credential(
        self,
        name: str,
        *,
        expires_at: str | None = None,
    ) -> Mapping[str, Any]:
        """Create a long-lived credential. Its token is returned only once."""
        return self._request("POST", "/auth/api-credentials", json={
            "name": name,
            "expires_at": expires_at,
        })

    def list_api_credentials(self) -> list[Mapping[str, Any]]:
        return self._request("GET", "/auth/api-credentials")

    def revoke_api_credential(self, credential_id: str) -> None:
        self._request("DELETE", f"/auth/api-credentials/{credential_id}")
