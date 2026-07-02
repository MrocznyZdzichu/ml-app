from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.security import Principal, require_user
from app.modules.datasets.schemas import (
    DataAssetCreate,
    DataAssetDrillRequest,
    DataAssetMetadataUpdate,
    DataAssetPreviewRead,
    DataAssetProfileRead,
    DataAssetProfileRequest,
    DataAssetRead,
    DataAssetSqlQueryRequest,
    DataAssetVisualizationGroupsRead,
    DataAssetVisualizationGroupsRequest,
    DataAssetVisualizationRead,
    DataAssetVisualizationRequest,
    DataViewCreate,
    FullDescriptiveProfileJobRead,
    FullDescriptiveProfileRequest,
    TimeSeriesAnalysisRead,
    TimeSeriesAnalysisJobRead,
    TimeSeriesAnalysisRequest,
)
from app.modules.datasets.service import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])
service = DatasetService()


@router.post("", response_model=DataAssetRead, status_code=201)
def register_dataset(
    payload: DataAssetCreate,
    principal: Principal = Depends(require_user),
) -> DataAssetRead:
    return DataAssetRead.model_validate(service.register(payload, principal))


@router.post("/upload", response_model=DataAssetRead, status_code=201)
def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    description: str = Form(default=""),
    tags: str = Form(default=""),
    principal: Principal = Depends(require_user),
) -> DataAssetRead:
    tag_values = [tag.strip() for tag in tags.split(",") if tag.strip()]
    return DataAssetRead.model_validate(
        service.upload_file_stream(
            stream=file.file,
            filename=file.filename or "dataset",
            principal=principal,
            name=name,
            description=description,
            tags=tag_values,
        )
    )


@router.post("/views", response_model=DataAssetRead, status_code=201)
def create_data_view(
    payload: DataViewCreate,
    principal: Principal = Depends(require_user),
) -> DataAssetRead:
    return DataAssetRead.model_validate(service.create_view(payload, principal))


@router.get("", response_model=list[DataAssetRead])
def list_datasets(principal: Principal = Depends(require_user)) -> list[DataAssetRead]:
    return [DataAssetRead.model_validate(asset) for asset in service.list_assets(principal)]


@router.get("/{dataset_id}/preview", response_model=DataAssetPreviewRead)
def preview_dataset(
    dataset_id: str,
    limit: int = 5000,
    principal: Principal = Depends(require_user),
) -> DataAssetPreviewRead:
    return service.preview(dataset_id, principal, max(1, min(limit, 50_000)))


@router.post("/{dataset_id}/query", response_model=DataAssetPreviewRead)
def query_dataset(
    dataset_id: str,
    payload: DataAssetSqlQueryRequest,
    principal: Principal = Depends(require_user),
) -> DataAssetPreviewRead:
    return service.query(dataset_id, payload, principal)


@router.post(
    "/{dataset_id}/visualization",
    response_model=DataAssetVisualizationRead,
    response_model_exclude_none=True,
)
def visualize_dataset(
    dataset_id: str,
    payload: DataAssetVisualizationRequest,
    principal: Principal = Depends(require_user),
) -> DataAssetVisualizationRead:
    return DataAssetVisualizationRead.model_validate(service.visualize(dataset_id, payload, principal))


@router.post("/{dataset_id}/drill", response_model=DataAssetPreviewRead)
def drill_dataset(
    dataset_id: str,
    payload: DataAssetDrillRequest,
    principal: Principal = Depends(require_user),
) -> DataAssetPreviewRead:
    return DataAssetPreviewRead.model_validate(service.drill(dataset_id, payload, principal))


@router.post("/{dataset_id}/visualization/groups", response_model=DataAssetVisualizationGroupsRead)
def visualization_groups(
    dataset_id: str,
    payload: DataAssetVisualizationGroupsRequest,
    principal: Principal = Depends(require_user),
) -> DataAssetVisualizationGroupsRead:
    return DataAssetVisualizationGroupsRead.model_validate(service.visualization_groups(dataset_id, payload, principal))


@router.post("/{dataset_id}/time-series-analysis", response_model=TimeSeriesAnalysisJobRead, status_code=202)
def analyze_time_series(
    dataset_id: str,
    payload: TimeSeriesAnalysisRequest,
    principal: Principal = Depends(require_user),
) -> TimeSeriesAnalysisJobRead:
    return TimeSeriesAnalysisJobRead.model_validate(service.start_time_series_analysis(dataset_id, payload, principal))


@router.get("/{dataset_id}/time-series-analysis/{job_id}", response_model=TimeSeriesAnalysisJobRead)
def time_series_analysis_status(
    dataset_id: str,
    job_id: str,
    principal: Principal = Depends(require_user),
) -> TimeSeriesAnalysisJobRead:
    return TimeSeriesAnalysisJobRead.model_validate(service.time_series_analysis_status(dataset_id, job_id, principal))


@router.get("/{dataset_id}", response_model=DataAssetRead)
def get_dataset(dataset_id: str, principal: Principal = Depends(require_user)) -> DataAssetRead:
    return DataAssetRead.model_validate(service.get_asset(dataset_id, principal))


@router.patch("/{dataset_id}/metadata", response_model=DataAssetRead)
def update_dataset_metadata(
    dataset_id: str,
    payload: DataAssetMetadataUpdate,
    principal: Principal = Depends(require_user),
) -> DataAssetRead:
    return DataAssetRead.model_validate(service.update_metadata(dataset_id, payload, principal))


@router.delete("/{dataset_id}", response_model=DataAssetRead)
def delete_dataset(dataset_id: str, principal: Principal = Depends(require_user)) -> DataAssetRead:
    return DataAssetRead.model_validate(service.delete_asset(dataset_id, principal))


@router.post("/{dataset_id}/profile", response_model=DataAssetProfileRead)
def profile_dataset(
    dataset_id: str,
    payload: DataAssetProfileRequest,
    principal: Principal = Depends(require_user),
) -> DataAssetProfileRead:
    return service.profile(dataset_id, payload, principal)


@router.post("/{dataset_id}/descriptive-profile", response_model=FullDescriptiveProfileJobRead, status_code=202)
def descriptive_profile_dataset(
    dataset_id: str,
    payload: FullDescriptiveProfileRequest,
    principal: Principal = Depends(require_user),
) -> FullDescriptiveProfileJobRead:
    return FullDescriptiveProfileJobRead.model_validate(
        service.start_descriptive_profile(dataset_id, payload, principal)
    )


@router.get("/{dataset_id}/descriptive-profile/{job_id}", response_model=FullDescriptiveProfileJobRead)
def descriptive_profile_status(
    dataset_id: str,
    job_id: str,
    principal: Principal = Depends(require_user),
) -> FullDescriptiveProfileJobRead:
    return FullDescriptiveProfileJobRead.model_validate(
        service.descriptive_profile_status(dataset_id, job_id, principal)
    )
