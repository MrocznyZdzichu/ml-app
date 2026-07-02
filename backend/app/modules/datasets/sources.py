import csv
import duckdb
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, status

from app.modules.datasets.domain import DataAsset, SourceType


@dataclass(frozen=True)
class TabularDataset:
    columns: list[str]
    rows: list[list[str]]


class DatasetSource(Protocol):
    def read(self, asset: DataAsset, action: str = "read") -> TabularDataset:
        ...


class DatasetSourceRegistry:
    def __init__(self, repository_root: Path) -> None:
        self.csv = CsvFileDatasetSource(repository_root)
        self.parquet = ParquetFileDatasetSource(repository_root)
        self._sources: dict[tuple[SourceType, str], DatasetSource] = {
            (SourceType.FILE, "csv"): self.csv,
        }

    def read(self, asset: DataAsset, action: str = "read") -> TabularDataset:
        source = self._sources.get((asset.source_type, asset.format.lower()))
        if source:
            return source.read(asset, action)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Dataset source {asset.source_type.value}/{asset.format} cannot be {action} yet",
        )


class ParquetFileDatasetSource:
    """Inspects flat Parquet datasets without materializing their rows in Python."""

    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()

    def inspect_path_with_schema(self, path: Path) -> tuple[None, int, list[dict[str, str]]]:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.repository_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset file location is outside the repository root",
            ) from exc

        connection = duckdb.connect(database=":memory:")
        try:
            described = connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)",
                [str(resolved)],
            ).fetchall()
            if not described:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parquet file does not contain any columns",
                )
            unsupported = [
                f"{row[0]} ({row[1]})"
                for row in described
                if self._is_unsupported_type(str(row[1]))
            ]
            if unsupported:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Parquet file contains unsupported nested or binary columns: "
                        + ", ".join(unsupported)
                    ),
                )
            row_count = int(
                connection.execute(
                    "SELECT count(*) FROM read_parquet(?)",
                    [str(resolved)],
                ).fetchone()[0]
            )
            schema = [
                {"name": str(row[0]), "type": self._frontend_type(str(row[1]))}
                for row in described
            ]
            return None, row_count, schema
        except HTTPException:
            raise
        except duckdb.Error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Parquet file is invalid or unreadable: {exc}",
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _is_unsupported_type(value: str) -> bool:
        normalized = value.upper()
        return any(token in normalized for token in ("STRUCT", "LIST", "MAP", "UNION", "[]", "BLOB"))

    @staticmethod
    def _frontend_type(value: str) -> str:
        normalized = value.upper()
        if any(token in normalized for token in ("INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT")):
            return "number"
        if "BOOL" in normalized:
            return "boolean"
        if any(token in normalized for token in ("DATE", "TIME")):
            return "date"
        return "text"


