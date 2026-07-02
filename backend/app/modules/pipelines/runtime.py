from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from app.shared.sql_security import identifier


@dataclass(frozen=True)
class SourceRelation:
    sql: str
    row_count: int


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
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value
