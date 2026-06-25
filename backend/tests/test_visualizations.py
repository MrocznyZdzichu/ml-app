from pathlib import Path

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.schemas import (
    DataAssetDrillRequest,
    DataAssetVisualizationRead,
    DataAssetVisualizationRequest,
)
from app.modules.datasets.sources import CsvFileDatasetSource
from app.modules.datasets.visualizations import FullDatasetVisualization


class QueryTrackingConnection:
    def __init__(self, connection: object, statements: list[str]) -> None:
        self.connection = connection
        self.statements = statements

    def execute(self, query: str, parameters: list[object] | None = None) -> object:
        self.statements.append(" ".join(query.split()))
        if parameters is None:
            return self.connection.execute(query)  # type: ignore[attr-defined,no-any-return]
        return self.connection.execute(query, parameters)  # type: ignore[attr-defined,no-any-return]

    def close(self) -> None:
        self.connection.close()  # type: ignore[attr-defined]


def track_visualization_queries(
    visualization: FullDatasetVisualization,
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    statements: list[str] = []
    original_connect = visualization.store.connect
    monkeypatch.setattr(
        visualization.store,
        "connect",
        lambda asset: QueryTrackingConnection(original_connect(asset), statements),
    )
    return statements


def visualization_fixture(tmp_path: Path) -> tuple[FullDatasetVisualization, DataAsset]:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "visualization-dataset"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "data.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        output.write("bucket,species,value,x,y,segment\n")
        for index in range(10_000):
            species = "setosa" if index % 2 == 0 else "virginica"
            value = 10 if index < 5_000 else 30
            output.write(f"{index % 5},{species},{value},{index % 100},{(index % 100) * 2},segment-{index}\n")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="visualization-dataset",
        owner_id="owner",
        name="visualization",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )
    return FullDatasetVisualization(ColumnarDatasetStore(repository)), asset


def test_grouped_visualization_scans_every_row_and_supports_multiple_metrics(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="line",
        x="bucket",
        y="value",
        group="species",
        aggregations=["average", "median", "std"],
    ))

    assert result["row_count"] == 10_000
    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert result["execution_mode"] == "full_dataset"
    assert len(result["series"]) == 6
    assert {point["aggregation"] for point in result["points"]} == {"average", "median", "std"}
    assert all(point["y"] == 20 for point in result["points"] if point["aggregation"] in {"average", "median"})


def test_category_bars_support_full_dataset_group_series(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="bar",
        x="bucket",
        y="value",
        group="species",
        aggregations=["average"],
    ))

    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert result["series"] == ["setosa", "virginica"]
    assert {point["group"] for point in result["points"]} == {"setosa", "virginica"}


def test_pca_projection_fits_complete_full_dataset_and_colors_classes(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="projection",
        feature_columns=["value", "x", "y"],
        target_column="species",
        max_points=500,
    ))

    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert result["reduction_metadata"]["fit_scope"] == "full_dataset_complete_cases"
    assert result["reduction_metadata"]["target_type"] == "categorical"
    assert result["reduction_metadata"]["feature_columns"] == ["value", "x", "y"]
    assert len(result["reduction_metadata"]["explained_variance_ratio"]) == 2
    assert set(result["series"]) == {"setosa", "virginica"}
    assert 0 < len(result["points"]) <= 500


def test_pca_projection_aggregates_continuous_target_into_gradient_values(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="projection",
        feature_columns=["bucket", "x", "y"],
        target_column="value",
        max_points=200,
    ))

    assert result["reduction_metadata"]["target_type"] == "continuous"
    assert result["series"] == ["Target gradient"]
    assert all(point["targetValue"] is not None for point in result["points"])