class CsvFileDatasetSource:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()

    def decode(self, content: bytes) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file must be UTF-8 encoded",
            ) from exc

    def inspect(self, text: str) -> tuple[bool, int]:
        rows = self._read_rows(text)
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file does not contain any rows",
            )

        has_header = self._has_header(text, rows)
        row_count = len(rows) - 1 if has_header else len(rows)
        return has_header, max(row_count, 0)

    def inspect_path(self, path: Path) -> tuple[bool, int]:
        has_header, row_count, _columns = self.inspect_path_with_schema(path)
        return has_header, row_count

    def inspect_path_with_schema(self, path: Path) -> tuple[bool, int, list[dict[str, str]]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                sample = source.read(4096)
            dialect = self._dialect(sample)
            sample_rows = [row for row in csv.reader(StringIO(sample), dialect) if any(cell.strip() for cell in row)]
            if not sample_rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV file does not contain any rows",
                )
            has_header = self._has_header(sample, sample_rows)
            headers = [self._column_name(value, index) for index, value in enumerate(sample_rows[0])] if has_header else [
                f"column_{index + 1}" for index in range(len(sample_rows[0]))
            ]
            headers = self._unique_column_names(headers)
            observed_types: list[set[str]] = [set() for _ in headers]
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                row_count = 0
                non_empty_row_index = 0
                for row in csv.reader(source, dialect):
                    if not any(cell.strip() for cell in row):
                        continue
                    if has_header and non_empty_row_index == 0:
                        non_empty_row_index += 1
                        continue
                    non_empty_row_index += 1
                    if not has_header and len(row) > len(headers):
                        start = len(headers)
                        headers.extend(f"column_{index + 1}" for index in range(start, len(row)))
                        observed_types.extend(set() for _ in range(start, len(row)))
                    row_count += 1
                    for index, _header in enumerate(headers):
                        observed_types[index].add(self._cell_type(row[index] if index < len(row) else ""))
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file must be UTF-8 encoded",
            ) from exc
        columns = [
            {"name": header, "type": self._resolve_types(observed_types[index])}
            for index, header in enumerate(headers)
        ]
        return has_header, row_count, columns

    def read(self, asset: DataAsset, action: str = "read") -> TabularDataset:
        if asset.source_type != SourceType.FILE or asset.format.lower() != "csv":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Only uploaded CSV datasets can be {action}",
            )
        if not asset.location_uri or not asset.location_uri.startswith("file://"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset file location is not available",
            )

        path = self._resolve_path(asset.location_uri.removeprefix("file://"))
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")

        rows = self._read_rows(self.decode(path.read_bytes()))
        if not rows:
            return TabularDataset(columns=[], rows=[])

        if asset.has_header:
            headers = [self._column_name(value, index) for index, value in enumerate(rows[0])]
            data_rows = rows[1:]
        else:
            width = max(len(row) for row in rows)
            headers = [f"column_{index + 1}" for index in range(width)]
            data_rows = rows

        return TabularDataset(columns=self._unique_column_names(headers), rows=data_rows)

    def _resolve_path(self, location_path: str) -> Path:
        path = Path(location_path).resolve()
        try:
            path.relative_to(self.repository_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset file location is outside the repository root",
            ) from exc
        return path

    def _read_rows(self, text: str) -> list[list[str]]:
        dialect = self._dialect(text[:4096])
        return [row for row in csv.reader(StringIO(text), dialect) if any(cell.strip() for cell in row)]

    def _dialect(self, sample: str):
        try:
            return csv.Sniffer().sniff(sample)
        except csv.Error:
            return csv.excel

    def _has_header(self, text: str, rows: list[list[str]]) -> bool:
        try:
            if csv.Sniffer().has_header(text[:4096]):
                return True
        except csv.Error:
            pass

        if len(rows) < 2:
            return False

        first_row = rows[0]
        next_row = rows[1]
        if len(first_row) != len(next_row):
            return False

        first_numeric = sum(self._is_number(value) for value in first_row)
        next_numeric = sum(self._is_number(value) for value in next_row)
        return first_numeric == 0 and next_numeric > 0

    def _is_number(self, value: str) -> bool:
        try:
            float(value)
        except ValueError:
            return False
        return True

    def _cell_type(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return "empty"
        if stripped.lower() in {"true", "false"}:
            return "boolean"
        if self._is_number(stripped):
            return "number"
        try:
            datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return "text"
        return "date"

    def _resolve_types(self, value_types: set[str]) -> str:
        concrete = value_types - {"empty"}
        if not concrete:
            return "empty"
        return next(iter(concrete)) if len(concrete) == 1 else "mixed"

    def _column_name(self, value: str, index: int) -> str:
        return value.strip() or f"column_{index + 1}"

    def _unique_column_names(self, headers: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        unique_headers = []
        for header in headers:
            base_name = header or "column"
            count = seen.get(base_name, 0)
            seen[base_name] = count + 1
            unique_headers.append(base_name if count == 0 else f"{base_name}_{count + 1}")
        return unique_headers
