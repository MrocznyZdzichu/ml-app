import math
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.schemas import DataAssetVisualizationRequest, TimeSeriesAnalysisRequest
from app.modules.datasets.sources import CsvFileDatasetSource
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer
from app.modules.datasets.visualizations import FullDatasetVisualization
from app.modules.analysis import time_series_jobs
from app.modules.analysis.time_series_jobs import TimeSeriesAnalysisJobs


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def setex(self, key: str, _seconds: int, value: str) -> None:
        self.values[key] = value.encode()

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)


def time_series_fixture(tmp_path: Path) -> tuple[ColumnarDatasetStore, DataAsset]:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "time-series"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "data.csv"
    start = datetime(2025, 1, 1, tzinfo=UTC)
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        output.write("timestamp,value,driver,inverse_driver\n")
        for index in range(240):
            effective_index = index + (1 if index >= 120 else 0)
            timestamp = start + timedelta(hours=effective_index)
            if index == 180:
                timestamp = start + timedelta(hours=180)
            value = 20 + 4 * math.sin(2 * math.pi * index / 24) + 0.01 * index
            output.write(f"{timestamp.isoformat().replace('+00:00', 'Z')},{value:.6f},{index % 7},{-(index % 7)}\n")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="time-series",
        owner_id="owner",
        name="time-series",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )
    return ColumnarDatasetStore(repository), asset


def test_full_dataset_time_series_analysis_reports_cadence_gaps_acf_and_seasonality(tmp_path: Path) -> None:
    store, asset = time_series_fixture(tmp_path)
    connection = store.connect(asset)
    relation = store.relation_sql(asset)
    try:
        columns = FullDatasetVisualization._columns(connection, relation)
        result = FullDatasetTimeSeriesAnalyzer(store).analyze(connection, relation, TimeSeriesAnalysisRequest(
            time_column="timestamp",
            value_column="value",
            max_lag=48,
            seasonal_period=24,
            rolling_window=12,
            max_points=120,
            driver_column="driver",
            driver_columns=["driver", "inverse_driver"],
        ), columns)
    finally:
        connection.close()

    assert result["row_count"] == 240
    assert result["valid_count"] == 240
    assert result["summary"]["median_interval_seconds"] == 3600
    assert result["summary"]["gap_count"] == 2
    assert result["summary"]["duplicate_timestamp_count"] == 1
    assert len(result["autocorrelation"]) == 48
    assert len(result["cross_correlation"]) == 49
    assert {item["driver_column"] for item in result["driver_relationships"]} == {"driver", "inverse_driver"}
    assert result["driver_relationships"][0]["strongest_lag"] is not None
    assert result["autocorrelation"][23]["correlation"] > 0.9
    assert result["summary"]["suggested_seasonal_period"] == 24
    assert len(result["seasonal_profile"]) == 24
    assert len(result["decomposition"]) <= 60
    assert {"observed", "trend", "seasonal", "residual"}.issubset(result["decomposition"][0])
    assert len(result["difference_series"]) <= 60
    assert result["difference_series"][0]["difference"] is not None
    assert len(result["series"]) <= 60
    assert sum(point["count"] for point in result["series"]) == 240
    assert len(result["feature_preview"]) == 100
    assert result["feature_preview"][0]["position"] == 1
    assert result["feature_preview"][-1]["position"] == 240
    assert result["feature_preview"][1]["lag_1"] is not None


def test_time_series_visualizations_return_bounded_full_dataset_points(tmp_path: Path) -> None:
    store, asset = time_series_fixture(tmp_path)
    visualization = FullDatasetVisualization(store)
    series = visualization.render(asset, DataAssetVisualizationRequest(
        kind="time_series", x="timestamp", y="value", max_points=120, rolling_window=12,
    ))
    acf = visualization.render(asset, DataAssetVisualizationRequest(
        kind="autocorrelation", x="timestamp", y="value", max_lag=36,
    ))
    lag_relationship = visualization.render(asset, DataAssetVisualizationRequest(
        kind="lag_relationship", x="timestamp", y="value", driver_column="driver", max_lag=36,
    ))

    assert series["scanned_row_count"] == 240
    assert series["valid_count"] == 240
    assert set(series["series"]) == {"Observed", "Rolling mean (12 bins)"}
    assert len(series["points"]) <= 120
    assert len(acf["points"]) == 36
    assert acf["points"][0]["xLabel"] == "Lag 1"
    assert len(lag_relationship["points"]) == 37
    assert lag_relationship["points"][0]["xLabel"] == "Lag 0"


def test_time_series_job_records_ownership_and_submits_full_options(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis()
    submitted: dict[str, object] = {}
    monkeypatch.setattr(time_series_jobs.time_series_analysis_dataset, "apply_async", lambda **kwargs: submitted.update(kwargs))
    monkeypatch.setattr(time_series_jobs, "uuid4", lambda: "time-job-1")
    jobs = TimeSeriesAnalysisJobs(fake_redis)

    result = jobs.start("dataset-1", "owner-1", {"time_column": "timestamp", "value_column": "value"})

    assert result["job_id"] == "time-job-1"
    assert submitted["task_id"] == "time-job-1"
    assert json.loads(fake_redis.values["time-series-analysis-owner:time-job-1"]) == {"dataset_id": "dataset-1", "owner_id": "owner-1"}


def test_time_series_job_rejects_cross_owner_polling() -> None:
    fake_redis = FakeRedis()
    fake_redis.setex("time-series-analysis-owner:time-job-1", 3600, json.dumps({"dataset_id": "dataset-1", "owner_id": "owner-1"}))
    jobs = TimeSeriesAnalysisJobs(fake_redis)

    with pytest.raises(HTTPException) as error:
        jobs.status("dataset-1", "owner-2", "time-job-1")

    assert error.value.status_code == 404