def test_pca_projection_rejects_non_numeric_features(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    with pytest.raises(HTTPException, match="feature columns must be numeric"):
        visualization.render(asset, DataAssetVisualizationRequest(
            kind="projection",
            feature_columns=["species", "x"],
        ))


def test_visualization_rejects_categorical_measure_even_for_count(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)

    with pytest.raises(HTTPException, match="Visualization measure must be numeric"):
        visualization.render(asset, DataAssetVisualizationRequest(
            kind="bar",
            x="bucket",
            y="species",
            aggregations=["count"],
        ))


def test_drill_filters_full_dataset_with_half_open_range_and_group(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    request = DataAssetDrillRequest.model_validate({
        "filters": {
            "x": {"operator": "between", "values": ["0", "10"]},
            "species": {"operator": "equals", "value": "setosa"},
        },
        "limit": 25,
    })
    result = visualization.drill(asset, request)

    assert result["row_count"] == 500
    assert result["returned_count"] == 25
    assert all(0 <= row["x"] < 10 for row in result["records"])
    assert {row["species"] for row in result["records"]} == {"setosa"}


def test_drill_rejects_unknown_filter_columns(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)

    with pytest.raises(HTTPException, match="Unknown drill filter column"):
        visualization.drill(asset, DataAssetDrillRequest.model_validate({
            "filters": {"does_not_exist": {"operator": "equals", "value": "x"}},
        }))


def test_drill_between_requires_exactly_two_bounds() -> None:
    with pytest.raises(ValueError, match="exactly two values"):
        DataAssetDrillRequest.model_validate({
            "filters": {"x": {"operator": "between", "values": ["1"]}},
        })


def test_drill_requires_at_least_one_source_filter() -> None:
    with pytest.raises(ValueError, match="at least 1 item"):
        DataAssetDrillRequest.model_validate({"filters": {}})


def test_visualization_rejects_series_column_that_duplicates_an_axis(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)

    with pytest.raises(HTTPException, match="Series column must be different from chart axes"):
        visualization.render(asset, DataAssetVisualizationRequest(
            kind="bar",
            x="species",
            y="value",
            group="species",
        ))


def test_scatter_bounds_high_cardinality_groups_before_python_materialization(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)

    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="scatter",
        x="x",
        y="y",
        group="segment",
        max_points=50,
    ))

    assert result["valid_count"] == 10_000
    assert result["truncated"] is True
    assert len(result["points"]) == 50


def test_scatter_trend_requires_bounded_group_selection(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)

    with pytest.raises(HTTPException, match="at most 100 selected groups"):
        visualization.render(asset, DataAssetVisualizationRequest(
            kind="scatter",
            x="x",
            y="y",
            group="segment",
            trend="linear",
        ))


def test_x_epsilon_groups_continuous_axis_into_centered_full_dataset_buckets(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="line",
        x="x",
        y="y",
        group="species",
        aggregations=["average"],
        x_epsilon=5,
    ))

    centers = sorted({point["x"] for point in result["points"]})
    first_bucket = [point for point in result["points"] if point["x"] == 5]
    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert centers == [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]
    assert {point["group"]: point["y"] for point in first_bucket} == {"setosa": 8, "virginica": 10}
    assert all(point["xRange"] == [0, 10] for point in first_bucket)
    assert all(point["count"] == 500 for point in first_bucket)


def test_x_epsilon_uses_half_open_boundaries_for_decimal_values(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "epsilon-boundary"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "epsilon.csv"
    csv_path.write_text("x,y\n0.8,1\n1.0,3\n1.19,5\n1.2,100\n", encoding="utf-8")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="epsilon-boundary",
        owner_id="owner",
        name="epsilon",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )
    result = FullDatasetVisualization(ColumnarDatasetStore(repository)).render(
        asset,
        DataAssetVisualizationRequest(kind="line", x="x", y="y", aggregations=["average"], x_epsilon=0.2),
    )

    by_center = {point["x"]: point for point in result["points"]}
    assert by_center[1]["y"] == 3
    assert by_center[1]["count"] == 3
    assert by_center[1]["xRange"] == [0.8, 1.2]
    assert by_center[1.4]["y"] == 100
    assert by_center[1.4]["count"] == 1


def test_visualization_group_selection_and_values_use_full_dataset(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    groups = visualization.group_values(asset, "species", 100)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="line",
        x="bucket",
        y="value",
        group="species",
        aggregations=["average"],
        selected_groups=["setosa"],
    ))

    assert set(groups["values"]) == {"setosa", "virginica"}
    assert result["valid_count"] == 5_000
    assert result["series"] == ["setosa"]


def test_kpi_filters_full_dataset_by_selected_values(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="kpi",
        y="value",
        group="species",
        selected_groups=["setosa"],
        aggregations=["sum"],
    ))

    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 5_000
    assert result["kpi"] == 100_000


