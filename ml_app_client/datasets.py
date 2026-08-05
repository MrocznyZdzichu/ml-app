"""Dataset catalog, upload, preview, and download workflows."""

from __future__ import annotations

from html import escape
import json
import mimetypes
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Mapping
from urllib.parse import quote

from .errors import ApiError, ConflictError, ResourceAmbiguousError, ResourceNotFoundError
from .models import CatalogPage, Dataset
from .pagination import iter_offset_items
from .transport import TransportClientMixin


DatasetRef = str | Dataset


class DatasetMetadataPresentation:
    """Readable terminal and notebook view of one Dataset and its structured metadata."""

    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset

    @property
    def _schema(self) -> list[Mapping[str, Any]]:
        value = self.dataset.metadata.get("source_schema")
        return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []

    @property
    def _other_metadata(self) -> Mapping[str, Any]:
        return {
            key: value for key, value in self.dataset.metadata.items()
            if key != "source_schema"
        }

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)

    def __str__(self) -> str:
        dataset = self.dataset
        lines = [
            f"Dataset metadata — {dataset.name} v{dataset.version_number}",
            f"Version ID : {dataset.id}",
            f"Family ID  : {dataset.logical_id}",
            f"Rows       : {dataset.row_count if dataset.row_count is not None else '—'}",
            f"Format     : {dataset.format}",
            f"Status     : {dataset.status}",
        ]
        if self._schema:
            lines.extend(["", "Columns:"])
            lines.extend(
                f"- {item.get('name', 'unnamed')}: {item.get('type', 'unknown')}"
                for item in self._schema
            )
        if self._other_metadata:
            lines.extend(["", "Other metadata:", self._json(self._other_metadata)])
        return "\n".join(lines)

    def _repr_html_(self) -> str:
        dataset = self.dataset
        overview = (
            ("Version ID", dataset.id), ("Family ID", dataset.logical_id),
            ("Rows", dataset.row_count if dataset.row_count is not None else "—"),
            ("Format", dataset.format), ("Source type", dataset.source_type),
            ("Stage", dataset.version_stage), ("Status", dataset.status),
            ("Tags", ", ".join(dataset.tags) or "—"),
        )
        overview_rows = "".join(
            f"<tr><th>{escape(label)}</th><td>{escape(str(value))}</td></tr>"
            for label, value in overview
        )
        columns = "".join(
            "<tr>"
            f"<td>{escape(str(item.get('name') or '—'))}</td>"
            f"<td>{escape(str(item.get('type') or '—'))}</td>"
            f"<td>{escape(self._json({key: value for key, value in item.items() if key not in {'name', 'type'}})) if len(item) > 2 else '—'}</td>"
            "</tr>"
            for item in self._schema
        ) or '<tr><td colspan="3">No column schema is available for this Dataset.</td></tr>'
        extra = escape(self._json(self._other_metadata))
        description = escape(dataset.description) if dataset.description else "—"
        return (
            '<section class="mlapp-dataset-metadata">'
            f"<h3>{escape(dataset.name)} <small>v{dataset.version_number}</small></h3>"
            f"<p>{description}</p>"
            f"<table><tbody>{overview_rows}</tbody></table>"
            "<h4>Columns</h4><table><thead><tr><th>Name</th><th>Type</th><th>Details</th></tr></thead>"
            f"<tbody>{columns}</tbody></table>"
            f"<details><summary>Other metadata ({len(self._other_metadata)})</summary><pre>{extra}</pre></details>"
            "<style>"
            ".mlapp-dataset-metadata{max-width:1000px;font-family:system-ui,sans-serif;color:#eaf1ff;}"
            ".mlapp-dataset-metadata h3{margin:0 0 4px;font-size:19px}.mlapp-dataset-metadata h3 small{color:#a3e635;font:600 12px ui-monospace,monospace}.mlapp-dataset-metadata p{margin:0 0 12px;color:#b8c7df}.mlapp-dataset-metadata table{width:100%;border-collapse:collapse;background:#121d30;margin:8px 0 16px}.mlapp-dataset-metadata th,.mlapp-dataset-metadata td{padding:8px 10px;border-bottom:1px solid #2d405d;text-align:left;vertical-align:top}.mlapp-dataset-metadata th{color:#a3e635;font:600 12px ui-monospace,monospace}.mlapp-dataset-metadata thead th{color:#a9bad4}.mlapp-dataset-metadata td{overflow-wrap:anywhere}.mlapp-dataset-metadata details{background:#121d30;border:1px solid #2d405d;padding:8px 10px}.mlapp-dataset-metadata summary{cursor:pointer;color:#a3e635}.mlapp-dataset-metadata pre{white-space:pre-wrap;overflow:auto;color:#d8e4f7}"
            "</style></section>"
        )


