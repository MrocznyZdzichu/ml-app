from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable
from uuid import uuid4

import duckdb
from fastapi import HTTPException, status

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset
from app.modules.datasets.schemas import DataAssetPreviewRead
from app.shared.sql_security import bind_user_sql_to_inputs


AssetLoader = Callable[[str], DataAsset]


class FullDatasetSqlQuery:
    """Executes bounded-result SQL over the complete columnar data asset."""

    def __init__(self, store: ColumnarDatasetStore | None = None) -> None:
        self.store = store or ColumnarDatasetStore()

    def execute(
        self,
        asset: DataAsset,
        load_asset: AssetLoader,
        sql: str,
        limit: int,
    ) -> DataAssetPreviewRead:
        connection = self.store.connect(asset)
        source_name = asset.name.strip() or "dataset"
        source_relation_name = f"__mlapp_query_source_{uuid4().hex}"
        result_name = f"__mlapp_query_result_{uuid4().hex}"
        try:
            relation = self.store.relation_sql(asset, load_asset)
            connection.execute(
                f"CREATE TEMP VIEW {self.store.identifier(source_relation_name)} "
                f"AS SELECT * FROM {relation}"
            )
            query = bind_user_sql_to_inputs(
                connection,
                sql,
                {source_name: source_relation_name},
            )
            # Materialize once so an expensive full-dataset query is not
            # evaluated separately for the total count and bounded preview.
            connection.execute(
                f"CREATE TEMP TABLE {self.store.identifier(result_name)} AS {query}"
            )
            result_relation = self.store.identifier(result_name)
            columns = self._columns(connection, result_relation)
            row_count = int(
                connection.execute(f"SELECT count(*) FROM {result_relation}").fetchone()[0]
            )
            cursor = connection.execute(
                f"SELECT * FROM {result_relation} LIMIT ?",
                [limit],
            )
            records = self._records(columns, cursor.fetchall())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SQL query is invalid: {exc}",
            ) from exc
        except duckdb.Error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SQL query failed: {exc}",
            ) from exc
        finally:
            connection.close()

        return DataAssetPreviewRead(
            dataset_id=asset.id,
            columns=columns,
            records=records,
            row_count=row_count,
            returned_count=len(records),
            limit=limit,
        )

    def _columns(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
    ) -> list[dict[str, str]]:
        described = connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        names = [str(row[0]) for row in described]
        if len(names) != len(set(names)):
            raise ValueError("SQL query output column names must be unique")
        return [
            {"name": name, "type": self._frontend_type(str(row[1]))}
            for name, row in zip(names, described, strict=True)
        ]

    @staticmethod
    def _records(
        columns: list[dict[str, str]],
        rows: list[tuple[Any, ...]],
    ) -> list[dict[str, Any]]:
        return [
            {
                column["name"]: FullDatasetSqlQuery._json_value(row[index])
                for index, column in enumerate(columns)
            }
            for row in rows
        ]

    @staticmethod
    def _frontend_type(value: str) -> str:
        upper = value.upper()
        if any(token in upper for token in ["INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT"]):
            return "number"
        if any(token in upper for token in ["DATE", "TIME"]):
            return "date"
        if "BOOL" in upper:
            return "boolean"
        return "text"

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value