def test_boxplot_returns_grouped_quartiles_and_tukey_whiskers(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="boxplot",
        x="value",
        group="species",
    ))

    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert result["series"] == ["setosa", "virginica"]
    assert len(result["points"]) == 2
    for point in result["points"]:
        assert point["count"] == 5_000
        assert point["minimum"] == 10
        assert point["q1"] == 10
        assert point["median"] == 20
        assert point["q3"] == 30
        assert point["maximum"] == 30
        assert point["lowerWhisker"] == 10
        assert point["upperWhisker"] == 30
        assert point["outlierCount"] == 0
        assert point["xRange"] == [10, 30]
    serialized = DataAssetVisualizationRead.model_validate(result).model_dump(by_alias=True, exclude_none=True)
    assert serialized["points"][0]["lowerWhisker"] == 10
    assert serialized["points"][0]["upperWhisker"] == 30
    assert serialized["points"][0]["outlierCount"] == 0


def test_boxplot_whiskers_exclude_outliers_without_materializing_them(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "boxplot-outlier"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "values.csv"
    csv_path.write_text("value\n1\n2\n3\n4\n100\n", encoding="utf-8")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="boxplot-outlier",
        owner_id="owner",
        name="boxplot",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )

    result = FullDatasetVisualization(ColumnarDatasetStore(repository)).render(
        asset,
        DataAssetVisualizationRequest(kind="boxplot", x="value"),
    )

    point = result["points"][0]
    assert point["minimum"] == 1
    assert point["q1"] == 2
    assert point["median"] == 3
    assert point["q3"] == 4
    assert point["maximum"] == 100
    assert point["lowerWhisker"] == 1
    assert point["upperWhisker"] == 4
    assert point["outlierCount"] == 1


def test_visualization_uses_trusted_row_count_without_an_extra_full_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    statements = track_visualization_queries(visualization, monkeypatch)
    result = visualization.render(asset, DataAssetVisualizationRequest(kind="kpi", y="value"))

    assert result["row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert not any(statement.upper().startswith("SELECT COUNT(*) FROM") for statement in statements)


@pytest.mark.parametrize(("kind", "expensive_operation"), [
    ("histogram", "STDDEV_SAMP"),
    ("boxplot", "QUANTILE_CONT"),
])
def test_distribution_views_reject_high_cardinality_before_expensive_statistics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    expensive_operation: str,
) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    statements = track_visualization_queries(visualization, monkeypatch)
    with pytest.raises(HTTPException, match="at most 20 selected groups"):
        visualization.render(asset, DataAssetVisualizationRequest(kind=kind, x="value", group="segment"))

    normalized_statements = [statement.upper() for statement in statements]
    assert any("SELECT DISTINCT" in statement for statement in normalized_statements)
    assert not any(expensive_operation in statement for statement in normalized_statements)


def test_visualization_limits_parallel_heavy_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    visualization = FullDatasetVisualization()
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def fake_render(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        return {}

    monkeypatch.setattr(visualization, "_render_in_execution_slot", fake_render)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(visualization.render, object(), object()) for _ in range(6)]
        for future in futures:
            future.result()

    assert maximum_active == min(settings.visualization_max_concurrency, 6)


def test_distribution_returns_grouped_full_dataset_kde_curves(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="histogram",
        x="value",
        group="species",
        bins=80,
    ))

    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert result["series"] == ["setosa", "virginica"]
    assert result["approximate"] is True
    assert result["approximation_method"] == "binned_gaussian_kde"
    assert len(result["points"]) == 160
    for group in result["series"]:
        curve = [point for point in result["points"] if point["group"] == group]
        assert len(curve) == 80
        assert all(point["count"] == 5_000 for point in curve)
        assert all(point["y"] >= 0 for point in curve)
        area = sum(
            (left["y"] + right["y"]) * (right["x"] - left["x"]) / 2
            for left, right in zip(curve, curve[1:])
        )
        assert area == pytest.approx(1, abs=0.02)


def test_distribution_group_selection_limits_the_full_dataset_curve(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="histogram",
        x="value",
        group="species",
        selected_groups=["setosa"],
        bins=40,
    ))

    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 5_000
    assert result["series"] == ["setosa"]
    assert len(result["points"]) == 40
    assert {point["group"] for point in result["points"]} == {"setosa"}


