"""Manual online-service monitoring workflows."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

from .errors import ApiError, ResourceAmbiguousError, ResourceNotFoundError
from .models import Dataset, Deployment, OnlineMonitoringRun
from .pagination import iter_offset_items
from .resolution import _exact_name_key
from .transport import TransportClientMixin


class OnlineMonitoringClientMixin(TransportClientMixin):
    """Online monitoring operations composed into :class:`MLAppClient`."""

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
        if join_strategy not in {
            "auto",
            "prediction_id",
            "request_record_id",
            "record_id",
        }:
            raise ValueError(
                "join_strategy must be auto, prediction_id, request_record_id or record_id"
            )
        if aggregation_granularity not in {"none", "hour", "day", "week", "month"}:
            raise ValueError(
                "aggregation_granularity must be none, hour, day, week or month"
            )
        target = self._deployment(deployment)
        actuals_dataset = (
            self._deployment_actuals(target, actuals)
            if actuals is not None
            else None
        )
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
            payload["join"]["actuals_prediction_id_column"] = (
                actuals_prediction_id_column
            )
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
            "GET",
            path,
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
            "POST",
            f"/serving/monitoring-runs/{run_id}/archive",
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
            "POST",
            f"/serving/deployments/{target.id}/monitoring-runs/archive",
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
        try:
            return Dataset.from_api(self._request(
                "GET",
                f"/datasets/{quote(value, safe='')}",
            ))
        except ResourceNotFoundError:
            pass
        candidates = [
            attachment
            for attachment in iter_offset_items(
                lambda limit, offset: self.page_business_case_attachments(
                    deployment.business_case_id,
                    limit=limit,
                    offset=offset,
                    search=value,
                    role="monitoring_actuals",
                )
            )
            if _exact_name_key(str(attachment.get("data_asset_name") or ""))
            == _exact_name_key(value)
        ]
        if not candidates:
            raise ResourceNotFoundError(
                f"Actuals dataset {value!r} attached with role monitoring_actuals "
                "was not found"
            )
        logical_ids = {
            str(item.get("data_asset_logical_id") or "")
            for item in candidates
        }
        logical_ids.discard("")
        if len(logical_ids) != 1:
            raise ResourceAmbiguousError(
                f"Actuals dataset name {value!r} resolves to multiple dataset families"
            )
        latest = self.page_dataset_versions(
            next(iter(logical_ids)),
            limit=1,
        )
        if not latest.items:
            raise ResourceNotFoundError(
                f"Actuals dataset family for {value!r} has no readable versions"
            )
        return latest.items[0]

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
