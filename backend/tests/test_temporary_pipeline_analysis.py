from pathlib import Path

import duckdb
import pytest
from fastapi import HTTPException

from app.core.security import Principal
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.repository import InMemoryDatasetRepository
from app.modules.datasets.schemas import DataAssetProfileRequest, DataAssetVisualizationRequest
from app.modules.datasets.service import DatasetService
from app.modules.datasets.temporary import (
    TemporaryPipelineOutputResolver,
    temporary_pipeline_output_id,
)
from app.modules.datasets.visualizations import FullDatasetVisualization
from app.modules.pipelines.domain import PipelineRun, PipelineRunStatus, PipelineRunTrigger
from app.modules.pipelines.repository import InMemoryPipelineRepository
from app.modules.pipelines.run_preview import PipelineRunOutputReader


def _temporary_run(repository_root: Path) -> tuple[PipelineRun, Path]:
    output_path = repository_root / "users" / "owner-1" / "pipeline-runs" / "run-1" / "result.parquet"
    output_path.parent.mkdir(parents=True)
    connection = duckdb.connect()
    connection.execute(
        "COPY (SELECT range::INTEGER AS value, CASE WHEN range % 2 = 0 THEN 'even' ELSE 'odd' END AS category "
        "FROM range(100)) TO ? (FORMAT PARQUET)",
        [str(output_path)],
    )
    connection.close()
    return PipelineRun(
        id="run-1",
        owner_id="owner-1",
        pipeline_id="pipeline-1",
        pipeline_version_id="version-1",
        business_case_id="bc-1",
        status=PipelineRunStatus.SUCCEEDED,
        trigger_type=PipelineRunTrigger.MANUAL,
        is_dry_run=True,
        output_row_count=100,
        created_by="owner-1",
        output_manifest=[{
            "output_id": "result",
            "location_uri": f"file://{output_path.as_posix()}",
            "row_count": 100,
            "schema": [{"name": "value", "type": "INTEGER"}, {"name": "category", "type": "VARCHAR"}],
        }],
    ), output_path


def test_temporary_output_uses_existing_full_dataset_analysis_without_registration(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    run, _ = _temporary_run(repository_root)
    pipelines = InMemoryPipelineRepository()
    pipelines.add_run(run)
    resolver = TemporaryPipelineOutputResolver(
        repository=pipelines,
        output_reader=PipelineRunOutputReader(repository_root),
    )
    service = DatasetService(repository=InMemoryDatasetRepository(), temporary_outputs=resolver)
    store = ColumnarDatasetStore(repository_root)
    service.full_profiler = FullDatasetProfiler(store)
    service.full_visualization = FullDatasetVisualization(store)
    principal = Principal(user_id="owner-1", email="owner@example.com", display_name="Owner")
    asset_id = temporary_pipeline_output_id(run.id, "result")

    preview = service.preview(asset_id, principal, limit=10)
    visualization = service.full_visualization.render(
        service.get_asset(asset_id, principal),
        DataAssetVisualizationRequest(kind="histogram", x="value", bins=20),
    )

    assert service.list_assets(principal) == []
    assert preview.row_count == 100
    assert preview.returned_count == 10
    assert visualization["scanned_row_count"] == 100
    assert visualization["execution_mode"] == "full_dataset"
    assert visualization["points"]


def test_temporary_output_is_read_only_and_owner_scoped(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    run, _ = _temporary_run(repository_root)
    pipelines = InMemoryPipelineRepository()
    pipelines.add_run(run)
    resolver = TemporaryPipelineOutputResolver(
        repository=pipelines,
        output_reader=PipelineRunOutputReader(repository_root),
    )
    datasets = InMemoryDatasetRepository()
    service = DatasetService(repository=datasets, temporary_outputs=resolver)
    asset_id = temporary_pipeline_output_id(run.id, "result")
    owner = Principal(user_id="owner-1", email="owner@example.com", display_name="Owner")

    with pytest.raises(HTTPException) as hidden:
        service.get_asset(
            asset_id,
            Principal(user_id="owner-2", email="other@example.com", display_name="Other"),
        )
    assert hidden.value.status_code == 404

    with pytest.raises(HTTPException) as read_only:
        service.delete_asset(asset_id, owner)
    assert read_only.value.status_code == 409

    with pytest.raises(HTTPException) as immutable_profile_status:
        service.profile(asset_id, DataAssetProfileRequest(), owner)
    assert immutable_profile_status.value.status_code == 409

    persistent = service.get_asset(asset_id, owner)
    persistent.id = "persistent-dataset"
    persistent.metadata = {"temporary": True}
    datasets.add(persistent)
    assert service.profile(
        persistent.id,
        DataAssetProfileRequest(),
        owner,
    ).status == "queued"


def test_temporary_output_identifier_round_trips_reserved_characters(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    run, _ = _temporary_run(repository_root)
    output_id = "result:2026/a b"
    run.output_manifest[0]["output_id"] = output_id
    pipelines = InMemoryPipelineRepository()
    pipelines.add_run(run)
    resolver = TemporaryPipelineOutputResolver(
        repository=pipelines,
        output_reader=PipelineRunOutputReader(repository_root),
    )

    asset = resolver.resolve(temporary_pipeline_output_id(run.id, output_id), run.owner_id)

    assert asset.metadata["output_id"] == output_id


def test_temporary_output_identifier_selects_pipeline_step(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    run, first_path = _temporary_run(repository_root)
    second_path = first_path.with_name("second.parquet")
    duckdb.connect().execute(
        "COPY (SELECT 7 AS value) TO ? (FORMAT PARQUET)",
        [str(second_path)],
    ).close()
    run.output_manifest[0]["pipeline_step_id"] = "de_1"
    run.output_manifest.append({
        "pipeline_step_id": "fe_1",
        "output_id": "result",
        "location_uri": f"file://{second_path.as_posix()}",
        "row_count": 1,
        "schema": [{"name": "value", "type": "INTEGER"}],
    })
    pipelines = InMemoryPipelineRepository()
    pipelines.add_run(run)
    resolver = TemporaryPipelineOutputResolver(
        repository=pipelines,
        output_reader=PipelineRunOutputReader(repository_root),
    )

    asset = resolver.resolve(
        temporary_pipeline_output_id(run.id, "result", "fe_1"),
        run.owner_id,
    )

    assert asset.metadata["pipeline_step_id"] == "fe_1"
    assert asset.row_count == 1