def test_distribution_does_not_extend_nonnegative_data_below_zero(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "nonnegative-distribution"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "prices.csv"
    csv_path.write_text(
        "price\n" + "\n".join(["135000"] * 50 + ["3200000"] * 50) + "\n",
        encoding="utf-8",
    )
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="nonnegative-distribution",
        owner_id="owner",
        name="prices",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )

    result = FullDatasetVisualization(ColumnarDatasetStore(repository)).render(
        asset,
        DataAssetVisualizationRequest(kind="histogram", x="price", bins=80),
    )

    assert min(point["x"] for point in result["points"]) == 0
    assert min(point["xRange"][0] for point in result["points"]) == 0
    assert all(point["x"] >= 0 for point in result["points"])
    assert all(point["xRange"][0] >= 0 for point in result["points"])


def test_grouped_visualization_reports_full_valid_count_when_output_is_bounded(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="line",
        x="x",
        y="value",
        group="species",
        aggregations=["average"],
        max_points=50,
    ))

    assert result["truncated"] is True
    assert len(result["points"]) == 50
    assert sum(point["count"] for point in result["points"]) == 5_000
    assert result["valid_count"] == 10_000


def test_scatter_uses_full_dataset_density_bins(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="scatter",
        x="x",
        y="y",
        group="species",
        max_points=500,
    ))

    assert result["scanned_row_count"] == 10_000
    assert result["valid_count"] == 10_000
    assert len(result["points"]) <= 500
    assert sum(point["count"] for point in result["points"]) == 10_000


def test_scatter_supports_independent_x_and_y_epsilon_buckets(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="scatter",
        x="x",
        y="y",
        group="species",
        x_epsilon=5,
        y_epsilon=20,
        max_points=500,
    ))

    assert result["valid_count"] == 10_000
    assert sum(point["count"] for point in result["points"]) == 10_000
    assert {point["x"] for point in result["points"]} == set(range(5, 100, 10))
    assert {point["y"] for point in result["points"]} == {20, 60, 100, 140, 180}
    assert all(point["xRange"][1] - point["xRange"][0] == 10 for point in result["points"])
    assert all(point["yRange"][1] - point["yRange"][0] == 40 for point in result["points"])


def test_scatter_rejects_epsilon_too_small_for_safe_bucket_indices(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)

    with pytest.raises(HTTPException, match="X epsilon is too small"):
        visualization.render(asset, DataAssetVisualizationRequest(
            kind="scatter", x="x", y="y", x_epsilon=1e-20,
        ))


def test_scatter_truncation_keeps_dense_regions_instead_of_coordinate_prefix(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "dense-tail"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "data.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        output.write("x,y\n")
        for value in range(100):
            output.write(f"{value},{value}\n")
        for _ in range(1_000):
            output.write("999,999\n")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="dense-tail", owner_id="owner", name="dense-tail", source_type=SourceType.FILE,
        format="csv", location_uri=f"file://{csv_path.as_posix()}", row_count=row_count,
        has_header=has_header, status=DataAssetStatus.READY, metadata={"source_schema": schema},
    )
    result = FullDatasetVisualization(ColumnarDatasetStore(repository)).render(
        asset,
        DataAssetVisualizationRequest(kind="scatter", x="x", y="y", x_epsilon=0.25, y_epsilon=0.25, max_points=50),
    )

    assert result["truncated"] is True
    assert result["valid_count"] == 1_100
    assert len(result["points"]) == 50
    assert any(point["count"] == 1_000 and point["xRange"] == [999, 999.5] for point in result["points"])


def test_visualization_rejects_scatter_only_options_for_other_chart_types(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)

    with pytest.raises(HTTPException, match="only for scatter"):
        visualization.render(asset, DataAssetVisualizationRequest(
            kind="line", x="x", y="y", y_epsilon=1,
        ))
    with pytest.raises(HTTPException, match="only for scatter"):
        visualization.render(asset, DataAssetVisualizationRequest(
            kind="bar", x="bucket", y="value", trend="linear",
        ))


def test_visualization_number_serialization_rejects_non_finite_values() -> None:
    assert FullDatasetVisualization._number(float("nan")) is None
    assert FullDatasetVisualization._number(float("inf")) is None
    assert FullDatasetVisualization._number(float("-inf")) is None


