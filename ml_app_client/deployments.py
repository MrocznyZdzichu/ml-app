"""Online model-service configuration and immutable revision workflows."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from .errors import ConflictError, ResourceAmbiguousError, ResourceNotFoundError
from .models import CatalogPage, Deployment, ModelServingUsage
from .pagination import iter_offset_items
from .resolution import _friendly_name_key, _named_candidates
from .transport import TransportClientMixin


class DeploymentClientMixin(TransportClientMixin):
    """Deployment operations composed into :class:`MLAppClient`."""

    def list_deployments(self, *, include_archived: bool = False) -> list[Deployment]:
        """List visible model services, excluding archived services by default."""
        params = {"include_archived": "true"} if include_archived else None
        return [
            Deployment.from_api(item)
            for item in self._request("GET", "/serving/deployments", params=params)
        ]

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
            item
            for item in iter_offset_items(
                lambda limit, offset: self.page_deployments(
                    limit=limit,
                    offset=offset,
                    search=name,
                    include_archived=include_archived,
                )
            )
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
        return [
            ModelServingUsage.from_api(item)
            for item in self._request("GET", path)
        ]

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
        resolved_model_id = (
            model_id or self._production_model_by_name(model_name or "")["id"]
        )
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
        assignments.extend(
            {"model_id": item, "role": "challenger"} for item in challengers
        )
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

    def _deployment(self, value: str | Deployment) -> Deployment:
        if isinstance(value, Deployment):
            return value
        normalized = value.strip().casefold()
        matches = [
            item
            for item in iter_offset_items(
                lambda limit, offset: self.page_deployments(
                    limit=limit,
                    offset=offset,
                    search=value,
                )
            )
            if normalized in {item.slug.casefold(), item.name.strip().casefold()}
        ]
        if not matches:
            try:
                return Deployment.from_api(self._request(
                    "GET",
                    f"/serving/deployments/{quote(value, safe='')}",
                ))
            except ResourceNotFoundError:
                pass
        if not matches:
            raise ResourceNotFoundError(f"Deployment {value!r} was not found")
        if len(matches) > 1:
            raise ResourceAmbiguousError(f"Deployment {value!r} is ambiguous")
        return matches[0]

    def _production_model_by_name(self, name: str) -> Mapping[str, Any]:
        if not name.strip():
            raise ValueError("Provide model_id or model_name")
        candidates = _named_candidates(
            self._model_family_candidates(
                name,
                stage="production",
            ),
            name,
        )
        if not candidates:
            raise ResourceNotFoundError(
                f"Production model named {name!r} was not found"
            )
        families = {
            str(
                item.get("logical_id")
                or _friendly_name_key(str(item.get("name") or ""))
            )
            for item in candidates
        }
        if len(families) > 1:
            raise ResourceAmbiguousError(
                f"Production model {name!r} is ambiguous; provide model_id explicitly"
            )
        return max(
            candidates,
            key=lambda item: int(item.get("version_number") or 0),
        )
