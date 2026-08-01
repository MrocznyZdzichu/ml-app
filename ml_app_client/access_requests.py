"""Typed Business Case directory and access-request workflows."""

from __future__ import annotations

from typing import Any

from .models import (
    BusinessCase,
    BusinessCaseAccessRequest,
    BusinessCaseCatalogEntry,
    CatalogPage,
)
from .transport import TransportClientMixin


BusinessCaseRef = str | BusinessCase


class AccessRequestClientMixin(TransportClientMixin):
    """Business Case discovery and auditable access-request operations.

    The directory intentionally exposes only minimal organization-wide metadata.
    Request queues are bounded; callers choose a page and any history scope
    explicitly rather than loading a complete organization-wide queue.
    """

    def page_business_case_catalog(
        self, *, limit: int = 30, offset: int = 0, search: str = "",
    ) -> CatalogPage[BusinessCaseCatalogEntry]:
        """Search the minimal organization-wide Business Case directory."""
        payload = self._request("GET", "/business-cases/catalog/page", params={
            "limit": limit, "offset": offset, "search": search,
        })
        return CatalogPage.from_api(payload, BusinessCaseCatalogEntry.from_api)

    def request_business_case_access(
        self, business_case: BusinessCaseRef, *, requested_role: str = "reader", justification: str,
    ) -> BusinessCaseAccessRequest:
        """Submit an auditable request to the Business Case owner and managers."""
        business_case_id = self._business_case_id(business_case)
        return BusinessCaseAccessRequest.from_api(self._request(
            "POST", f"/sharing/business-cases/{business_case_id}/access-requests",
            json={"requested_role": requested_role, "justification": justification},
        ))

    def page_business_case_access_requests(
        self, *, box: str = "incoming", status: str | None = None, limit: int = 30, offset: int = 0,
    ) -> CatalogPage[BusinessCaseAccessRequest]:
        """Page the caller-scoped current queue or submitted/handled history.

        ``submitted_history`` returns the caller's completed requests and
        ``handled`` returns completed requests decided by the caller. Current
        inboxes retain the ``pending`` default unless another status is given.
        """
        effective_status = status
        if effective_status is None and box not in {"submitted_history", "handled"}:
            effective_status = "pending"
        payload = self._request("GET", "/sharing/access-requests/page", params={
            "box": box, "status": effective_status, "limit": limit, "offset": offset,
        })
        return CatalogPage.from_api(payload, BusinessCaseAccessRequest.from_api)

    def page_business_case_access_requests_for_business_case(
        self, business_case: BusinessCaseRef, *, history: bool = False,
        status: str | None = None, limit: int = 30, offset: int = 0,
    ) -> CatalogPage[BusinessCaseAccessRequest]:
        """Page requests for one Business Case the caller is allowed to manage."""
        business_case_id = self._business_case_id(business_case)
        effective_status = status if status is not None else (None if history else "pending")
        payload = self._request(
            "GET", f"/sharing/business-cases/{business_case_id}/access-requests/page", params={
                "history": str(history).lower(), "status": effective_status,
                "limit": limit, "offset": offset,
            },
        )
        return CatalogPage.from_api(payload, BusinessCaseAccessRequest.from_api)

    def approve_business_case_access_request(
        self, request_id: str, *, access_role: str, decision_note: str = "",
    ) -> BusinessCaseAccessRequest:
        """Approve one pending request and atomically grant the selected role."""
        return BusinessCaseAccessRequest.from_api(self._request(
            "POST", f"/sharing/access-requests/{request_id}/approve",
            json={"access_role": access_role, "decision_note": decision_note},
        ))

    def reject_business_case_access_request(
        self, request_id: str, *, decision_note: str = "",
    ) -> BusinessCaseAccessRequest:
        """Reject one pending Business Case access request."""
        return BusinessCaseAccessRequest.from_api(self._request(
            "POST", f"/sharing/access-requests/{request_id}/reject",
            json={"decision_note": decision_note},
        ))

    @staticmethod
    def _business_case_id(business_case: BusinessCaseRef) -> str:
        return business_case.id if isinstance(business_case, BusinessCase) else business_case
