from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from collections.abc import Mapping, Sequence
from typing import Any

import duckdb

from app.shared.sql_security import identifier


@dataclass(frozen=True)
class SourceRelation:
    sql: str
    row_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


def relation_columns(
    connection: duckdb.DuckDBPyConnection,
    view_name: str,
) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            f"DESCRIBE SELECT * FROM {identifier(view_name)}"
        ).fetchall()
    ]


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def safe_filename(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return json_safe(value.item())
    return value
