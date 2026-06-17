import csv
from dataclasses import dataclass
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
        try:
            dialect = csv.Sniffer().sniff(text[:4096])
        except csv.Error:
            dialect = csv.excel
        return [row for row in csv.reader(StringIO(text), dialect) if any(cell.strip() for cell in row)]

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
