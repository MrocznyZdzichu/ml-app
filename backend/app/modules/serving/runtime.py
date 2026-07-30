from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx2

from app.core.config import settings


class RuntimeUnavailableError(RuntimeError):
    pass


class RuntimeInputError(ValueError):
    pass


class RuntimeGateway(Protocol):
    def score(
        self,
        *,
        model_artifact_uri: str,
        model_hash: str,
        records: list[dict[str, Any]],
        request_id: str,
    ) -> list[dict[str, Any]]: ...


@dataclass
class HttpModelRuntimeGateway:
    base_url: str = settings.model_runtime_url
    timeout: float = settings.model_runtime_timeout_seconds
    client: httpx2.Client | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx2.Client(
                base_url=self.base_url.rstrip("/"),
                timeout=self.timeout,
                limits=httpx2.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0,
                ),
            )

    def score(
        self,
        *,
        model_artifact_uri: str,
        model_hash: str,
        records: list[dict[str, Any]],
        request_id: str,
    ) -> list[dict[str, Any]]:
        payload = {
            "model_artifact_uri": model_artifact_uri,
            "model_hash": model_hash,
            "records": records,
        }
        try:
            assert self.client is not None
            response = self.client.post(
                "/score",
                json=payload,
                headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Request-ID": request_id,
                },
            )
            if response.status_code in {400, 422}:
                raise RuntimeInputError(
                    f"Model rejected scoring input: {response.text[:1000]}"
                )
            if response.status_code >= 400:
                raise RuntimeUnavailableError(
                    "Model runtime returned HTTP "
                    f"{response.status_code}: {response.text[:1000]}"
                )
            result = response.json()
        except (RuntimeInputError, RuntimeUnavailableError):
            raise
        except (httpx2.RequestError, ValueError) as exc:
            raise RuntimeUnavailableError(f"Model runtime is unavailable: {exc}") from exc
        predictions = result.get("predictions") if isinstance(result, dict) else None
        if not isinstance(predictions, list) or len(predictions) != len(records):
            raise RuntimeUnavailableError("Model runtime returned an invalid prediction contract")
        return [item if isinstance(item, dict) else {"prediction": item} for item in predictions]
