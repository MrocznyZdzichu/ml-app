import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.query_engine import DatasetQueryEngine
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.datasets.schemas import (
    DataAssetCreate,
    DataAssetMetadataUpdate,
    DataAssetPreviewRead,
    DataAssetProfileRead,
    DataAssetProfileRequest,
    DataAssetSqlQueryRequest,
    DataViewCreate,
)
from app.modules.datasets.sources import DatasetSourceRegistry


class DatasetService:
    """Coordinates dataset lifecycle and delegates tabular execution to DatasetQueryEngine."""

    def __init__(self, repository: DatasetRepository | None = None) -> None:
        self.repository = repository or PostgresDatasetRepository()
        self.repository_root = Path("data/repository")
        self.sources = DatasetSourceRegistry(self.repository_root)
        self.query_engine = DatasetQueryEngine(self.sources)

    def register(self, payload: DataAssetCreate, principal: Principal) -> DataAsset:
        asset = DataAsset(
            id=str(uuid4()),
            owner_id=principal.user_id,
            name=payload.name,
            source_type=payload.source_type,
            format=payload.format,
            description=payload.description,
            location_uri=payload.location_uri,
            tags=list(payload.tags),
            metadata=dict(payload.metadata),
        )
        return self.repository.add(asset)

    def create_view(self, payload: DataViewCreate, principal: Principal) -> DataAsset:
        source = self.get_asset(payload.source_dataset_id, principal)
        if source.status == DataAssetStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted dataset cannot be used as a Data View source",
            )

        now = datetime.now(timezone.utc)
        preview = self.query_engine.preview_definition(
            source,
            payload.definition,
            lambda asset_id: self.get_asset(asset_id, principal),
            limit=50_000,
        )
        inherited_roles = self._inherit_data_roles(source, [column.name for column in preview.columns])
        view = DataAsset(
            id=str(uuid4()),
            owner_id=principal.user_id,
            name=payload.name.strip(),
            source_type=SourceType.VIEW,
            format="view",
            description=payload.description,
            location_uri=f"view://{source.id}",
            row_count=preview.row_count,
            has_header=True,
            uploaded_by=principal.user_id,
            uploaded_at=now,
            status=DataAssetStatus.READY,
            tags=list(payload.tags),
            metadata={
                "data_view": {
                    "source_dataset_id": source.id,
                    "source_dataset_name": source.name,
                    "definition": dict(payload.definition),
                    "created_by": principal.user_id,
                    "created_at": now.isoformat(),
                    "row_count": preview.row_count,
                    "column_count": len(preview.columns),
                },
                **({"data_roles": inherited_roles} if inherited_roles else {}),
            },
        )
        return self.repository.add(view)

    def upload_csv(
        self,
        content: bytes,
        filename: str,
        principal: Principal,
        name: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
    ) -> DataAsset:
        if not filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .csv files are supported",
            )
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded CSV file is empty",
            )

        text = self.sources.csv.decode(content)
        has_header, row_count = self.sources.csv.inspect(text)
        dataset_id = str(uuid4())
        safe_filename = self._safe_filename(filename)
        storage_path = self.repository_root / "users" / principal.user_id / dataset_id / safe_filename
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        now = datetime.now(timezone.utc)

        asset = DataAsset(
            id=dataset_id,
            owner_id=principal.user_id,
            name=name or Path(filename).stem,
            source_type=SourceType.FILE,
            format="csv",
            description=description,
            original_filename=filename,
            location_uri=f"file://{storage_path.as_posix()}",
            file_size_bytes=len(content),
            row_count=row_count,
            has_header=has_header,
            uploaded_by=principal.user_id,
            uploaded_at=now,
            status=DataAssetStatus.READY,
            tags=list(tags or []),
        )
        return self.repository.add(asset)

    def list_assets(self, principal: Principal) -> list[DataAsset]:
        return self.repository.list_for_owner(principal.user_id)

    def get_asset(self, dataset_id: str, principal: Principal) -> DataAsset:
        asset = self.repository.get(dataset_id)
        if not asset or asset.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
        return asset

    def profile(self, dataset_id: str, payload: DataAssetProfileRequest, principal: Principal) -> DataAssetProfileRead:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted dataset cannot be profiled",
            )
        asset.status = DataAssetStatus.PROFILING
        self.repository.update(asset)
        return DataAssetProfileRead(
            dataset_id=dataset_id,
            status="queued",
            sample_size=payload.sample_size,
            include_correlations=payload.include_correlations,
            artifact_uri=None,
        )

    def update_metadata(
        self,
        dataset_id: str,
        payload: DataAssetMetadataUpdate,
        principal: Principal,
    ) -> DataAsset:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted dataset metadata cannot be updated",
            )
        asset.metadata = self._merge_metadata(asset.metadata, payload.metadata)
        return self.repository.update(asset)

    def preview(self, dataset_id: str, principal: Principal, limit: int = 5000) -> DataAssetPreviewRead:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted dataset cannot be browsed",
            )
        return self.query_engine.preview(
            asset,
            lambda asset_id: self.get_asset(asset_id, principal),
            limit,
            dataset_id=dataset_id,
        )

    def query(
        self,
        dataset_id: str,
        payload: DataAssetSqlQueryRequest,
        principal: Principal,
    ) -> DataAssetPreviewRead:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted dataset cannot be queried",
            )
        return self.query_engine.query(
            asset,
            lambda asset_id: self.get_asset(asset_id, principal),
            payload.sql,
            payload.limit,
            dataset_id=dataset_id,
        )

    def delete_asset(self, dataset_id: str, principal: Principal) -> DataAsset:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            return asset

        self._delete_physical_data(asset)
        now = datetime.now(timezone.utc)
        asset.status = DataAssetStatus.DELETED
        asset.deleted_by = principal.user_id
        asset.deleted_at = now
        return self.repository.update(asset)

    def _safe_filename(self, filename: str) -> str:
        return Path(filename.replace("\\", "_").replace("/", "_")).name

    def _inherit_data_roles(self, source: DataAsset, column_names: list[str]) -> dict[str, Any]:
        source_roles = self._as_record(source.metadata.get("data_roles"))
        if not source_roles:
            return {}

        column_set = set(column_names)
        inherited: dict[str, Any] = {}
        dataset_roles = self._as_list(source_roles.get("dataset_roles"))
        if dataset_roles:
            inherited["dataset_roles"] = [role for role in dataset_roles if isinstance(role, str)]

        for key in ("entity_id_column", "timestamp_column", "period_column", "target_column"):
            value = source_roles.get(key)
            if isinstance(value, str) and value in column_set:
                inherited[key] = value

        column_roles = {
            column: role
            for column, role in self._as_record(source_roles.get("column_roles")).items()
            if column in column_set and isinstance(role, str)
        }
        if column_roles:
            inherited["column_roles"] = column_roles

        notes = source_roles.get("notes")
        if isinstance(notes, str) and notes:
            inherited["notes"] = notes

        return inherited

    def _merge_metadata(self, existing: dict[str, object], incoming: dict[str, Any]) -> dict[str, object]:
        merged = dict(existing or {})
        for key, value in incoming.items():
            current_value = merged.get(key)
            if isinstance(current_value, dict) and isinstance(value, dict):
                merged[key] = self._merge_metadata(current_value, value)
            else:
                merged[key] = value
        return merged

    def _delete_physical_data(self, asset: DataAsset) -> None:
        dataset_dir = self.repository_root / "users" / asset.owner_id / asset.id
        root = self.repository_root.resolve()
        target = dataset_dir.resolve()
        if not self._is_relative_to(target, root):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Dataset storage path is outside the repository root",
            )
        if target.exists():
            shutil.rmtree(target)

    def _is_relative_to(self, path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
        except ValueError:
            return False
        return True

    def _as_record(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _as_list(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []
