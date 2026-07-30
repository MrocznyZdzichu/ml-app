"""Business Case lifecycle and dataset attachment operations."""

from __future__ import annotations

from typing import Any, Mapping

from .errors import AuthorizationError, ConflictError, ResourceNotFoundError
from .models import CatalogPage
from .pagination import iter_offset_items
from .resolution import _one_named
from .transport import TransportClientMixin


class BusinessCaseClientMixin(TransportClientMixin):
    """Business Case operations composed into :class:`MLAppClient`."""

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

    def _business_case_by_name(self, name: str) -> Mapping[str, Any]:
        candidates = [
            item
            for item in iter_offset_items(
                lambda limit, offset: self.page_business_cases(
                    limit=limit,
                    offset=offset,
                    search=name,
                )
            )
            if item.get("name") == name
        ]
        return _one_named(candidates, name, "Business Case")
