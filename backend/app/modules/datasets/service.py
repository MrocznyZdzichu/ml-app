import shutil
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from fastapi import HTTPException, status
from app.core.security import Principal
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.analysis.profile_jobs import DescriptiveProfileJobs
from app.modules.analysis.time_series_jobs import TimeSeriesAnalysisJobs
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.query_engine import DatasetQueryEngine
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.datasets.schemas import (
    DataAssetCreate,
    DataAssetMetadataUpdate,
    DataAssetDrillRequest,
    DataAssetPreviewRead,
    DataAssetProfileRead,
    DataAssetProfileRequest,
    DataAssetSqlQueryRequest,
    DataAssetVisualizationGroupsRequest,
    DataAssetVisualizationRequest,
    DataViewCreate,
    FullDescriptiveProfileRequest,
    TimeSeriesAnalysisRequest,
)
from app.modules.datasets.sources import DatasetSourceRegistry
from app.modules.datasets.visualizations import FullDatasetVisualization
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer


class DatasetService:
    """Coordinates dataset lifecycle and delegates tabular execution to DatasetQueryEngine."""

    def __init__(self, repository: DatasetRepository | None = None) -> None:
        self.repository = repository or PostgresDatasetRepository()
        self.repository_root = Path("data/repository")
        self.sources = DatasetSourceRegistry(self.repository_root)
        self.query_engine = DatasetQueryEngine(self.sources)
        self.full_profiler = FullDatasetProfiler()
        self.full_visualization = FullDatasetVisualization()
        self.time_series = FullDatasetTimeSeriesAnalyzer(self.full_visualization.store)
        self.time_series_jobs = TimeSeriesAnalysisJobs()
        self.profile_jobs = DescriptiveProfileJobs()

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
        view = DataAsset(
            id=str(uuid4()),
            owner_id=principal.user_id,
            name=payload.name.strip(),
            source_type=SourceType.VIEW,
            format="view",
            description=payload.description,
            location_uri=f"view://{source.id}",
            row_count=None,
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
                }
            },
        )
        preview = self.full_visualization.preview(
            view,
            limit=1,
            load_asset=lambda asset_id: self.get_asset(asset_id, principal),
        )
        columns = [str(column["name"]) for column in preview["columns"]]
        inherited_roles = self._inherit_data_roles(source, columns)
        view.row_count = int(preview["row_count"])
        view.metadata = {
            **view.metadata,
            "source_schema": preview["columns"],
            "data_view": {
                **dict(view.metadata["data_view"]),
                "row_count": view.row_count,
                "column_count": len(columns),
            },
            **({"data_roles": inherited_roles} if inherited_roles else {}),
        }
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
        return self.upload_csv_stream(
            stream=BytesIO(content),
            filename=filename,
            principal=principal,
            name=name,
            description=description,
            tags=tags,
        )

    def upload_csv_stream(
        self,
        stream: BinaryIO,
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
        dataset_id = str(uuid4())
        safe_filename = self._safe_filename(filename)
        storage_path = self.repository_root / "users" / principal.user_id / dataset_id / safe_filename
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        stream.seek(0)
        with storage_path.open("wb") as destination:
            shutil.copyfileobj(stream, destination, length=1024 * 1024)
        file_size = storage_path.stat().st_size
        if file_size == 0:
            storage_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded CSV file is empty",
            )
        try:
            has_header, row_count, source_schema = self.sources.csv.inspect_path_with_schema(storage_path)
        except Exception:
            shutil.rmtree(storage_path.parent, ignore_errors=True)
            raise
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
            file_size_bytes=file_size,
            row_count=row_count,
            has_header=has_header,
            uploaded_by=principal.user_id,
            uploaded_at=now,
            status=DataAssetStatus.READY,
            tags=list(tags or []),
            metadata={"source_schema": source_schema},
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
        if asset.source_type == SourceType.FILE and asset.format.lower() == "csv":
            return DataAssetPreviewRead.model_validate(self.full_profiler.schema(asset, limit))
        if asset.source_type == SourceType.VIEW:
            return DataAssetPreviewRead.model_validate(
                self.full_visualization.preview(asset, limit, lambda asset_id: self.get_asset(asset_id, principal))
            )
        return self.query_engine.preview(
            asset,
            lambda asset_id: self.get_asset(asset_id, principal),
            limit,
            dataset_id=dataset_id,
        )

    def start_descriptive_profile(
        self,
        dataset_id: str,
        payload: FullDescriptiveProfileRequest,
        principal: Principal,
    ) -> dict[str, Any]:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted dataset cannot be profiled",
            )
        return self.profile_jobs.start(dataset_id, principal.user_id, payload.model_dump())

    def descriptive_profile_status(
        self,
        dataset_id: str,
        job_id: str,
        principal: Principal,
    ) -> dict[str, Any]:
        self.get_asset(dataset_id, principal)
        return self.profile_jobs.status(dataset_id, principal.user_id, job_id)

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

    def visualize(
        self,
        dataset_id: str,
        payload: DataAssetVisualizationRequest,
        principal: Principal,
    ) -> dict[str, Any]:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deleted dataset cannot be visualized")
        return self.full_visualization.render(asset, payload, lambda asset_id: self.get_asset(asset_id, principal))

    def drill(
        self,
        dataset_id: str,
        payload: DataAssetDrillRequest,
        principal: Principal,
    ) -> dict[str, Any]:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deleted dataset cannot be drilled")
        return self.full_visualization.drill(
            asset,
            payload,
            lambda asset_id: self.get_asset(asset_id, principal),
        )

    def visualization_groups(
        self,
        dataset_id: str,
        payload: DataAssetVisualizationGroupsRequest,
        principal: Principal,
    ) -> dict[str, Any]:
        asset = self.get_asset(dataset_id, principal)
        if asset.status == DataAssetStatus.DELETED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deleted dataset cannot be visualized")
        return self.full_visualization.group_values(
            asset,
            payload.column,
            payload.limit,
            lambda asset_id: self.get_asset(asset_id, principal),
        )

    def analyze_time_series(
        self,
        dataset_id: str,
        payload: TimeSeriesAnalysisRequest,
        principal: Principal,
    ) -> dict[str, Any]:
        asset = self.get_asset(dataset_id, principal)
        connection = self.full_visualization.store.connect(asset)
        relation = self.full_visualization.store.relation_sql(asset, lambda asset_id: self.get_asset(asset_id, principal))
        try:
            columns = self.full_visualization._columns(connection, relation)
            result = self.time_series.analyze(connection, relation, payload, columns)
            return {
                "dataset_id": asset.id,
                "time_column": payload.time_column,
                "value_column": payload.value_column,
                **result,
            }
        finally:
            connection.close()

    def start_time_series_analysis(self, dataset_id: str, payload: TimeSeriesAnalysisRequest, principal: Principal) -> dict[str, Any]:
        self.get_asset(dataset_id, principal)
        return self.time_series_jobs.start(dataset_id, principal.user_id, payload.model_dump())

    def time_series_analysis_status(self, dataset_id: str, job_id: str, principal: Principal) -> dict[str, Any]:
        self.get_asset(dataset_id, principal)
        return self.time_series_jobs.status(dataset_id, principal.user_id, job_id)

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