class DatasetClientMixin(TransportClientMixin):
    """Dataset operations composed into :class:`MLAppClient`."""

    upload_timeout: float

    def _assert_new_dataset_name_available(self, name: str, *, force: bool) -> None:
        """Reject a duplicate only when it is already visible to this principal."""
        if force:
            return
        normalized_name = name.strip().casefold()
        if not normalized_name:
            return
        for dataset in iter_offset_items(
            lambda limit, offset: self.page_datasets(
                limit=limit,
                offset=offset,
                search=name,
                families=True,
            )
        ):
            if dataset.name.strip().casefold() == normalized_name:
                raise ConflictError(
                    f"A visible Dataset named {name!r} already exists. "
                    "Pass force=True to create another Dataset family with this name."
                )

    def create_dataset(
        self,
        *,
        name: str,
        source_type: str,
        format: str = "csv",
        description: str = "",
        location_uri: str | None = None,
        database: Mapping[str, Any] | None = None,
        api: Mapping[str, Any] | None = None,
        tags: tuple[str, ...] | list[str] = (),
        metadata: Mapping[str, Any] | None = None,
        force: bool = False,
    ) -> Dataset:
        """Register a non-uploaded dataset source as a new dataset family.

        The REST API accepts ``file``, ``database`` and ``api`` source types.
        File-backed datasets with content should use :meth:`upload_dataset`.
        A visible Dataset with the same name requires explicit ``force=True``.
        Invisible Datasets do not affect this check and are never disclosed.
        """
        self._assert_new_dataset_name_available(name, force=force)
        payload: dict[str, Any] = {
            "name": name,
            "source_type": source_type,
            "format": format,
            "description": description,
            "location_uri": location_uri,
            "tags": list(tags),
            "metadata": dict(metadata or {}),
        }
        if database is not None:
            payload["database"] = dict(database)
        if api is not None:
            payload["api"] = dict(api)
        return Dataset.from_api(self._request("POST", "/datasets", json=payload))

    def upload_dataset(
        self,
        file_path: str | Path,
        *,
        name: str | None = None,
        description: str = "",
        tags: tuple[str, ...] | list[str] = (),
        logical_id: str | None = None,
        force: bool = False,
    ) -> Dataset:
        """Stream a CSV or Parquet file as a new dataset or immutable version.

        Creating a family requires ``force=True`` when a visible Dataset already
        has the selected name. Uploading with ``logical_id`` creates a version and
        therefore never performs this duplicate-name check.
        """
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(path)
        if logical_id is None:
            self._assert_new_dataset_name_available(name or path.stem, force=force)
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

    def get_dataset(self, dataset: DatasetRef) -> Dataset:
        """Fetch one immutable dataset version by ID or return a typed instance."""
        if isinstance(dataset, Dataset):
            return dataset
        return Dataset.from_api(self._request("GET", f"/datasets/{quote(dataset, safe='')}"))

    def present_dataset_metadata(self, dataset: DatasetRef) -> DatasetMetadataPresentation:
        """Return a structured metadata view with a column table and compact JSON sections."""
        return DatasetMetadataPresentation(self.get_dataset(dataset))

    def display_dataset_metadata(self, dataset: DatasetRef) -> DatasetMetadataPresentation:
        """Render structured Dataset metadata in IPython or print it in a terminal."""
        presentation = self.present_dataset_metadata(dataset)
        try:
            from IPython.display import display
        except ImportError:
            print(presentation)
        else:
            display(presentation)
        return presentation

    def update_dataset_metadata(
        self, dataset: DatasetRef, *, metadata: Mapping[str, Any],
    ) -> Dataset:
        """Merge metadata into one persistent dataset version.

        Dataset content and version identity stay immutable. The service currently
        exposes metadata as the only mutable dataset field.
        """
        dataset_id = dataset.id if isinstance(dataset, Dataset) else dataset
        return Dataset.from_api(self._request(
            "PATCH", f"/datasets/{quote(dataset_id, safe='')}/metadata",
            json={"metadata": dict(metadata)},
        ))

    def delete_dataset(self, dataset: DatasetRef) -> Dataset:
        """Soft-delete one dataset version and return its deleted metadata."""
        dataset_id = dataset.id if isinstance(dataset, Dataset) else dataset
        return Dataset.from_api(self._request(
            "DELETE", f"/datasets/{quote(dataset_id, safe='')}"
        ))

    def page_datasets(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        business_case_id: str = "",
        status: str = "",
        source_type: str = "",
        asset_kind: str = "",
        include_deleted: bool = False,
        families: bool = True,
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        owned_only: bool = False,
    ) -> CatalogPage[Dataset]:
        """Search a bounded data catalog and return the exact filtered total.

        Filters mirror the Dataset UI. ``uploaded_only`` excludes views,
        pipeline outputs, and platform-generated assets; ``owned_only`` limits
        the page to datasets owned by the authenticated user.
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "search": search,
            "business_case_id": business_case_id,
            "asset_kind": asset_kind,
            "include_deleted": str(include_deleted).lower(),
            "families": str(families).lower(),
            "pipeline_id": pipeline_id,
            "pipeline_type": pipeline_type,
            "uploaded_only": str(uploaded_only).lower(),
            "owned_only": str(owned_only).lower(),
            "summary": "true",
        }
        # FastAPI enum query parameters must be absent when no filter is selected;
        # sending status="" or source_type="" is a validation error (HTTP 422).
        if status:
            params["status"] = status
        if source_type:
            params["source_type"] = source_type
        payload = self._request("GET", "/datasets/page", params=params)
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

    def list_dataset_versions(self, logical_dataset_id: str) -> list[Dataset]:
        """Return a legacy unbounded version history; prefer paged access."""
        payload = self._request(
            "GET", f"/datasets/{quote(logical_dataset_id, safe='')}/versions"
        )
        return [Dataset.from_api(item) for item in payload]

    def iter_dataset_versions(
        self, logical_dataset_id: str, *, page_size: int = 100,
    ) -> Iterator[Dataset]:
        """Iterate a deliberately selected complete immutable version history."""
        return iter_offset_items(
            lambda limit, offset: self.page_dataset_versions(
                logical_dataset_id, limit=limit, offset=offset,
            ),
            page_size=page_size,
        )

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
        force: bool = False,
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
            force=force,
        )
        self.create_dataset_attachment(
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

    def create_dataset_version(
        self,
        file_path: str | Path,
        dataset: DatasetRef,
        *,
        description: str = "",
        tags: tuple[str, ...] | list[str] = (),
    ) -> Dataset:
        """Upload the next immutable version of an existing dataset family."""
        current = self.get_dataset(dataset)
        return self.upload_dataset(
            file_path,
            logical_id=current.logical_id,
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
