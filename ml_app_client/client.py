"""Stable, authenticated facade for the ML App integration API."""

from __future__ import annotations

import os
from getpass import getpass
from typing import Any, Callable

import requests

from .auth import AuthenticationClientMixin
from .access_requests import AccessRequestClientMixin
from .business_cases import BusinessCaseClientMixin
from .datasets import DatasetClientMixin
from .errors import AuthenticationError
from .model_registry import ModelRegistryClientMixin
from .pipelines import PipelineClientMixin
from .presentation import PresentationClientMixin
from .scoring_reports import ScoringReportClientMixin
from .serving import ServingClientMixin
from .transport import Session


class MLAppClient(
    AuthenticationClientMixin,
    DatasetClientMixin,
    BusinessCaseClientMixin,
    AccessRequestClientMixin,
    PipelineClientMixin,
    PresentationClientMixin,
    ScoringReportClientMixin,
    ModelRegistryClientMixin,
    ServingClientMixin,
):
    """Authenticated facade composed from focused domain clients."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        access_token: str | None = None,
        *,
        timeout: float = 30.0,
        upload_timeout: float = 600.0,
        session: Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.upload_timeout = upload_timeout
        self._session: Session = session or requests.Session()
        self._session.headers.setdefault("Accept", "application/json")
        if access_token:
            self._session.headers["Authorization"] = f"Bearer {access_token.strip()}"

    @classmethod
    def from_env(cls, **kwargs: Any) -> "MLAppClient":
        """Create a client from ML_APP_API_URL and ML_APP_ACCESS_TOKEN."""
        return cls(
            base_url=os.getenv("ML_APP_API_URL", "http://localhost:8000/api/v1"),
            access_token=os.getenv("ML_APP_ACCESS_TOKEN") or None,
            **kwargs,
        )

    @classmethod
    def connect(
        cls,
        *,
        login: str | None = None,
        prompt: Callable[[str], str] = input,
        password_prompt: Callable[[str], str] = getpass,
        **kwargs: Any,
    ) -> "MLAppClient":
        """Create an authenticated client, prompting only when no token is configured.

        ``ML_APP_ACCESS_TOKEN`` remains the preferred non-interactive mechanism.
        Interactive notebooks can use this method without placing a password in a cell.
        ``ML_APP_LOGIN`` may provide the default account name while the password is
        still collected through a hidden prompt.
        """
        client = cls.from_env(**kwargs)
        if os.getenv("ML_APP_ACCESS_TOKEN"):
            return client
        login_name = (
            login
            or os.getenv("ML_APP_LOGIN")
            or prompt("ML App login or email: ")
        ).strip()
        if not login_name:
            raise AuthenticationError("A login or email is required")
        client.login(login_name, password_prompt("ML App password: "))
        return client

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "MLAppClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
