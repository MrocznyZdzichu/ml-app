"""Online prediction, inference-log, and challenger-replay workflows."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .models import CatalogPage, Deployment, PredictionResult
from .transport import TransportClientMixin


class InferenceClientMixin(TransportClientMixin):
    """Inference operations composed into :class:`MLAppClient`."""

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
            raise ValueError(
                "Provide either features for one record or instances for a batch"
            )
        normalized = (
            [{"record_id": record_id, "features": dict(features or {})}]
            if features is not None
            else [self._prediction_instance(item) for item in instances or []]
        )
        if not normalized or len(normalized) > 1000:
            raise ValueError(
                "Prediction batch must contain between 1 and 1,000 instances"
            )
        path = f"/serving/deployments/{target.id}/predictions"
        if challenger_model_id:
            path = (
                f"/serving/deployments/{target.id}/challengers/"
                f"{challenger_model_id}/predictions"
            )
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return PredictionResult.from_api(
            self._request(
                "POST",
                path,
                json={"instances": normalized},
                headers=headers,
            )
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
        return self._request(
            "GET",
            f"/serving/deployments/{target.id}/inference-log",
            params=params,
        )

    def inference_request(
        self,
        deployment: str | Deployment,
        request_id: str,
    ) -> Mapping[str, Any]:
        """Read full champion/fallback/shadow executions for one audited request."""
        target = self._deployment(deployment)
        return self._request(
            "GET",
            f"/serving/deployments/{target.id}/inference-log/{request_id}",
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

    def list_challenger_replays(
        self,
        deployment: str | Deployment,
    ) -> list[Mapping[str, Any]]:
        target = self._deployment(deployment)
        return self._request(
            "GET",
            f"/serving/deployments/{target.id}/challenger-replays",
        )

    @staticmethod
    def _prediction_instance(value: Mapping[str, Any]) -> dict[str, Any]:
        if "features" in value:
            return {
                "record_id": value.get("record_id"),
                "features": dict(value["features"]),
            }
        return {
            "record_id": value.get("record_id"),
            "features": {
                key: item
                for key, item in value.items()
                if key != "record_id"
            },
        }
