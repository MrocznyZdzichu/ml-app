from pathlib import Path

from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.sources import CsvFileDatasetSource


def test_full_profile_uses_rows_beyond_the_old_frontend_limit(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "large-dataset"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "large.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        output.write("value,target\n")
        for index in range(60_000):
            output.write(f"{0 if index < 50_000 else 60},{index % 2}\n")

    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="large-dataset",
        owner_id="owner",
        name="large",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={
            "source_schema": schema,
            "data_roles": {
                "target_column": "target",
                "column_roles": {"value": "feature_continuous", "target": "target"},
            },
        },
    )

    result = FullDatasetProfiler(ColumnarDatasetStore(repository)).profile(
        asset,
        {
            "target_column": "target",
            "target_type": "categorical",
            "comparison_column": "target",
            "comparison_type": "categorical",
            "include_target_relations": False,
            "include_segments": False,
            "include_graphic_summaries": False,
        },
    )

    value_profile = next(item for item in result["profile"]["columnProfiles"] if item["name"] == "value")
    assert result["row_count"] == 60_000
    assert value_profile["count"] == 60_000
    assert value_profile["mean"] == 10
    assert (dataset_dir / "dataset.mlapp.parquet").exists()


def test_lightweight_schema_does_not_materialize_parquet(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "schema-dataset"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "schema.csv"
    csv_path.write_text("value,target\n1,no\n2,yes\n", encoding="utf-8")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="schema-dataset",
        owner_id="owner",
        name="schema",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )

    preview = FullDatasetProfiler(ColumnarDatasetStore(repository)).schema(asset, limit=1)

    assert preview["row_count"] == 2
    assert preview["returned_count"] == 1
    assert not (dataset_dir / "dataset.mlapp.parquet").exists()


def test_full_profile_builds_relations_graphics_and_segments(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "complete-dataset"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "complete.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        output.write("region,channel,score,amount\n")
        for index in range(1_000):
            region = "north" if index % 2 else "south"
            channel = "paid" if index % 3 else "organic"
            score = index % 100
            amount = score * 2 + (20 if region == "north" else 0)
            output.write(f"{region},{channel},{score},{amount}\n")

    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
    asset = DataAsset(
        id="complete-dataset",
        owner_id="owner",
        name="complete",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={
            "source_schema": schema,
            "data_roles": {
                "target_column": "amount",
                "column_roles": {
                    "region": "feature_categorical",
                    "channel": "feature_categorical",
                    "score": "feature_continuous",
                    "amount": "target",
                },
            },
        },
    )

    result = FullDatasetProfiler(ColumnarDatasetStore(repository)).profile(
        asset,
        {
            "target_column": "amount",
            "target_type": "continuous",
            "comparison_column": "amount",
            "comparison_type": "continuous",
            "include_target_relations": True,
            "include_segments": True,
            "include_graphic_summaries": True,
            "row_limit": 50_000,
            "max_target_features": 30,
            "max_segment_features": 4,
        },
    )

    relations = result["profile"]["targetRelations"]
    assert [item["feature"] for item in relations] == ["region", "channel", "score"]
    score_relation = next(item for item in relations if item["feature"] == "score")
    region_relation = next(item for item in relations if item["feature"] == "region")
    assert score_relation["numericStats"]["pearson"] > 0.9
    assert 0 < len(score_relation["scatterPlot"]["points"]) <= 800
    assert region_relation["densityPlot"]["series"]
    assert all(len(series["points"]) == 80 for series in region_relation["densityPlot"]["series"])
    assert result["profile"]["segmentProfile"]["results"]

    lighter_result = FullDatasetProfiler(ColumnarDatasetStore(repository)).profile(
        asset,
        {
            "target_column": "amount",
            "target_type": "continuous",
            "comparison_column": "amount",
            "comparison_type": "continuous",
            "include_summary": False,
            "include_univariate": False,
            "include_target_relations": True,
            "include_segments": False,
            "include_graphic_summaries": True,
            "max_target_features": 2,
        },
    )
    lighter_profiles = lighter_result["profile"]["columnProfiles"]
    assert [item["feature"] for item in lighter_result["profile"]["targetRelations"]] == ["region", "channel"]
    assert lighter_result["profile"]["dataQualityNotes"] == []
    assert all(profile["median"] is None for profile in lighter_profiles if profile["name"] != "amount")
    assert all(profile["topValues"] == [] for profile in lighter_profiles if profile["name"] != "amount")


def test_csv_edge_cases_keep_stable_column_contract(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "edge-dataset"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "edge.csv"
    csv_path.write_text("\nvalue,value\n1,10\n2,20\n", encoding="utf-8")
    source = CsvFileDatasetSource(repository)

    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)

    assert has_header is True
    assert row_count == 2
    assert [column["name"] for column in schema] == ["value", "value_2"]

    asset = DataAsset(
        id="edge-dataset",
        owner_id="owner",
        name="edge",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )
    result = FullDatasetProfiler(ColumnarDatasetStore(repository)).profile(
        asset,
        {"include_target_relations": False, "include_segments": False, "include_graphic_summaries": False},
    )
    assert [column["name"] for column in result["columns"]] == ["value", "value_2"]


def test_headerless_csv_uses_application_column_names(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    dataset_dir = repository / "users" / "owner" / "headerless-dataset"
    dataset_dir.mkdir(parents=True)
    csv_path = dataset_dir / "headerless.csv"
    csv_path.write_text("1,north\n2,south\n3,east,extra\n", encoding="utf-8")
    source = CsvFileDatasetSource(repository)
    has_header, row_count, schema = source.inspect_path_with_schema(csv_path)

    assert has_header is False
    assert row_count == 3
    assert [column["name"] for column in schema] == ["column_1", "column_2", "column_3"]

    asset = DataAsset(
        id="headerless-dataset",
        owner_id="owner",
        name="headerless",
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{csv_path.as_posix()}",
        row_count=row_count,
        has_header=has_header,
        status=DataAssetStatus.READY,
        metadata={"source_schema": schema},
    )
    preview = FullDatasetProfiler(ColumnarDatasetStore(repository)).schema(asset, limit=10)
    assert [column["name"] for column in preview["columns"]] == ["column_1", "column_2", "column_3"]
    assert preview["records"][0] == {"column_1": 1, "column_2": "north", "column_3": None}
