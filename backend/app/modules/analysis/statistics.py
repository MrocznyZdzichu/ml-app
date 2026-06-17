from collections import defaultdict
from typing import Any

from app.modules.analysis.schemas import ColumnStats, DescriptiveStatsResponse


def describe_records(records: list[dict[str, Any]]) -> DescriptiveStatsResponse:
    columns = sorted({key for row in records for key in row.keys()})
    values_by_column: dict[str, list[Any]] = defaultdict(list)

    for row in records:
        for column in columns:
            values_by_column[column].append(row.get(column))

    stats: dict[str, ColumnStats] = {}
    for column, values in values_by_column.items():
        present = [value for value in values if value is not None and value != ""]
        numeric = _as_numbers(present)
        if numeric:
            stats[column] = ColumnStats(
                count=len(present),
                missing=len(values) - len(present),
                mean=sum(numeric) / len(numeric),
                minimum=min(numeric),
                maximum=max(numeric),
                unique=len(set(present)),
            )
        else:
            stats[column] = ColumnStats(
                count=len(present),
                missing=len(values) - len(present),
                unique=len(set(present)),
            )

    return DescriptiveStatsResponse(row_count=len(records), columns=stats)


def _as_numbers(values: list[Any]) -> list[float]:
    numbers: list[float] = []
    for value in values:
        if isinstance(value, bool):
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            return []
    return numbers
