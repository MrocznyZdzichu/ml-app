"""Typed Business Case lifecycle and data-binding workflows."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .errors import AuthorizationError, ConflictError, ResourceNotFoundError
from .models import (
    BusinessCase,
    CatalogPage,
)
from .pagination import iter_offset_items
from .resolution import _one_named
from .transport import TransportClientMixin


BusinessCaseRef = str | BusinessCase
class BusinessCaseClientMixin(TransportClientMixin):
    """Business Case operations composed into :class:`MLAppClient`.

    Catalog methods are bounded by default. Iterators intentionally traverse all
    matching pages only when a caller explicitly requests the complete range.
    """

    def create_business_case(
        self, *, name: str, description: str = "", problem_type: str = "custom",
        status: str = "draft", business_owner: str = "", primary_metric: str = "",
        target_column: str = "", business_goal: str = "", success_criteria: str = "",
    ) -> BusinessCase:
        """Create a Business Case owned by the authenticated user."""
        return BusinessCase.from_api(self._request("POST", "/business-cases", json={
            "name": name, "description": description, "problem_type": problem_type,
            "status": status, "business_owner": business_owner,
            "primary_metric": primary_metric, "target_column": target_column,
            "business_goal": business_goal, "success_criteria": success_criteria,
        }))

    def get_business_case(self, business_case: BusinessCaseRef) -> BusinessCase:
        """Fetch one Business Case by ID, or return an already typed instance."""
        if isinstance(business_case, BusinessCase):
            return business_case
        return BusinessCase.from_api(self._request("GET", f"/business-cases/{business_case}"))

    def get_business_case_by_name(self, name: str) -> BusinessCase:
        """Resolve one visible Business Case by its globally unique name."""
        return self._business_case_by_name(name)

    def business_case_by_name(self, name: str) -> BusinessCase:
        """Backward-compatible alias for :meth:`get_business_case_by_name`."""
        return self.get_business_case_by_name(name)

    def page_business_cases(
        self, *, limit: int = 30, offset: int = 0, search: str = "",
        manageable_only: bool = False,
    ) -> CatalogPage[BusinessCase]:
        """Search visible Business Cases without loading the full catalog."""
        payload = self._request("GET", "/business-cases/page", params={
            "limit": limit, "offset": offset, "search": search,
            "manageable_only": str(manageable_only).lower(),
        })
        return CatalogPage.from_api(payload, BusinessCase.from_api)

    def iter_business_cases(
        self, *, search: str = "", manageable_only: bool = False, page_size: int = 100,
    ) -> Iterator[BusinessCase]:
        """Iterate an explicitly chosen complete Business Case search result."""
        return iter_offset_items(
            lambda limit, offset: self.page_business_cases(
                limit=limit, offset=offset, search=search, manageable_only=manageable_only,
            ), page_size=page_size,
        )

    def update_business_case(self, business_case: BusinessCaseRef, **changes: Any) -> BusinessCase:
        """Update named BC fields, preserving omitted fields required by the REST contract."""
        current = self.get_business_case(business_case)
        allowed = {
            "name", "description", "problem_type", "status", "business_owner",
            "primary_metric", "target_column", "business_goal", "success_criteria",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported Business Case fields: {', '.join(sorted(unknown))}")
        payload = {
            field: getattr(current, field)
            for field in allowed
        }
        payload.update(changes)
        return BusinessCase.from_api(self._request(
            "PATCH", f"/business-cases/{current.id}", json=payload
        ))

    def archive_business_case(self, business_case: BusinessCaseRef) -> BusinessCase:
        """Archive a BC without deleting its immutable lineage."""
        return self.update_business_case(business_case, status="archived")

    def activate_business_case(self, business_case: BusinessCaseRef) -> BusinessCase:
        """Restore a Business Case to the active lifecycle state."""
        return self.update_business_case(business_case, status="active")

    def transfer_business_case_ownership(
        self, business_case: BusinessCaseRef, *, new_owner_id: str, reason: str = "",
    ) -> BusinessCase:
        """Transfer ownership through the auditable platform endpoint."""
        business_case_id = self._business_case_id(business_case)
        return BusinessCase.from_api(self._request(
            "POST", f"/business-cases/{business_case_id}/transfer-ownership",
            json={"new_owner_id": new_owner_id, "reason": reason},
        ))

    def ensure_business_case(self, **definition: Any) -> tuple[BusinessCase, bool]:
        """Return a visible BC or create it once, with race-safe conflict handling."""
        name = str(definition.get("name") or "").strip()
        if not name:
            raise ValueError("Business Case name is required")
        try:
            return self.get_business_case_by_name(name), False
        except ResourceNotFoundError:
            pass
        try:
            return self.create_business_case(**definition), True
        except ConflictError as exc:
            try:
                return self.get_business_case_by_name(name), False
            except ResourceNotFoundError:
                raise AuthorizationError(
                    f"Business Case {name!r} already exists but is not accessible. "
                    "Ask an administrator or Business Case manager to grant access."
                ) from exc

    def _business_case_by_name(self, name: str) -> BusinessCase:
        candidates = [
            item for item in self.iter_business_cases(search=name)
            if item.name == name
        ]
        return BusinessCase.from_api(_one_named(candidates, name, "Business Case"))

    @staticmethod
    def _business_case_id(business_case: BusinessCaseRef) -> str:
        return business_case.id if isinstance(business_case, BusinessCase) else business_case
