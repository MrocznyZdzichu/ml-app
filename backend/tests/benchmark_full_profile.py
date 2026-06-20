"""Manual full-profile benchmark: python tests/benchmark_full_profile.py --rows 1000000."""

import argparse
import json
import tempfile
from pathlib import Path
from time import perf_counter

import duckdb

from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.sources import CsvFileDatasetSource


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory() as temporary:
        repository = Path(temporary) / "repository"
        dataset_dir = repository / "users" / "benchmark" / "large"
        dataset_dir.mkdir(parents=True)
        csv_path = dataset_dir / "large.csv"
        duckdb.sql(
            "COPY (SELECT i AS customer_id, "
            "CASE WHEN i % 4 = 0 THEN 'north' WHEN i % 4 = 1 THEN 'south' "
            "WHEN i % 4 = 2 THEN 'east' ELSE 'west' END AS region, "
            "CASE WHEN i % 3 = 0 THEN 'paid' ELSE 'organic' END AS channel, "
            "i % 120 AS tenure_months, 20 + (i % 100) * 0.75 AS monthly_fee, "
            "CASE WHEN i % 19 = 0 THEN 1 ELSE 0 END AS churned "
            f"FROM range({arguments.rows}) AS source(i)) TO '{csv_path.as_posix()}' (HEADER, DELIMITER ',')"
        )
        source = CsvFileDatasetSource(repository)
        has_header, row_count, schema = source.inspect_path_with_schema(csv_path)
        asset = DataAsset(
            id="large",
            owner_id="benchmark",
            name="benchmark",
            source_type=SourceType.FILE,
            format="csv",
            location_uri=f"file://{csv_path.as_posix()}",
            row_count=row_count,
            has_header=has_header,
            status=DataAssetStatus.READY,
            metadata={
                "source_schema": schema,
                "data_roles": {
                    "target_column": "churned",
                    "column_roles": {
                        "customer_id": "identifier",
                        "region": "feature_categorical",
                        "channel": "feature_categorical",
                        "tenure_months": "feature_continuous",
                        "monthly_fee": "feature_continuous",
                        "churned": "target",
                    },
                },
            },
        )
        started = perf_counter()
        result = FullDatasetProfiler(ColumnarDatasetStore(repository)).profile(
            asset,
            {
                "target_column": "churned",
                "target_type": "categorical",
                "comparison_column": "churned",
                "comparison_type": "categorical",
                "include_target_relations": True,
                "include_segments": True,
                "include_graphic_summaries": True,
                "row_limit": 50_000,
                "max_target_features": 30,
                "max_segment_features": 4,
            },
        )
        elapsed = perf_counter() - started
        print(json.dumps({
            "rows": result["row_count"],
            "columns": len(result["columns"]),
            "relations": len(result["profile"]["targetRelations"]),
            "segments": len(result["profile"]["segmentProfile"]["results"]),
            "seconds": round(elapsed, 3),
            "rows_per_second": round(result["row_count"] / elapsed),
            "csv_mb": round(csv_path.stat().st_size / 1024 ** 2, 2),
            "parquet_mb": round((dataset_dir / "dataset.mlapp.parquet").stat().st_size / 1024 ** 2, 2),
        }, indent=2))


if __name__ == "__main__":
    main()
