from pathlib import Path

from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.schemas import DataAssetVisualizationRequest
from app.modules.datasets.sources import CsvFileDatasetSource
from app.modules.datasets.visualizations import FullDatasetVisualization


def visualization_fixture(tmp_path: Path) -> tuple[FullDatasetVisualization, DataAsset]:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "visualization-dataset"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "data.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        output.write("bucket,species,value,x,y\n")
        for index in range(10_000):
            species = "setosa" if index % 2 == 0 else "virginica"
            value = 10 if index < 5_000 else 30
            output.write(f"{index % 5},{species},{value},{index % 100},{(index % 100) * 2}\n")
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

    assert preview["row_count"] == 5
    assert [column["name"] for column in preview["columns"]] == ["bucket", "species", "records", "Sum value"]
    assert all(record["species"] == "virginica" for record in preview["records"])
    assert sum(record["records"] for record in preview["records"]) == 5_000


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
