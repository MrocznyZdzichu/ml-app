"""Small, stable Python interface to ML App's integration API.

The client streams dataset files from disk and keeps API responses bounded. It
intentionally exposes only supported integration operations instead of mirroring
every backend endpoint.
"""

from __future__ import annotations

import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import requests


class ApiError(RuntimeError):
    """The platform rejected a request or returned an invalid response."""


class AuthenticationError(ApiError):
    """Authentication credentials are missing or invalid."""


class ResourceNotFoundError(ApiError):
    """A named platform resource could not be found."""


class ResourceAmbiguousError(ApiError):
    """A name resolved to more than one platform resource."""


class _Response(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...


class _Session(Protocol):
    headers: dict[str, str]

    def request(self, method: str, url: str, **kwargs: Any) -> _Response: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class Dataset:
    id: str
    logical_id: str
    name: str
    version_number: int
    row_count: int | None
    format: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "Dataset":
        return cls(
            id=str(value["id"]),
            logical_id=str(value["logical_id"]),
            name=str(value["name"]),
            version_number=int(value["version_number"]),
            row_count=None if value.get("row_count") is None else int(value["row_count"]),
            format=str(value["format"]),
            raw=value,
        )


@dataclass(frozen=True)
class PipelineRun:
    id: str
    pipeline_id: str
    pipeline_version_id: str
    status: str
    processed_row_count: int | None
    error_message: str
    raw: Mapping[str, Any]

    @property
    def finished(self) -> bool:
        return self.status in {"succeeded", "failed", "cancelled"}

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "PipelineRun":
        return cls(
            id=str(value["id"]),
            pipeline_id=str(value["pipeline_id"]),
            pipeline_version_id=str(value["pipeline_version_id"]),
            status=str(value["status"]),
            processed_row_count=(
                None if value.get("processed_row_count") is None
                else int(value["processed_row_count"])
            ),
            error_message=str(value.get("error_message") or ""),
            raw=value,
        )


def _one_named(items: list[Mapping[str, Any]], name: str, resource: str) -> Mapping[str, Any]:
    matches = [item for item in items if item.get("name") == name]
    if not matches:
        raise ResourceNotFoundError(f"{resource} named {name!r} was not found")
    if len(matches) > 1:
        raise ResourceAmbiguousError(
            f"{resource} name {name!r} is ambiguous ({len(matches)} matches)"
        )
    return matches[0]


class MLAppClient:
    """Authenticated facade for supported dataset and pipeline integrations."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        access_token: str | None = None,
        *,
        timeout: float = 30.0,
        upload_timeout: float = 600.0,
        session: _Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.upload_timeout = upload_timeout
        self._session: _Session = session or requests.Session()
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

    def login(self, login: str, password: str) -> None:
        """Authenticate this client without persisting the password."""
        payload = self._request(
            "POST", "/auth/login", json={"login": login, "password": password}
        )
        token = str(payload.get("access_token") or "")
        if not token:
            raise AuthenticationError("Login response did not contain an access token")
        self._session.headers["Authorization"] = f"Bearer {token}"

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "MLAppClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def upload_dataset(
        self,
        file_path: str | Path,
        *,
        name: str | None = None,
        description: str = "",
        tags: tuple[str, ...] | list[str] = (),
        logical_id: str | None = None,
    ) -> Dataset:
        """Stream a CSV or Parquet file as a new dataset or immutable version."""
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(path)
        data: dict[str, str] = {"description": description, "tags": ",".join(tags)}
        if name is not None:
            data["name"] = name
        if logical_id is not None:
            data["logical_id"] = logical_id
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as stream:
            payload = self._request(
                "POST",
                "/datasets/upload",
                data=data,
                files={"file": (path.name, stream, content_type)},
                timeout=self.upload_timeout,
            )
        return Dataset.from_api(payload)

    def upload_dataset_version(
        self,
        file_path: str | Path,
        *,
        business_case_name: str,
        dataset_name: str,
        description: str = "",
        tags: tuple[str, ...] | list[str] = (),
    ) -> Dataset:
        """Resolve a BC-attached dataset by name and upload its next version."""
        business_case = self._business_case_by_name(business_case_name)
        attachments = self._request(
            "GET", f"/business-cases/{business_case['id']}/data-attachments"
        )
        attached_ids = {item["data_asset_id"] for item in attachments}
        candidates = [
            item for item in self._request("GET", "/datasets")
            if item.get("id") in attached_ids
        ]
        dataset = _one_named(candidates, dataset_name, "Dataset attached to Business Case")
        return self.upload_dataset(
            file_path,
            logical_id=str(dataset["logical_id"]),
            description=description,
            tags=tags,
        )

    def run_pipeline(
        self,
        pipeline_id: str,
        *,
        pipeline_version_id: str | None = None,
        runtime_parameters: Mapping[str, Any] | None = None,
        input_versions: Mapping[str, str] | None = None,
        model_versions: Mapping[str, str] | None = None,
        dry_run: bool = False,
        step_id: str | None = None,
    ) -> PipelineRun:
        payload: dict[str, Any] = {
            "runtime_parameters": dict(runtime_parameters or {}),
            "input_versions": dict(input_versions or {}),
            "model_versions": dict(model_versions or {}),
            "is_dry_run": dry_run,
        }
        if pipeline_version_id is not None:
            payload["pipeline_version_id"] = pipeline_version_id
        if step_id is not None:
            payload["step_id"] = step_id
        return PipelineRun.from_api(
            self._request("POST", f"/pipelines/{pipeline_id}/runs", json=payload)
        )

    def run_pipeline_by_name(
        self,
        *,
        business_case_name: str,
        pipeline_name: str,
        runtime_parameters: Mapping[str, Any] | None = None,
        input_versions: Mapping[str, str] | None = None,
        model_versions: Mapping[str, str] | None = None,
        dry_run: bool = False,
        step_id: str | None = None,
    ) -> PipelineRun:
        """Run the newest published version of a pipeline resolved by names."""
        business_case = self._business_case_by_name(business_case_name)
        pipelines = self._request(
            "GET", "/pipelines", params={"business_case_id": business_case["id"]}
        )
        pipeline = _one_named(pipelines, pipeline_name, "Pipeline in Business Case")
        versions = self._request("GET", f"/pipelines/{pipeline['id']}/versions")
        published = [item for item in versions if item.get("status") == "published"]
        if not published:
            raise ResourceNotFoundError(
                f"Pipeline {pipeline_name!r} has no published version"
            )
        version = max(published, key=lambda item: int(item["version_number"]))
        return self.run_pipeline(
            str(pipeline["id"]),
            pipeline_version_id=str(version["id"]),
            runtime_parameters=runtime_parameters,
            input_versions=input_versions,
            model_versions=model_versions,
            dry_run=dry_run,
            step_id=step_id,
        )

    def get_pipeline_run(self, pipeline_id: str, run_id: str) -> PipelineRun:
        return PipelineRun.from_api(
            self._request("GET", f"/pipelines/{pipeline_id}/runs/{run_id}")
        )

    def wait_for_pipeline_run(
        self,
        run: PipelineRun,
        *,
        poll_interval: float = 2.0,
        timeout: float | None = None,
        on_update: Callable[[PipelineRun], None] | None = None,
    ) -> PipelineRun:
        """Poll a run to completion without downloading its output data."""
        started = time.monotonic()
        current = run
        while not current.finished:
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"Pipeline run {run.id} did not finish within {timeout}s")
            time.sleep(poll_interval)
            current = self.get_pipeline_run(run.pipeline_id, run.id)
            if on_update is not None:
                on_update(current)
        if current.status != "succeeded":
            detail = current.error_message or "no error detail returned"
            raise ApiError(f"Pipeline run {current.id} ended as {current.status}: {detail}")
        return current

    def _business_case_by_name(self, name: str) -> Mapping[str, Any]:
        return _one_named(self._request("GET", "/business-cases"), name, "Business Case")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self._session.request(method, f"{self.base_url}{path}", **kwargs)
        except requests.RequestException as exc:
            raise ApiError(f"{method} {path} failed: {exc}") from exc
        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail", body) if isinstance(body, dict) else body
            except (ValueError, TypeError):
                detail = response.text[:500]
            error = AuthenticationError if response.status_code in {401, 403} else ApiError
            raise error(f"{method} {path} returned HTTP {response.status_code}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(f"{method} {path} returned invalid JSON") from exc
