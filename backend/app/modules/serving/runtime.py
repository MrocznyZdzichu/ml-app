from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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

    def score(
        self,
        *,
        model_artifact_uri: str,
        model_hash: str,
        records: list[dict[str, Any]],
        request_id: str,
    ) -> list[dict[str, Any]]:
        body = json.dumps({
            "model_artifact_uri": model_artifact_uri,
            "model_hash": model_hash,
            "records": records,
        }, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"{self.base_url.rstrip('/')}/score",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Request-ID": request_id,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            if exc.code in {400, 422}:
                raise RuntimeInputError(f"Model rejected scoring input: {detail}") from exc
            raise RuntimeUnavailableError(f"Model runtime returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise RuntimeUnavailableError(f"Model runtime is unavailable: {exc}") from exc
        predictions = payload.get("predictions") if isinstance(payload, dict) else None
        if not isinstance(predictions, list) or len(predictions) != len(records):
            raise RuntimeUnavailableError("Model runtime returned an invalid prediction contract")
        return [item if isinstance(item, dict) else {"prediction": item} for item in predictions]
