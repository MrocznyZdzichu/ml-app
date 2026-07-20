"""Small, stable Python interface to ML App's integration API.

The client streams dataset files from disk and keeps API responses bounded. It
intentionally exposes only supported integration operations instead of mirroring
every backend endpoint.
"""

from __future__ import annotations

import mimetypes
import os
import time
import warnings
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote

import requests


class ApiError(RuntimeError):
    """The platform rejected a request or returned an invalid response."""


class AuthenticationError(ApiError):
    """Authentication credentials are missing or invalid."""


class AuthorizationError(ApiError):
    """The authenticated user lacks access required for an operation."""


class ConflictError(ApiError):
    """The requested mutation conflicts with an existing platform resource."""


class ResourceNotFoundError(ApiError):
    """A named platform resource could not be found."""


class ResourceAmbiguousError(ApiError):
    """A name resolved to more than one platform resource."""


class _Response(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...

    def iter_content(self, chunk_size: int) -> Any: ...


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


@dataclass(frozen=True)
class Deployment:
    id: str
    name: str
    slug: str
    business_case_id: str
    status: str
    endpoint_url: str
    active_revision: Mapping[str, Any]
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "Deployment":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            slug=str(value["slug"]),
            business_case_id=str(value["business_case_id"]),
            status=str(value["status"]),
            endpoint_url=str(value.get("endpoint_url") or ""),
            active_revision=dict(value.get("active_revision") or {}),
            raw=value,
        )


@dataclass(frozen=True)
class ModelServingUsage:
    model_id: str
    deployment_id: str
    deployment_name: str
    deployment_status: str
    revision_version: int
    role: str
    endpoint_url: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "ModelServingUsage":
        return cls(
            model_id=str(value["model_id"]),
            deployment_id=str(value["deployment_id"]),
            deployment_name=str(value["deployment_name"]),
            deployment_status=str(value["deployment_status"]),
            revision_version=int(value["revision_version"]),
            role=str(value["role"]),
            endpoint_url=str(value.get("endpoint_url") or ""),
            raw=value,
        )


