"""High-level online-serving and monitoring workflows."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

from .errors import ResourceAmbiguousError, ResourceNotFoundError
from .models import CatalogPage, Dataset, Deployment, ModelServingUsage, OnlineMonitoringRun, PredictionResult
from .resolution import _exact_name_key, _friendly_name_key, _named_candidates


class ServingClientMixin:
    """Serving operations composed into :class:`MLAppClient`."""

    def list_deployments(self, *, include_archived: bool = False) -> list[Deployment]:
        """List visible model services, excluding archived services by default."""
        params = {"include_archived": "true"} if include_archived else None
        return [Deployment.from_api(item) for item in self._request("GET", "/serving/deployments", params=params)]

    def page_deployments(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        status: str = "",
        business_case_id: str = "",
        include_archived: bool = False,
    ) -> CatalogPage[Deployment]:
        """Search model services using a bounded, exact-count catalog page."""
        payload = self._request("GET", "/serving/deployments/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "status": status,
            "business_case_id": business_case_id,
            "include_archived": str(include_archived).lower(),
        })
        return CatalogPage.from_api(payload, Deployment.from_api)

    def deployment_by_name(
        self,
        name: str,
        *,
        include_archived: bool = False,
    ) -> Deployment:
        """Resolve one model service by its exact user-facing name."""
        matches = [
            item for item in self.list_deployments(include_archived=include_archived)
            if item.name == name
        ]
        if not matches:
            raise ResourceNotFoundError(f"Deployment named {name!r} was not found")
        if len(matches) > 1:
            raise ResourceAmbiguousError(f"Deployment name {name!r} is ambiguous")
        return matches[0]

    def list_model_serving_usage(self, logical_model_id: str) -> list[ModelServingUsage]:
        """List active service assignments for every version in a model family."""
        path = f"/serving/model-families/{quote(logical_model_id, safe='')}/usage"
        return [ModelServingUsage.from_api(item) for item in self._request("GET", path)]

    def page_model_serving_usage(
        self,
        model_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> CatalogPage[ModelServingUsage]:
        """Browse active service assignments for one immutable model version."""
        payload = self._request(
            "GET",
            f"/serving/models/{quote(model_id, safe='')}/usage/page",
            params={"limit": limit, "offset": offset},
        )
        return CatalogPage.from_api(payload, ModelServingUsage.from_api)

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

    def ensure_deployment(
        self,
        *,
        name: str,
        model_id: str,
        retention_days: int = 365,
    ) -> tuple[Deployment, bool]:
        """Reuse a matching active service or create it with the model as champion."""
        try:
            deployment = self.deployment_by_name(name, include_archived=True)
        except ResourceNotFoundError:
            return self.create_deployment(
                name=name,
                model_id=model_id,
                retention_days=retention_days,
            ), True
        if deployment.status == "archived":
            raise ConflictError(
                f"Deployment {name!r} is archived and its governed history keeps the name reserved"
            )
        assignments = deployment.active_revision.get("assignments") or []
        champions = [
            item for item in assignments
            if isinstance(item, Mapping) and item.get("role") == "champion"
        ]
        if len(champions) != 1 or str(champions[0].get("model_id")) != model_id:
            raise ConflictError(
                f"Deployment {name!r} already exists with a different champion; "
                "create an explicit immutable revision instead"
            )
        if deployment.status == "stopped":
            deployment = self.set_deployment_status(
                deployment,
                status="running",
                reason="Resume idempotent example service",
            )
        return deployment, False

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
        """Start, stop or irreversibly archive a service while preserving its history."""
        if status not in {"running", "stopped", "archived"}:
            raise ValueError("status must be running, stopped or archived")
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

    def deployment_input_contract(
        self,
        deployment: str | Deployment,
        *,
        challenger_model_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Return the model-derived input contract used by the endpoint form."""
        target = self._deployment(deployment)
        params = (
            {"challenger_model_id": challenger_model_id}
            if challenger_model_id
            else None
        )
        return self._request(
            "GET",
            f"/serving/deployments/{target.id}/input-contract",
            params=params,
        )

    def deployment_model_options(
        self,
        deployment: str | Deployment,
    ) -> list[Mapping[str, Any]]:
        """List role eligibility and inference-contract compatibility for a service."""
        target = self._deployment(deployment)
        return self._request(
            "GET", f"/serving/deployments/{target.id}/model-options"
        )

    def page_deployment_model_options(
        self,
        deployment: str | Deployment,
        *,
        limit: int = 20,
        offset: int = 0,
        search: str = "",
        model_ids: Sequence[str] = (),
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search deployable role options without loading every model bundle."""
        target = self._deployment(deployment)
        payload = self._request(
            "GET",
            f"/serving/deployments/{target.id}/model-options/page",
            params={
                "limit": limit,
                "offset": offset,
                "search": search,
                "model_id": list(model_ids),
            },
        )
        return CatalogPage.from_api(payload, lambda item: item)

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

    def inference_history_summary(
        self,
        deployment: str | Deployment,
        *,
        limit: int = 50,
        cursor: str | None = None,
        record_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Read a bounded history page without retained request/response payloads."""
        if limit < 1 or limit > 200:
            raise ValueError("History limit must be between 1 and 200")
        target = self._deployment(deployment)
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if record_id:
            params["record_id"] = record_id
        return self._request(
            "GET",
            f"/serving/deployments/{target.id}/inference-log-summary",
            params=params,
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

    def run_deployment_monitoring(
        self,
        deployment: str | Deployment,
        *,
        actuals: str | Dataset | None = None,
        since: str | datetime | None = None,
        until: str | datetime | None = None,
        actuals_target_column: str | None = None,
        actuals_prediction_id_column: str | None = None,
        actuals_request_id_column: str | None = None,
        actuals_record_id_column: str | None = None,
        join_strategy: str = "auto",
        aggregation_granularity: str = "none",
    ) -> OnlineMonitoringRun:
        """Queue a full-scope online report; actuals optionally add performance metrics."""
        if join_strategy not in {"auto", "prediction_id", "request_record_id", "record_id"}:
            raise ValueError(
                "join_strategy must be auto, prediction_id, request_record_id or record_id"
            )
        if aggregation_granularity not in {"none", "hour", "day", "week", "month"}:
            raise ValueError("aggregation_granularity must be none, hour, day, week or month")
        target = self._deployment(deployment)
        actuals_dataset = self._deployment_actuals(target, actuals) if actuals is not None else None
        until_value = until or datetime.now(timezone.utc)
        if since is None:
            parsed_until = (
                until_value
                if isinstance(until_value, datetime)
                else datetime.fromisoformat(until_value.replace("Z", "+00:00"))
            )
            if parsed_until.tzinfo is None:
                raise ValueError("Monitoring datetimes must include a timezone")
            since_value: str | datetime = parsed_until - timedelta(days=1)
        else:
            since_value = since
        payload: dict[str, Any] = {
            "since": self._datetime_value(since_value),
            "until": self._datetime_value(until_value),
            "aggregation_granularity": aggregation_granularity,
            "join": {"strategy": join_strategy},
        }
        if actuals_dataset is not None:
            payload["actuals_dataset_id"] = actuals_dataset.id
        if actuals_target_column:
            payload["actuals_target_column"] = actuals_target_column
        if actuals_prediction_id_column:
            payload["join"]["actuals_prediction_id_column"] = actuals_prediction_id_column
        if actuals_request_id_column:
            payload["join"]["actuals_request_id_column"] = actuals_request_id_column
        if actuals_record_id_column:
            payload["join"]["actuals_record_id_column"] = actuals_record_id_column
        value = self._request(
            "POST",
            f"/serving/deployments/{target.id}/monitoring-runs",
            json=payload,
        )
        return OnlineMonitoringRun.from_api(value)

    def list_online_monitoring_runs(
        self,
        deployment: str | Deployment | None = None,
        *,
        limit: int = 100,
        include_archived: bool = False,
    ) -> list[OnlineMonitoringRun]:
        """List bounded immutable report runs, optionally for one service."""
        if limit < 1 or limit > 200:
            raise ValueError("Monitoring run limit must be between 1 and 200")
        path = "/serving/monitoring-runs"
        if deployment is not None:
            target = self._deployment(deployment)
            path = f"/serving/deployments/{target.id}/monitoring-runs"
        values = self._request(
            "GET", path,
            params={"limit": limit, "include_archived": include_archived},
        )
        return [OnlineMonitoringRun.from_api(item) for item in values]

    def archive_online_monitoring_run(
        self,
        run: str | OnlineMonitoringRun,
        *,
        reason: str = "Archived from monitoring history",
    ) -> OnlineMonitoringRun:
        """Hide one finished run from default history without deleting its report or lineage."""
        run_id = run.id if isinstance(run, OnlineMonitoringRun) else run
        return OnlineMonitoringRun.from_api(self._request(
            "POST", f"/serving/monitoring-runs/{run_id}/archive",
            json={"reason": reason},
        ))

    def archive_deployment_monitoring_history(
        self,
        deployment: str | Deployment,
        *,
        reason: str = "Archived from monitoring history",
    ) -> int:
        """Archive every finished run for one service while preserving governed metadata."""
        target = self._deployment(deployment)
        value = self._request(
            "POST", f"/serving/deployments/{target.id}/monitoring-runs/archive",
            json={"reason": reason},
        )
        return int(value.get("archived_run_count") or 0)

    def get_online_monitoring_run(self, run_id: str) -> OnlineMonitoringRun:
        return OnlineMonitoringRun.from_api(
            self._request("GET", f"/serving/monitoring-runs/{run_id}")
        )

    def get_online_monitoring_bucket_evaluations(
        self,
        run: str | OnlineMonitoringRun,
        bucket_starts: Sequence[str],
    ) -> list[Mapping[str, Any]]:
        """Return bounded scoring diagnostics for up to eight selected time buckets."""
        selected = list(dict.fromkeys(bucket_starts))
        if len(selected) > 8:
            raise ValueError("Select at most 8 monitoring buckets")
        run_id = run.id if isinstance(run, OnlineMonitoringRun) else run
        return list(self._request(
            "GET",
            f"/serving/monitoring-runs/{run_id}/bucket-evaluations",
            params=[("bucket_start", value) for value in selected],
        ))

    def wait_for_online_monitoring_run(
        self,
        run: OnlineMonitoringRun,
        *,
        poll_interval: float = 2.0,
        timeout: float | None = None,
        on_update: Callable[[OnlineMonitoringRun], None] | None = None,
    ) -> OnlineMonitoringRun:
        """Poll an online monitoring run without downloading row-level snapshots."""
        started = time.monotonic()
        current = run
        while not current.finished:
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(
                    f"Online monitoring run {run.id} did not finish within {timeout}s"
                )
            time.sleep(poll_interval)
            current = self.get_online_monitoring_run(run.id)
            if on_update is not None:
                on_update(current)
        if current.status != "succeeded":
            raise ApiError(
                f"Online monitoring run {current.id} failed: "
                f"{current.error_message or 'no error detail returned'}"
            )
        return current

    def _deployment_actuals(
        self,
        deployment: Deployment,
        value: str | Dataset,
    ) -> Dataset:
        if isinstance(value, Dataset):
            return value
        visible = self.list_datasets()
        by_id = {str(item.get("id")): item for item in visible}
        if value in by_id:
            return Dataset.from_api(by_id[value])
        attachments = self.list_business_case_attachments(deployment.business_case_id)
        candidates = [
            by_id[str(item.get("data_asset_id"))]
            for item in attachments
            if item.get("role") == "monitoring_actuals"
            and str(item.get("data_asset_id")) in by_id
            and _exact_name_key(str(by_id[str(item.get("data_asset_id"))].get("name") or ""))
            == _exact_name_key(value)
        ]
        if not candidates:
            raise ResourceNotFoundError(
                f"Actuals dataset {value!r} attached with role monitoring_actuals was not found"
            )
        logical_ids = {str(item.get("logical_id") or "") for item in candidates}
        if len(logical_ids) != 1:
            raise ResourceAmbiguousError(
                f"Actuals dataset name {value!r} resolves to multiple dataset families"
            )
        family = [
            item for item in visible
            if str(item.get("logical_id") or "") == next(iter(logical_ids))
        ]
        return Dataset.from_api(max(family, key=lambda item: int(item.get("version_number") or 0)))

    @staticmethod
    def _datetime_value(value: str | datetime) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("Monitoring datetimes must include a timezone")
            return value.isoformat()
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Monitoring datetimes must include a timezone")
        return value

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
        models = self._request("GET", "/models")
        candidates = [
            item for item in _named_candidates(models, name)
            if item.get("stage") == "production"
        ]
        if not candidates:
            raise ResourceNotFoundError(f"Production model named {name!r} was not found")
        families = {
            str(item.get("logical_id") or _friendly_name_key(str(item.get("name") or "")))
            for item in candidates
        }
        if len(families) > 1:
            raise ResourceAmbiguousError(
                f"Production model {name!r} is ambiguous; provide model_id explicitly"
            )
        return max(candidates, key=lambda item: int(item.get("version_number") or 0))

    @staticmethod
    def _prediction_instance(value: Mapping[str, Any]) -> dict[str, Any]:
        if "features" in value:
            return {"record_id": value.get("record_id"), "features": dict(value["features"])}
        return {"record_id": value.get("record_id"), "features": {
            key: item for key, item in value.items() if key != "record_id"
        }}
