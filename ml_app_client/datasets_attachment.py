"""Business Case-to-dataset mapping workflows."""

from __future__ import annotations

from collections.abc import Iterator

from .errors import ResourceAmbiguousError, ResourceNotFoundError
from .models import BusinessCase, Dataset, DatasetAttachment, CatalogPage
from .pagination import iter_offset_items
from .transport import TransportClientMixin


BusinessCaseRef = str | BusinessCase
DatasetAttachmentRef = str | DatasetAttachment


class DatasetAttachmentClientMixin(TransportClientMixin):
    """CRUD operations for role-specific Dataset-to-Business-Case mappings."""

    def create_dataset_attachment(
        self,
        business_case: BusinessCaseRef,
        dataset: str | Dataset,
        *,
        role: str,
        context_note: str = "",
        primary_key_column: str = "",
        target_column: str = "",
    ) -> DatasetAttachment:
        """Attach one readable immutable dataset version to a Business Case."""
        business_case_id = self._business_case_id(business_case)
        dataset_id = dataset.id if isinstance(dataset, Dataset) else dataset
        return DatasetAttachment.from_api(self._request(
            "POST", f"/business-cases/{business_case_id}/data-attachments",
            json={
                "data_asset_id": dataset_id,
                "data_asset_kind": "dataset",
                "role": role,
                "context_note": context_note,
                "primary_key_column": primary_key_column,
                "target_column": target_column,
                "origin": "uploaded",
            },
        ))

    def page_dataset_attachments(
        self,
        business_case: BusinessCaseRef,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        role: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        deleted_only: bool = False,
    ) -> CatalogPage[DatasetAttachment]:
        """Search a Business Case's mappings with bounded pagination."""
        business_case_id = self._business_case_id(business_case)
        payload = self._request(
            "GET", f"/business-cases/{business_case_id}/data-attachments/page",
            params={
                "limit": limit, "offset": offset, "search": search, "role": role,
                "pipeline_id": pipeline_id, "pipeline_type": pipeline_type,
                "uploaded_only": str(uploaded_only).lower(),
                "deleted_only": str(deleted_only).lower(),
            },
        )
        return CatalogPage.from_api(payload, DatasetAttachment.from_api)

    def list_dataset_attachments(self, business_case: BusinessCaseRef) -> list[DatasetAttachment]:
        """Return a legacy unbounded mapping list; prefer :meth:`page_dataset_attachments`."""
        business_case_id = self._business_case_id(business_case)
        payload = self._request("GET", f"/business-cases/{business_case_id}/data-attachments")
        return [DatasetAttachment.from_api(item) for item in payload]

    def iter_dataset_attachments(
        self, business_case: BusinessCaseRef, *, search: str = "", role: str = "", page_size: int = 100,
    ) -> Iterator[DatasetAttachment]:
        """Iterate a caller-selected complete mapping result."""
        return iter_offset_items(
            lambda limit, offset: self.page_dataset_attachments(
                business_case, limit=limit, offset=offset, search=search, role=role,
            ),
            page_size=page_size,
        )

    def get_dataset_attachment(
        self, business_case: BusinessCaseRef, attachment_id: str,
    ) -> DatasetAttachment:
        """Resolve one mapping through bounded pages until a detail API exists."""
        for attachment in self.iter_dataset_attachments(business_case):
            if attachment.id == attachment_id:
                return attachment
        raise ResourceNotFoundError(f"Dataset attachment {attachment_id!r} was not found")

    def update_dataset_attachment(
        self,
        business_case: BusinessCaseRef,
        attachment: DatasetAttachmentRef,
        **changes: str,
    ) -> DatasetAttachment:
        """Update mapping context without changing its immutable dataset version."""
        business_case_id = self._business_case_id(business_case)
        current = (
            attachment if isinstance(attachment, DatasetAttachment)
            else self.get_dataset_attachment(business_case_id, attachment)
        )
        allowed = {"role", "context_note", "primary_key_column", "target_column"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported dataset attachment fields: {', '.join(sorted(unknown))}")
        payload = {field: current.raw.get(field, "") for field in allowed}
        payload.update(changes)
        return DatasetAttachment.from_api(self._request(
            "PATCH", f"/business-cases/{business_case_id}/data-attachments/{current.id}", json=payload,
        ))

    def delete_dataset_attachment(
        self, business_case: BusinessCaseRef, attachment: DatasetAttachmentRef,
    ) -> None:
        """Delete only the mapping; dataset data and lineage remain intact."""
        business_case_id = self._business_case_id(business_case)
        attachment_id = attachment.id if isinstance(attachment, DatasetAttachment) else attachment
        self._request("DELETE", f"/business-cases/{business_case_id}/data-attachments/{attachment_id}")

    def find_dataset_attachment(
        self, business_case: BusinessCaseRef, dataset: str | Dataset, *, role: str | None = None,
    ) -> DatasetAttachment:
        """Resolve exactly one mapping for a dataset version and optional role."""
        dataset_id = dataset.id if isinstance(dataset, Dataset) else dataset
        matches = [
            item for item in self.iter_dataset_attachments(business_case, role=role or "")
            if item.data_asset_id == dataset_id and (role is None or item.role == role)
        ]
        if not matches:
            raise ResourceNotFoundError(f"Dataset {dataset_id!r} is not attached to the Business Case")
        if len(matches) > 1:
            raise ResourceAmbiguousError(
                f"Dataset {dataset_id!r} has {len(matches)} matching Business Case attachments"
            )
        return matches[0]