@dataclass(frozen=True)
class PredictionResult:
    request_id: str
    deployment_id: str
    deployment_revision_id: str
    model_id: str
    served_role: str
    fallback_used: bool
    predictions: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "PredictionResult":
        return cls(
            request_id=str(value["request_id"]),
            deployment_id=str(value["deployment_id"]),
            deployment_revision_id=str(value["deployment_revision_id"]),
            model_id=str(value["model_id"]),
            served_role=str(value["served_role"]),
            fallback_used=bool(value.get("fallback_used")),
            predictions=tuple(value.get("predictions") or ()),
            warnings=tuple(str(item) for item in value.get("warnings") or ()),
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
        login_name = (login or os.getenv("ML_APP_LOGIN") or prompt("ML App login or email: ")).strip()
        if not login_name:
            raise AuthenticationError("A login or email is required")
        client.login(login_name, password_prompt("ML App password: "))
        return client

    def login(self, login: str, password: str) -> None:
        """Authenticate this client without persisting the password."""
        payload = self._request(
            "POST", "/auth/login", json={"login": login, "password": password}
        )
        token = str(payload.get("access_token") or "")
        if not token:
            raise AuthenticationError("Login response did not contain an access token")
        self._session.headers["Authorization"] = f"Bearer {token}"

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

    def list_datasets(self) -> list[Mapping[str, Any]]:
        """List bounded dataset metadata visible to the authenticated user."""
        return self._request("GET", "/datasets")

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

    def business_case_by_name(self, name: str) -> Mapping[str, Any]:
        """Resolve one visible Business Case by its globally unique name."""
        return self._business_case_by_name(name)

    def create_business_case(
        self,
        *,
        name: str,
        description: str = "",
        problem_type: str = "custom",
        status: str = "draft",
        business_owner: str = "",
        primary_metric: str = "",
        target_column: str = "",
        business_goal: str = "",
        success_criteria: str = "",
    ) -> Mapping[str, Any]:
        """Create a Business Case owned by the authenticated user."""
        return self._request("POST", "/business-cases", json={
            "name": name,
            "description": description,
            "problem_type": problem_type,
            "status": status,
            "business_owner": business_owner,
            "primary_metric": primary_metric,
            "target_column": target_column,
            "business_goal": business_goal,
            "success_criteria": success_criteria,
        })

    def ensure_business_case(self, **definition: Any) -> tuple[Mapping[str, Any], bool]:
        """Return a visible BC or create it once, with race-safe conflict handling."""
        name = str(definition.get("name") or "").strip()
        if not name:
            raise ValueError("Business Case name is required")
        try:
            return self._business_case_by_name(name), False
        except ResourceNotFoundError:
            pass
        try:
            return self.create_business_case(**definition), True
        except ConflictError as exc:
            try:
                return self._business_case_by_name(name), False
            except ResourceNotFoundError:
                raise AuthorizationError(
                    f"Business Case {name!r} already exists but is not accessible. "
                    "Ask an administrator or Business Case manager to grant access."
                ) from exc

    def attach_dataset(
        self,
        business_case_id: str,
        dataset_id: str,
        *,
        role: str,
        context_note: str = "",
        primary_key_column: str = "",
        target_column: str = "",
    ) -> Mapping[str, Any]:
        """Attach one readable dataset version to a Business Case."""
        return self._request(
            "POST",
            f"/business-cases/{business_case_id}/data-attachments",
            json={
                "data_asset_id": dataset_id,
                "data_asset_kind": "dataset",
                "role": role,
                "context_note": context_note,
                "primary_key_column": primary_key_column,
                "target_column": target_column,
                "origin": "uploaded",
            },
        )

    def list_business_case_attachments(
        self, business_case_id: str
    ) -> list[Mapping[str, Any]]:
        return self._request("GET", f"/business-cases/{business_case_id}/data-attachments")

    def list_pipelines(self, business_case_id: str) -> list[Mapping[str, Any]]:
        return self._request(
            "GET", "/pipelines", params={"business_case_id": business_case_id}
        )

    def create_pipeline(
        self,
        *,
        business_case_id: str,
        name: str,
        definition: Mapping[str, Any],
        pipeline_type: str = "custom",
        description: str = "",
    ) -> Mapping[str, Any]:
        """Create a pipeline and its first editable draft definition."""
        return self._request("POST", "/pipelines", json={
            "business_case_id": business_case_id,
            "name": name,
            "description": description,
            "type": pipeline_type,
            "definition": dict(definition),
        })

    def publish_pipeline_draft(self, pipeline_id: str) -> Mapping[str, Any]:
        """Validate and publish the current draft version of a pipeline."""
        return self._request(
            "POST", f"/pipelines/{pipeline_id}/versions/draft/publish"
        )

    def preview_dataset(self, dataset_id: str, *, limit: int = 20) -> Mapping[str, Any]:
        """Return a bounded dataset preview suitable for interactive inspection."""
        if limit < 1 or limit > 50_000:
            raise ValueError("limit must be between 1 and 50000")
        payload = self._request(
            "GET", f"/datasets/{dataset_id}/preview", params={"limit": limit}
        )
        if not isinstance(payload, Mapping):
            raise ApiError("Dataset preview returned an invalid response")
        return payload

    def download_dataset(
        self,
        dataset_id: str,
        destination: str | Path,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Path:
        """Stream a complete dataset to disk without buffering it in memory."""
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        path = Path(destination).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f"{path.name}.part")
        response = self._session.request(
            "GET",
            f"{self.base_url}/datasets/{dataset_id}/download",
            timeout=self.upload_timeout,
            stream=True,
        )
        self._raise_for_status(response, "GET", f"/datasets/{dataset_id}/download")
        try:
            with partial.open("wb") as output:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        output.write(chunk)
            partial.replace(path)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return path

    def prediction_dataset_id(self, run: PipelineRun) -> str:
        """Return the immutable prediction dataset ID recorded by a scoring run."""
        outputs = run.raw.get("output_manifest") or []
        matches = [
            item for item in outputs
            if isinstance(item, Mapping)
            and item.get("artifact_type") == "prediction_dataset"
            and item.get("dataset_id")
        ]
        if len(matches) != 1:
            raise ApiError(
                f"Pipeline run {run.id} has {len(matches)} prediction dataset outputs; expected one"
            )
        return str(matches[0]["dataset_id"])

    def output_dataset_id(
        self,
        run: PipelineRun,
        *,
        artifact_type: str = "dataset",
    ) -> str:
        """Return one immutable dataset output of the requested artifact type."""
        outputs = run.raw.get("output_manifest") or []
        matches = [
            item for item in outputs
            if isinstance(item, Mapping)
            and item.get("artifact_type") == artifact_type
            and item.get("dataset_id")
        ]
        if len(matches) != 1:
            raise ApiError(
                f"Pipeline run {run.id} has {len(matches)} {artifact_type!r} dataset outputs; expected one"
            )
        return str(matches[0]["dataset_id"])

    def scoring_report_for_run(
        self,
        run: PipelineRun,
        *,
        business_case_name: str,
    ) -> Mapping[str, Any]:
        """Fetch the report artifact created by a completed scoring or monitoring run."""
        business_case = self._business_case_by_name(business_case_name)
        reports = self._request(
            "GET", "/scoring-reports", params={"business_case_id": business_case["id"]}
        )
        matches = [
            report for report in reports
            if isinstance(report, Mapping) and report.get("pipeline_run_id") == run.id
        ]
        if len(matches) != 1:
            raise ApiError(
                f"Pipeline run {run.id} has {len(matches)} scoring report artifacts; expected one"
            )
        return matches[0]

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

    def list_models(self) -> list[Mapping[str, Any]]:
        """List model versions visible through the current Business Case grants."""
        return self._request("GET", "/models")

    def promote_model(
        self,
        model: str,
        stage: str,
        *,
        version: str | int | None = None,
    ) -> Mapping[str, Any]:
        """Change a model version lifecycle stage using an ID or friendly name.

        When ``model`` is a name, the newest version is selected by default.
        Pass ``version="v5"`` or ``version=5`` to choose an explicit version.
        """
        if stage == "candidate":
            warnings.warn(
                "Model stage 'candidate' is deprecated; use 'developed' instead",
                DeprecationWarning,
                stacklevel=2,
            )
            stage = "developed"
        allowed_stages = {"developed", "staging", "production", "archived"}
        if stage not in allowed_stages:
            raise ValueError(
                "stage must be one of: developed, staging, production, archived"
            )
        models = self.list_models()
        normalized = model.strip().casefold()
        matches = [
            item for item in models
            if str(item.get("id") or "") == model
            or str(item.get("name") or "").strip().casefold() == normalized
        ]
        if version is not None:
            normalized_version = str(version).strip().casefold()
            if normalized_version.isdigit():
                normalized_version = f"v{normalized_version}"
            matches = [
                item for item in matches
                if str(item.get("version") or "").casefold() == normalized_version
                or str(item.get("version_number") or "") == str(version)
            ]
        if not matches:
            suffix = "" if version is None else f" version {version!r}"
            raise ResourceNotFoundError(f"Model {model!r}{suffix} was not found")
        selected = max(matches, key=lambda item: int(item.get("version_number") or 0))
        return self._request(
            "PATCH",
            f"/models/{selected['id']}/stage",
            json={"stage": stage},
        )

    def list_deployments(self) -> list[Deployment]:
        """List model services visible through the current Business Case grants."""
        return [Deployment.from_api(item) for item in self._request("GET", "/serving/deployments")]

    def list_model_serving_usage(self, logical_model_id: str) -> list[ModelServingUsage]:
        """List active service assignments for every version in a model family."""
        path = f"/serving/model-families/{quote(logical_model_id, safe='')}/usage"
        return [ModelServingUsage.from_api(item) for item in self._request("GET", path)]

    def create_deployment(
        self,
        *,
        name: str,
        model_id: str | None = None,
        model_name: str | None = None,
        retention_days: int = 365,
    ) -> Deployment:
        """Create a service with one production model as its initial champion."""
        resolved_model_id = model_id or self._production_model_by_name(model_name or "")["id"]
        payload = self._request("POST", "/serving/deployments", json={
            "name": name,
            "model_id": resolved_model_id,
            "retention_days": retention_days,
        })
        return Deployment.from_api(payload)

    def revise_deployment(
        self,
        deployment: str | Deployment,
        *,
        champion: str,
        challengers: tuple[str, ...] | list[str] = (),
        shadows: tuple[str, ...] | list[str] = (),
        fallback: str | None = None,
        reason: str,
    ) -> Mapping[str, Any]:
        """Atomically activate an immutable role assignment revision."""
        target = self._deployment(deployment)
        assignments = [{"model_id": champion, "role": "champion"}]
        assignments.extend({"model_id": item, "role": "challenger"} for item in challengers)
        assignments.extend({"model_id": item, "role": "shadow"} for item in shadows)
        if fallback:
            assignments.append({"model_id": fallback, "role": "fallback"})
        return self._request(
            "POST",
            f"/serving/deployments/{target.id}/revisions",
            json={"assignments": assignments, "reason": reason},
        )

    def deployment_revisions(
        self,
        deployment: str | Deployment,
    ) -> list[Mapping[str, Any]]:
        """List immutable service revisions from newest to oldest."""
        target = self._deployment(deployment)
        return self._request("GET", f"/serving/deployments/{target.id}/revisions")

    def rollback_deployment(
        self,
        deployment: str | Deployment,
        *,
        revision_id: str,
        reason: str,
    ) -> Mapping[str, Any]:
        """Activate a new revision copied from a selected historical revision."""
        if not reason.strip():
            raise ValueError("Rollback reason is required")
        target = self._deployment(deployment)
        return self._request(
            "POST",
            f"/serving/deployments/{target.id}/revisions/{revision_id}/rollback",
            json={"reason": reason},
        )

    def set_deployment_status(
        self,
        deployment: str | Deployment,
        *,
        status: str,
        reason: str,
    ) -> Deployment:
        """Start or stop a model service without deleting its revision history."""
        if status not in {"running", "stopped"}:
            raise ValueError("status must be running or stopped")
        if not reason.strip():
            raise ValueError("Deployment status change reason is required")
        target = self._deployment(deployment)
        return Deployment.from_api(self._request(
            "POST",
            f"/serving/deployments/{target.id}/status",
            json={"status": status, "reason": reason},
        ))

    def predict(
        self,
        deployment: str | Deployment,
        *,
        features: Mapping[str, Any] | None = None,
        record_id: str | None = None,
        instances: list[Mapping[str, Any]] | None = None,
        challenger_model_id: str | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> PredictionResult:
        """Score one simple feature mapping or up to 1,000 explicit instances."""
        target = self._deployment(deployment)
        if (features is None) == (instances is None):
            raise ValueError("Provide either features for one record or instances for a batch")
        normalized = (
            [{"record_id": record_id, "features": dict(features or {})}]
            if features is not None
            else [self._prediction_instance(item) for item in instances or []]
        )
        if not normalized or len(normalized) > 1000:
            raise ValueError("Prediction batch must contain between 1 and 1,000 instances")
        path = f"/serving/deployments/{target.id}/predictions"
        if challenger_model_id:
            path = f"/serving/deployments/{target.id}/challengers/{challenger_model_id}/predictions"
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return PredictionResult.from_api(
            self._request("POST", path, json={"instances": normalized}, headers=headers)
        )

    def inference_history(
        self,
        deployment: str | Deployment,
        *,
        limit: int = 50,
        cursor: str | None = None,
        record_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Read one bounded page from the deployment's full inference log."""
        if limit < 1 or limit > 200:
            raise ValueError("History limit must be between 1 and 200")
        target = self._deployment(deployment)
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if record_id:
            params["record_id"] = record_id
        return self._request("GET", f"/serving/deployments/{target.id}/inference-log", params=params)

    def inference_request(
        self,
        deployment: str | Deployment,
        request_id: str,
    ) -> Mapping[str, Any]:
        """Read full champion/fallback/shadow executions for one audited request."""
        target = self._deployment(deployment)
        return self._request(
            "GET", f"/serving/deployments/{target.id}/inference-log/{request_id}"
        )

    def replay_challenger(
        self,
        deployment: str | Deployment,
        *,
        challenger_model_id: str,
        since: str | None = None,
        until: str | None = None,
        max_requests: int = 1000,
    ) -> Mapping[str, Any]:
        """Queue a pinned, asynchronous challenger replay over champion history."""
        target = self._deployment(deployment)
        return self._request(
            "POST",
            f"/serving/deployments/{target.id}/challenger-replays",
            json={
                "challenger_model_id": challenger_model_id,
                "since": since,
                "until": until,
                "max_requests": max_requests,
            },
        )

    def list_challenger_replays(self, deployment: str | Deployment) -> list[Mapping[str, Any]]:
        target = self._deployment(deployment)
        return self._request("GET", f"/serving/deployments/{target.id}/challenger-replays")

    def _deployment(self, value: str | Deployment) -> Deployment:
        if isinstance(value, Deployment):
            return value
        deployments = self.list_deployments()
        normalized = value.strip().casefold()
        matches = [
            item for item in deployments
            if value == item.id or normalized in {item.slug.casefold(), item.name.strip().casefold()}
        ]
        if not matches:
            raise ResourceNotFoundError(f"Deployment {value!r} was not found")
        if len(matches) > 1:
            raise ResourceAmbiguousError(f"Deployment {value!r} is ambiguous")
        return matches[0]

    def _production_model_by_name(self, name: str) -> Mapping[str, Any]:
        if not name.strip():
            raise ValueError("Provide model_id or model_name")
        normalized = name.strip().casefold()
        candidates = [
            item for item in self._request("GET", "/models")
            if str(item.get("name") or "").strip().casefold() == normalized
            and item.get("stage") == "production"
        ]
        if not candidates:
            raise ResourceNotFoundError(f"Production model named {name!r} was not found")
        return max(candidates, key=lambda item: int(item.get("version_number") or 0))

    @staticmethod
    def _prediction_instance(value: Mapping[str, Any]) -> dict[str, Any]:
        if "features" in value:
            return {"record_id": value.get("record_id"), "features": dict(value["features"])}
        return {"record_id": value.get("record_id"), "features": {
            key: item for key, item in value.items() if key != "record_id"
        }}

    def _business_case_by_name(self, name: str) -> Mapping[str, Any]:
        return _one_named(self._request("GET", "/business-cases"), name, "Business Case")

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
    def _raise_for_status(response: _Response, method: str, path: str) -> None:
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
            else ConflictError if response.status_code == 409
            else ApiError
        )
        raise error(f"{method} {path} returned HTTP {response.status_code}: {detail}")
