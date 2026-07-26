"""Small, stable Python interface to ML App's integration API.

The client streams dataset files from disk and keeps API responses bounded. It
intentionally exposes only supported integration operations instead of mirroring
every backend endpoint.
"""

from __future__ import annotations

import mimetypes
import os
import time
from getpass import getpass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote

import requests

from .errors import (
    ApiError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ResourceAmbiguousError,
    ResourceNotFoundError,
)
from .models import (
    CatalogPage,
    Dataset,
    Deployment,
    ModelServingUsage,
    OnlineMonitoringRun,
    PipelineRun,
    PredictionResult,
)
from .resolution import (
    _friendly_name_key,
    _model_stage,
    _named_candidates,
    _one_named,
)
from .serving import ServingClientMixin


class _Response(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...

    def iter_content(self, chunk_size: int) -> Any: ...


class _Session(Protocol):
    headers: dict[str, str]

    def request(self, method: str, url: str, **kwargs: Any) -> _Response: ...

    def close(self) -> None: ...


class MLAppClient(ServingClientMixin):
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
        """List complete dataset metadata visible to the authenticated user."""
        return self._request("GET", "/datasets")

    def page_datasets(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        business_case_id: str = "",
        asset_kind: str = "",
        include_deleted: bool = False,
        families: bool = True,
    ) -> CatalogPage[Dataset]:
        """Search a bounded data catalog and return the exact filtered total."""
        payload = self._request("GET", "/datasets/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "business_case_id": business_case_id,
            "asset_kind": asset_kind,
            "include_deleted": str(include_deleted).lower(),
            "families": str(families).lower(),
            "summary": "true",
        })
        return CatalogPage.from_api(payload, Dataset.from_api)

    def list_dataset_summaries(self) -> list[Mapping[str, Any]]:
        """List catalog metadata without large, non-presented metadata extensions."""
        return self._request("GET", "/datasets", params={"summary": True})

    def page_dataset_versions(
        self,
        logical_dataset_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> CatalogPage[Dataset]:
        """Browse one immutable dataset family without downloading all versions."""
        payload = self._request(
            "GET",
            f"/datasets/{quote(logical_dataset_id, safe='')}/versions/page",
            params={"limit": limit, "offset": offset},
        )
        return CatalogPage.from_api(payload, Dataset.from_api)

    def dataset_by_name(
        self,
        *,
        business_case_name: str,
        dataset_name: str,
    ) -> Dataset:
        """Resolve the newest version of one dataset family attached to a BC."""
        business_case = self._business_case_by_name(business_case_name)
        attachments = self.list_business_case_attachments(str(business_case["id"]))
        datasets = self.list_datasets()
        by_id = {str(item["id"]): item for item in datasets}
        attached_matches = [
            by_id[str(attachment["data_asset_id"])]
            for attachment in attachments
            if str(attachment.get("data_asset_id") or "") in by_id
            and by_id[str(attachment["data_asset_id"])].get("name") == dataset_name
        ]
        if not attached_matches:
            raise ResourceNotFoundError(
                f"Dataset attached to Business Case named {dataset_name!r} was not found"
            )
        logical_ids = {str(item["logical_id"]) for item in attached_matches}
        if len(logical_ids) != 1:
            raise ResourceAmbiguousError(
                f"Dataset attached to Business Case name {dataset_name!r} is ambiguous "
                f"({len(logical_ids)} families)"
            )
        logical_id = next(iter(logical_ids))
        family = [item for item in datasets if str(item.get("logical_id")) == logical_id]
        newest = max(family, key=lambda item: int(item.get("version_number") or 0))
        return Dataset.from_api(newest)

    def ensure_dataset(
        self,
        file_path: str | Path,
        *,
        business_case_name: str,
        dataset_name: str,
        role: str,
        description: str = "",
        tags: tuple[str, ...] | list[str] = (),
        context_note: str = "",
        primary_key_column: str = "",
        target_column: str = "",
    ) -> tuple[Dataset, bool]:
        """Reuse an attached dataset family or upload and attach its first version.

        This operation is intentionally conservative: a matching attached family is
        reused and never receives an implicit new immutable version.
        """
        try:
            return self.dataset_by_name(
                business_case_name=business_case_name,
                dataset_name=dataset_name,
            ), False
        except ResourceNotFoundError:
            pass
        business_case = self._business_case_by_name(business_case_name)
        dataset = self.upload_dataset(
            file_path,
            name=dataset_name,
            description=description,
            tags=tags,
        )
        self.attach_dataset(
            str(business_case["id"]),
            dataset.id,
            role=role,
            context_note=context_note,
            primary_key_column=primary_key_column,
            target_column=target_column,
        )
        return dataset, True

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

    def page_business_cases(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        manageable_only: bool = False,
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search visible Business Cases without loading the full catalog."""
        payload = self._request("GET", "/business-cases/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "manageable_only": str(manageable_only).lower(),
        })
        return CatalogPage.from_api(payload, lambda item: item)

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

    def page_business_case_attachments(
        self,
        business_case_id: str,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        role: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        deleted_only: bool = False,
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search mapped BC data with lightweight latest-version metadata."""
        payload = self._request(
            "GET",
            f"/business-cases/{business_case_id}/data-attachments/page",
            params={
                "limit": limit,
                "offset": offset,
                "search": search,
                "role": role,
                "pipeline_id": pipeline_id,
                "pipeline_type": pipeline_type,
                "uploaded_only": str(uploaded_only).lower(),
                "deleted_only": str(deleted_only).lower(),
            },
        )
        return CatalogPage.from_api(payload, lambda item: item)

    def list_pipelines(self, business_case_id: str) -> list[Mapping[str, Any]]:
        return self._request(
            "GET", "/pipelines", params={"business_case_id": business_case_id}
        )

    def page_pipeline_versions(
        self,
        pipeline_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str = "",
    ) -> CatalogPage[Mapping[str, Any]]:
        """Read a bounded immutable version history for one pipeline."""
        payload = self._request(
            "GET",
            f"/pipelines/{pipeline_id}/versions/page",
            params={
                "limit": limit,
                "offset": offset,
                "status": status,
            },
        )
        return CatalogPage.from_api(payload, lambda item: item)

    def page_pipelines(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        business_case_id: str = "",
        pipeline_type: str = "",
        status: str = "",
        include_deprecated: bool = True,
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search workflow definitions without loading every pipeline."""
        payload = self._request("GET", "/pipelines/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "business_case_id": business_case_id,
            "pipeline_type": pipeline_type,
            "status": status,
            "include_deprecated": str(include_deprecated).lower(),
        })
        return CatalogPage.from_api(payload, lambda item: item)

    def pipeline_by_name(
        self,
        *,
        business_case_name: str,
        pipeline_name: str,
    ) -> Mapping[str, Any]:
        """Resolve one pipeline by its Business Case and user-facing name."""
        business_case = self._business_case_by_name(business_case_name)
        return _one_named(
            self.list_pipelines(str(business_case["id"])),
            pipeline_name,
            "Pipeline in Business Case",
        )

    def list_pipeline_versions(self, pipeline_id: str) -> list[Mapping[str, Any]]:
        return self._request("GET", f"/pipelines/{pipeline_id}/versions")

    def latest_published_pipeline_version(
        self, pipeline_id: str
    ) -> Mapping[str, Any]:
        """Return the newest immutable published version of a pipeline."""
        published = [
            item for item in self.list_pipeline_versions(pipeline_id)
            if item.get("status") == "published"
        ]
        if not published:
            raise ResourceNotFoundError(
                f"Pipeline {pipeline_id!r} has no published version"
            )
        return max(published, key=lambda item: int(item["version_number"]))

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

    def ensure_pipeline(
        self,
        *,
        business_case_name: str,
        name: str,
        definition: Mapping[str, Any],
        pipeline_type: str = "custom",
        description: str = "",
    ) -> tuple[Mapping[str, Any], Mapping[str, Any], bool]:
        """Reuse a published named pipeline or create and publish it once."""
        business_case = self._business_case_by_name(business_case_name)
        pipelines = self.list_pipelines(str(business_case["id"]))
        matches = [item for item in pipelines if item.get("name") == name]
        if len(matches) > 1:
            raise ResourceAmbiguousError(
                f"Pipeline in Business Case name {name!r} is ambiguous ({len(matches)} matches)"
            )
        if matches:
            pipeline = matches[0]
            if str(pipeline.get("status") or "draft") not in {"draft", "published"}:
                raise ConflictError(
                    f"Pipeline {name!r} exists with status {pipeline.get('status')!r}; "
                    "use a new versioned example name"
                )
            try:
                version = self.latest_published_pipeline_version(str(pipeline["id"]))
            except ResourceNotFoundError:
                version = self.publish_pipeline_draft(str(pipeline["id"]))
            return pipeline, version, False
        pipeline = self.create_pipeline(
            business_case_id=str(business_case["id"]),
            name=name,
            definition=definition,
            pipeline_type=pipeline_type,
            description=description,
        )
        version = self.publish_pipeline_draft(str(pipeline["id"]))
        return pipeline, version, True

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

    def list_scoring_report_summaries(
        self,
        *,
        business_case_id: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """List scoring report catalog fields without full evaluation payloads."""
        params: dict[str, Any] = {"summary": True}
        if business_case_id is not None:
            params["business_case_id"] = business_case_id
        return self._request("GET", "/scoring-reports", params=params)

    def page_scoring_reports(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        business_case_id: str = "",
        problem_type: str = "",
        pipeline_id: str = "",
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search immutable report families using the same bounded API as the UI."""
        payload = self._request("GET", "/scoring-reports/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "business_case_id": business_case_id,
            "problem_type": problem_type,
            "pipeline_id": pipeline_id,
        })
        return CatalogPage.from_api(payload, lambda item: item)

    def get_scoring_report(self, report_id: str) -> Mapping[str, Any]:
        """Fetch one complete immutable scoring report."""
        return self._request("GET", f"/scoring-reports/{report_id}")

    def page_scoring_report_versions(
        self,
        logical_report_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> CatalogPage[Mapping[str, Any]]:
        """Browse summary metadata for one immutable scoring-report family."""
        payload = self._request(
            "GET",
            f"/scoring-reports/{quote(logical_report_id, safe='')}/versions/page",
            params={"limit": limit, "offset": offset, "summary": "true"},
        )
        return CatalogPage.from_api(payload, lambda item: item)

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

    def list_pipeline_runs(self, pipeline_id: str) -> list[PipelineRun]:
        """List bounded run metadata for one readable pipeline."""
        return [
            PipelineRun.from_api(item)
            for item in self._request("GET", f"/pipelines/{pipeline_id}/runs")
        ]

    def page_pipeline_runs(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        pipeline_id: str = "",
        pipeline_version_id: str = "",
        business_case_id: str = "",
        status: str = "",
    ) -> CatalogPage[PipelineRun]:
        """Search the cross-pipeline run history without loading every run."""
        payload = self._request("GET", "/pipelines/runs/history/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "pipeline_id": pipeline_id,
            "pipeline_version_id": pipeline_version_id,
            "business_case_id": business_case_id,
            "status": status,
        })
        return CatalogPage.from_api(payload, PipelineRun.from_api)

    def pipeline_run_by_operation_key(
        self,
        *,
        business_case_name: str,
        pipeline_name: str,
        operation_key: str,
        status: str = "succeeded",
    ) -> PipelineRun:
        """Resolve a prior named client operation, normally a successful run."""
        pipeline = self.pipeline_by_name(
            business_case_name=business_case_name,
            pipeline_name=pipeline_name,
        )
        matches = [
            run for run in self.list_pipeline_runs(str(pipeline["id"]))
            if (run.raw.get("runtime_parameters") or {}).get("client_operation_key")
            == operation_key
            and run.status == status
            and not bool(run.raw.get("is_dry_run"))
        ]
        if not matches:
            raise ResourceNotFoundError(
                f"Pipeline {pipeline_name!r} has no {status!r} run for operation "
                f"{operation_key!r}; run the preceding example notebook first"
            )
        return matches[0]

    def ensure_pipeline_run_by_name(
        self,
        *,
        business_case_name: str,
        pipeline_name: str,
        operation_key: str,
        runtime_parameters: Mapping[str, Any] | None = None,
        input_versions: Mapping[str, str] | None = None,
        model_versions: Mapping[str, str] | None = None,
    ) -> tuple[PipelineRun, bool]:
        """Reuse a matching successful/active run or start the operation once.

        ``operation_key`` is stored in run metadata. It makes sequential notebook
        reruns convergent while retaining failed attempts for audit and diagnosis.
        """
        normalized_key = operation_key.strip()
        if not normalized_key:
            raise ValueError("operation_key is required")
        pipeline = self.pipeline_by_name(
            business_case_name=business_case_name,
            pipeline_name=pipeline_name,
        )
        version = self.latest_published_pipeline_version(str(pipeline["id"]))
        matches = [
            run for run in self.list_pipeline_runs(str(pipeline["id"]))
            if run.pipeline_version_id == str(version["id"])
            and (run.raw.get("runtime_parameters") or {}).get("client_operation_key")
            == normalized_key
            and not bool(run.raw.get("is_dry_run"))
        ]
        succeeded = [run for run in matches if run.status == "succeeded"]
        if succeeded:
            return succeeded[0], False
        active = [run for run in matches if not run.finished]
        if active:
            return active[0], False
        parameters = dict(runtime_parameters or {})
        existing_key = parameters.get("client_operation_key")
        if existing_key not in {None, normalized_key}:
            raise ValueError("runtime_parameters.client_operation_key conflicts with operation_key")
        parameters["client_operation_key"] = normalized_key
        run = self.run_pipeline(
            str(pipeline["id"]),
            pipeline_version_id=str(version["id"]),
            runtime_parameters=parameters,
            input_versions=input_versions,
            model_versions=model_versions,
        )
        return run, True

    def get_pipeline_run(self, pipeline_id: str, run_id: str) -> PipelineRun:
        return PipelineRun.from_api(
            self._request("GET", f"/pipelines/{pipeline_id}/runs/{run_id}")
        )

    def get_pipeline_run_status(self, pipeline_id: str, run_id: str) -> PipelineRun:
        """Fetch progress fields without downloading run events and manifests."""
        return PipelineRun.from_api(
            self._request("GET", f"/pipelines/{pipeline_id}/runs/{run_id}/status")
        )

    def wait_for_pipeline_run(
        self,
        run: PipelineRun,
        *,
        poll_interval: float = 2.0,
        timeout: float | None = None,
        on_update: Callable[[PipelineRun], None] | None = None,
    ) -> PipelineRun:
        """Poll compact progress to completion and fetch the full final run once."""
        started = time.monotonic()
        current = run
        polled = False
        while not current.finished:
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"Pipeline run {run.id} did not finish within {timeout}s")
            time.sleep(poll_interval)
            current = self.get_pipeline_run_status(run.pipeline_id, run.id)
            polled = True
            if on_update is not None:
                on_update(current)
        if polled:
            current = self.get_pipeline_run(run.pipeline_id, run.id)
        if current.status != "succeeded":
            detail = current.error_message or "no error detail returned"
            raise ApiError(f"Pipeline run {current.id} ended as {current.status}: {detail}")
        return current

    def list_models(self) -> list[Mapping[str, Any]]:
        """List model versions visible through the current Business Case grants."""
        return self._request("GET", "/models")

    def list_model_summaries(self) -> list[Mapping[str, Any]]:
        """List model registry/workflow fields without experiment-heavy payloads."""
        return self._request("GET", "/models", params={"summary": True})

    def page_models(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        business_case_id: str = "",
        stage: str = "",
        pipeline_id: str = "",
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search latest model families and retain their server-side version counts."""
        payload = self._request("GET", "/models/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "business_case_id": business_case_id,
            "stage": stage,
            "pipeline_id": pipeline_id,
        })
        return CatalogPage.from_api(payload, lambda item: item)

    def model_by_name(
        self,
        *,
        business_case_name: str,
        model_name: str,
        version: str | int | None = None,
    ) -> Mapping[str, Any]:
        """Resolve an immutable model version by its user-facing coordinates.

        The newest visible version is returned when ``version`` is omitted. Pass
        ``version="v3"`` or ``version=3`` when a workflow must pin an older
        version explicitly.
        """
        business_case = self.business_case_by_name(business_case_name)
        candidates = [
            item for item in self.list_models()
            if str(item.get("business_case_id") or "") == str(business_case["id"])
        ]
        matches = _named_candidates(candidates, model_name)
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
            raise ResourceNotFoundError(
                f"Model {model_name!r}{suffix} was not found in Business Case "
                f"{business_case_name!r}"
            )
        logical_ids = {
            str(item.get("logical_id") or item.get("id") or "") for item in matches
        }
        if len(logical_ids) > 1:
            choices = ", ".join(
                f"{item.get('name')} {item.get('version')} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model_name!r} is ambiguous in Business Case "
                f"{business_case_name!r}; candidates: {choices}"
            )
        return max(matches, key=lambda item: int(item.get("version_number") or 0))

    def model_for_pipeline_run(self, run: str | PipelineRun) -> Mapping[str, Any]:
        """Resolve the single immutable model artifact created by a pipeline run."""
        run_id = run.id if isinstance(run, PipelineRun) else run
        matches = [
            item for item in self.list_models()
            if str(item.get("pipeline_run_id") or "") == run_id
        ]
        if not matches:
            raise ResourceNotFoundError(
                f"Pipeline run {run_id!r} did not create a visible model artifact"
            )
        if len(matches) > 1:
            raise ResourceAmbiguousError(
                f"Pipeline run {run_id!r} created {len(matches)} model artifacts"
            )
        return matches[0]

    def list_model_versions(self, logical_model_id: str) -> list[Mapping[str, Any]]:
        """List the complete version history of one logical model family."""
        path = f"/models/{quote(logical_model_id, safe='')}/versions"
        return self._request("GET", path)

    def page_model_versions(
        self,
        logical_model_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> CatalogPage[Mapping[str, Any]]:
        """Browse one logical model family with a bounded response."""
        payload = self._request(
            "GET",
            f"/models/{quote(logical_model_id, safe='')}/versions/page",
            params={"limit": limit, "offset": offset},
        )
        return CatalogPage.from_api(payload, lambda item: item)

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
        stage = _model_stage(stage)
        models = self.list_models()
        id_matches = [item for item in models if str(item.get("id") or "") == model]
        matches = id_matches or _named_candidates(models, model)
        if not matches:
            suffix = "" if version is None else f" version {version!r}"
            raise ResourceNotFoundError(f"Model {model!r}{suffix} was not found")

        matching_families = {
            str(item.get("logical_id") or _friendly_name_key(str(item.get("name") or "")))
            for item in matches
        }
        if len(matching_families) > 1:
            candidates = ", ".join(
                f"{item.get('name')} {item.get('version') or 'v' + str(item.get('version_number'))} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model!r} is ambiguous; use an exact model ID. Candidates: {candidates}"
            )

        logical_ids = {
            str(item["logical_id"])
            for item in matches
            if item.get("logical_id")
        }
        if not id_matches and len(logical_ids) == 1:
            matches = self.list_model_versions(next(iter(logical_ids)))
        available_versions = matches
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
            available_versions = (
                self.list_model_versions(next(iter(logical_ids)))
                if id_matches and len(logical_ids) == 1
                else available_versions
            )
            if available_versions:
                available = ", ".join(sorted({
                    str(item.get("version") or f"v{item.get('version_number')}")
                    for item in available_versions
                }))
                raise ResourceNotFoundError(
                    f"Model {model!r}{suffix} was not found; available versions: {available}"
                )
            raise ResourceNotFoundError(f"Model {model!r}{suffix} was not found")
        if version is not None and len(matches) > 1:
            candidates = ", ".join(
                f"{item.get('name')} {item.get('version') or 'v' + str(item.get('version_number'))} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model!r} is ambiguous; use an exact model ID. Candidates: {candidates}"
            )
        selected = max(matches, key=lambda item: int(item.get("version_number") or 0))
        return self._request(
            "PATCH",
            f"/models/{selected['id']}/stage",
            json={"stage": stage},
        )

    def promote_model_versions(
        self,
        model: str,
        stage: str,
        *,
        versions: list[str | int] | tuple[str | int, ...],
    ) -> list[Mapping[str, Any]]:
        """Change several versions in one family without repeatedly resolving it.

        Every version still uses the standard audited stage-change endpoint. The
        optimization only removes redundant registry and family-history reads.
        Results preserve the order supplied in ``versions``.
        """
        stage = _model_stage(stage)
        requested = list(versions)
        if not requested:
            raise ValueError("versions must contain at least one model version")

        models = self.list_models()
        id_matches = [item for item in models if str(item.get("id") or "") == model]
        matches = id_matches or _named_candidates(models, model)
        if not matches:
            raise ResourceNotFoundError(f"Model {model!r} was not found")
        family_ids = {
            str(item.get("logical_id") or _friendly_name_key(str(item.get("name") or "")))
            for item in matches
        }
        if len(family_ids) > 1:
            candidates = ", ".join(
                f"{item.get('name')} {item.get('version') or 'v' + str(item.get('version_number'))} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model!r} is ambiguous; use an exact model ID. Candidates: {candidates}"
            )

        logical_ids = {str(item["logical_id"]) for item in matches if item.get("logical_id")}
        family = (
            self.list_model_versions(next(iter(logical_ids)))
            if len(logical_ids) == 1
            else matches
        )
        by_version: dict[str, list[Mapping[str, Any]]] = {}
        for item in family:
            labels = {
                str(item.get("version") or "").strip().casefold(),
                str(item.get("version_number") or "").strip().casefold(),
            }
            for label in labels:
                if label:
                    by_version.setdefault(label, []).append(item)
                    if label.isdigit():
                        by_version.setdefault(f"v{label}", []).append(item)

        selected: list[Mapping[str, Any]] = []
        missing: list[str] = []
        for version in requested:
            normalized = str(version).strip().casefold()
            if normalized.isdigit():
                normalized = f"v{normalized}"
            candidates = {
                str(item.get("id")): item for item in by_version.get(normalized, [])
            }
            if not candidates:
                missing.append(str(version))
                continue
            if len(candidates) > 1:
                raise ResourceAmbiguousError(
                    f"Model {model!r} version {version!r} is ambiguous; use exact model IDs"
                )
            selected.append(next(iter(candidates.values())))
        if missing:
            available = ", ".join(
                str(item.get("version") or f"v{item.get('version_number')}")
                for item in family
            )
            raise ResourceNotFoundError(
                f"Model {model!r} versions {', '.join(missing)} were not found; "
                f"available versions: {available}"
            )

        return [
            self._request(
                "PATCH",
                f"/models/{item['id']}/stage",
                json={"stage": stage},
            )
            for item in selected
        ]

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