def test_visualization_response_contract_preserves_frontend_field_aliases(tmp_path: Path) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="scatter", x="x", y="y", trend="linear",
    ))

    serialized = DataAssetVisualizationRead.model_validate(result).model_dump(by_alias=True)

    assert serialized["points"][0]["xLabel"].startswith("x:")
    assert "xRange" in serialized["points"][0]
    assert serialized["trends"][0]["kind"] == "linear"
    assert serialized["trends"][0]["parameters"]["slope"] == pytest.approx(2)


@pytest.mark.parametrize("trend", ["linear", "spline", "polynomial"])
def test_scatter_trend_is_fitted_from_full_data_per_group(tmp_path: Path, trend: str) -> None:
    visualization, asset = visualization_fixture(tmp_path)
    result = visualization.render(asset, DataAssetVisualizationRequest(
        kind="scatter",
        x="x",
        y="y",
        group="species",
        trend=trend,
        polynomial_degree=3,
    ))

    assert {curve["series"] for curve in result["trends"]} == {"setosa", "virginica"}
    assert all(curve["valid_count"] == 5_000 for curve in result["trends"])
    assert all(len(curve["points"]) == 80 for curve in result["trends"])
    assert all(abs(point["y"] - 2 * point["x"]) < 1e-6 for curve in result["trends"] for point in curve["points"])
    if trend == "linear":
        assert all(curve["parameters"]["slope"] == pytest.approx(2) for curve in result["trends"])
        assert all(curve["parameters"]["intercept"] == pytest.approx(0, abs=1e-8) for curve in result["trends"])
        assert all(curve["r_squared"] == pytest.approx(1) for curve in result["trends"])
    elif trend == "polynomial":
        assert all(curve["parameters"]["coefficients"][0] == pytest.approx(0, abs=1e-8) for curve in result["trends"])
        assert all(curve["parameters"]["coefficients"][1] == pytest.approx(2) for curve in result["trends"])
        assert all(curve["parameters"]["degree"] == 3 for curve in result["trends"])
    else:
        assert all(curve["parameters"] == {"nodes": 24, "source_bins": 24} for curve in result["trends"])


def test_scatter_exponential_trend_ignores_nonpositive_y_and_reports_scope(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "exponential"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "data.csv"
    csv_path.write_text("x,y,group\n0,3,a\n1,6,a\n2,12,a\n3,-1,a\n0,2,b\n1,4,b\n2,8,b\n", encoding="utf-8")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="exponential",
        owner_id="owner",
        name="exponential",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )
    result = FullDatasetVisualization(ColumnarDatasetStore(repository)).render(
        asset,
        DataAssetVisualizationRequest(kind="scatter", x="x", y="y", group="group", trend="exponential"),
    )

    by_group = {curve["series"]: curve for curve in result["trends"]}
    assert by_group["a"]["valid_count"] == 3
    assert by_group["b"]["valid_count"] == 3
    assert by_group["a"]["points"][0]["y"] == pytest.approx(3)
    assert by_group["a"]["points"][-1]["y"] == pytest.approx(12)
    assert by_group["a"]["parameters"]["amplitude"] == pytest.approx(3)
    assert by_group["a"]["parameters"]["rate"] == pytest.approx(0.69314718056)
    assert by_group["a"]["r_squared"] == pytest.approx(1)
    assert by_group["a"]["fit_space"] == "log_y"


def test_sql_data_view_is_materialized_and_visualized(tmp_path: Path) -> None:
    visualization, source = visualization_fixture(tmp_path)
    view = DataAsset(
        id="sql-view",
        owner_id="owner",
        name="setosa-summary",
        source_type=SourceType.VIEW,
        format="view",
        location_uri=f"view://{source.id}",
        status=DataAssetStatus.READY,
        metadata={"data_view": {
            "source_dataset_id": source.id,
            "definition": {
                "kind": "sql",
                "sql": "SELECT bucket, species, avg(value) AS avg_value FROM visualization WHERE species = 'setosa' GROUP BY bucket, species",
            },
        }},
    )
    loader = lambda asset_id: source if asset_id == source.id else view

    preview = visualization.preview(view, 10, loader)
    result = visualization.render(view, DataAssetVisualizationRequest(
        kind="line", x="bucket", y="avg_value", group="species", aggregations=["average"]
    ), loader)

    assert preview["row_count"] == 5
    assert {column["name"] for column in preview["columns"]} == {"bucket", "species", "avg_value"}
    assert result["scanned_row_count"] == 5
    assert result["series"] == ["setosa"]
    assert all(point["y"] == 20 for point in result["points"])


