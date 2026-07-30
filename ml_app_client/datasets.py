"""Dataset catalog, upload, preview, and download workflows."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from .errors import ApiError, ResourceAmbiguousError, ResourceNotFoundError
from .models import CatalogPage, Dataset
from .pagination import iter_offset_items
from .transport import TransportClientMixin


class DatasetClientMixin(TransportClientMixin):
    """Dataset operations composed into :class:`MLAppClient`."""

    upload_timeout: float

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
        attached_matches = [
            item
            for item in iter_offset_items(
                lambda limit, offset: self.page_datasets(
                    limit=limit,
                    offset=offset,
                    search=dataset_name,
                    business_case_id=str(business_case["id"]),
                    families=True,
                )
            )
            if item.name == dataset_name
        ]
        if not attached_matches:
            raise ResourceNotFoundError(
                f"Dataset attached to Business Case named {dataset_name!r} was not found"
            )
        logical_ids = {item.logical_id for item in attached_matches}
        if len(logical_ids) != 1:
            raise ResourceAmbiguousError(
                f"Dataset attached to Business Case name {dataset_name!r} is ambiguous "
                f"({len(logical_ids)} families)"
            )
        return max(attached_matches, key=lambda item: item.version_number)

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
        dataset = self.dataset_by_name(
            business_case_name=business_case_name,
            dataset_name=dataset_name,
        )
        return self.upload_dataset(
            file_path,
            logical_id=dataset.logical_id,
            description=description,
            tags=tags,
        )

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
