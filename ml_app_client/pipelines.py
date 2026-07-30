"""Pipeline definition, publication, execution, and polling workflows."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from .errors import (
    ApiError,
    ConflictError,
    ResourceNotFoundError,
)
from .models import CatalogPage, PipelineRun
from .pagination import iter_offset_items
from .resolution import _one_named
from .transport import TransportClientMixin


class PipelineClientMixin(TransportClientMixin):
    """Pipeline operations composed into :class:`MLAppClient`."""

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
        return self._pipeline_by_name_in_case(
            str(business_case["id"]),
            pipeline_name,
        )

    def list_pipeline_versions(self, pipeline_id: str) -> list[Mapping[str, Any]]:
        return self._request("GET", f"/pipelines/{pipeline_id}/versions")

    def latest_published_pipeline_version(
        self, pipeline_id: str
    ) -> Mapping[str, Any]:
        """Return the newest immutable published version of a pipeline."""
        page = self.page_pipeline_versions(
            pipeline_id,
            limit=1,
            status="published",
        )
        if not page.items:
            raise ResourceNotFoundError(
                f"Pipeline {pipeline_id!r} has no published version"
            )
        return page.items[0]

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
        try:
            pipeline = self._pipeline_by_name_in_case(
                str(business_case["id"]),
                name,
            )
        except ResourceNotFoundError:
            pipeline = None
        if pipeline is not None:
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
        pipeline = self.pipeline_by_name(
            business_case_name=business_case_name,
            pipeline_name=pipeline_name,
        )
        version = self.latest_published_pipeline_version(str(pipeline["id"]))
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

    def _pipeline_by_name_in_case(
        self,
        business_case_id: str,
        pipeline_name: str,
    ) -> Mapping[str, Any]:
        candidates = list(iter_offset_items(
            lambda limit, offset: self.page_pipelines(
                limit=limit,
                offset=offset,
                search=pipeline_name,
                business_case_id=business_case_id,
            )
        ))
        return _one_named(
            candidates,
            pipeline_name,
            "Pipeline in Business Case",
        )