def test_browser_data_view_pushes_filters_and_grouping_to_duckdb(tmp_path: Path) -> None:
    visualization, source = visualization_fixture(tmp_path)
    view = DataAsset(
        id="browser-view",
        owner_id="owner",
        name="browser-summary",
        source_type=SourceType.VIEW,
        format="view",
        location_uri=f"view://{source.id}",
        status=DataAssetStatus.READY,
        metadata={"data_view": {
            "source_dataset_id": source.id,
            "definition": {
                "kind": "browser",
                "filters": {"species": {"operator": "equals", "value": "virginica"}},
                "grouping": {
                    "bucket": {"role": "group", "aggregate": "count_non_empty"},
                    "species": {"role": "group", "aggregate": "count_non_empty"},
                    "value": {"role": "aggregate", "aggregate": "sum"},
                },
                "sort_rules": [{"column": "bucket", "direction": "asc"}],
            },
        }},
    )
    loader = lambda asset_id: source if asset_id == source.id else view

    preview = visualization.preview(view, 10, loader)
    drill = visualization.drill(view, DataAssetDrillRequest.model_validate({
        "filters": {"bucket": {"operator": "equals", "value": "2"}},
    }), loader)

    assert preview["row_count"] == 5
    assert [column["name"] for column in preview["columns"]] == ["bucket", "species", "records", "Sum value"]
    assert all(record["species"] == "virginica" for record in preview["records"])
    assert sum(record["records"] for record in preview["records"]) == 5_000
    assert drill["row_count"] == 1
    assert drill["records"][0]["bucket"] == 2
    assert drill["records"][0]["records"] == 1_000


def test_nested_data_views_resolve_recursively(tmp_path: Path) -> None:
    visualization, source = visualization_fixture(tmp_path)
    filtered = DataAsset(
        id="filtered-view",
        owner_id="owner",
        name="filtered source",
        source_type=SourceType.VIEW,
        format="view",
        status=DataAssetStatus.READY,
        metadata={"data_view": {
            "source_dataset_id": source.id,
            "definition": {"kind": "browser", "filters": {"species": {"operator": "equals", "value": "setosa"}}},
        }},
    )
    nested = DataAsset(
        id="nested-view",
        owner_id="owner",
        name="nested",
        source_type=SourceType.VIEW,
        format="view",
        status=DataAssetStatus.READY,
        metadata={"data_view": {
            "source_dataset_id": filtered.id,
            "definition": {"kind": "sql", "sql": 'SELECT bucket, avg(value) AS avg_value FROM "filtered source" GROUP BY bucket'},
        }},
    )
    assets = {source.id: source, filtered.id: filtered, nested.id: nested}

    preview = visualization.preview(nested, 10, lambda asset_id: assets[asset_id])

    assert preview["row_count"] == 5
    assert all(record["avg_value"] == 20 for record in preview["records"])


def test_data_view_can_continue_into_descriptive_analysis(tmp_path: Path) -> None:
    visualization, source = visualization_fixture(tmp_path)
    view = DataAsset(
        id="profile-view",
        owner_id="owner",
        name="profile view",
        source_type=SourceType.VIEW,
        format="view",
        status=DataAssetStatus.READY,
        metadata={"data_view": {
            "source_dataset_id": source.id,
            "definition": {"kind": "browser", "filters": {"species": {"operator": "equals", "value": "setosa"}}},
        }},
    )
    loader = lambda asset_id: source if asset_id == source.id else view

    result = FullDatasetProfiler(visualization.store).profile(
        view,
        {"include_target_relations": False, "include_segments": False, "include_graphic_summaries": False},
        loader,
    )
    value_profile = next(profile for profile in result["profile"]["columnProfiles"] if profile["name"] == "value")

    assert result["row_count"] == 5_000
    assert value_profile["mean"] == 20
