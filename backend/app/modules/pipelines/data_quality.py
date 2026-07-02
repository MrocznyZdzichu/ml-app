from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb

from app.modules.pipelines.runtime import json_safe, sql_literal
from app.shared.sql_security import identifier


@dataclass(frozen=True)
class QualityEvaluation:
    report: dict[str, Any]
    warnings: list[str]
    reject_predicate: str
    reject_reason_expression: str
    rejected_row_count: int


def evaluate_data_contract(
    connection: duckdb.DuckDBPyConnection,
    relation_name: str,
    contract: Any,
) -> QualityEvaluation:
    if contract is None:
        return QualityEvaluation(
            report={"status": "not_configured", "data_scope": "full", "checks": [], "schema_drift": []},
            warnings=[],
            reject_predicate="FALSE",
            reject_reason_expression="''",
            rejected_row_count=0,
        )

    actual_schema = {
        str(row[0]): str(row[1])
        for row in connection.execute(
            f"DESCRIBE SELECT * FROM {identifier(relation_name)}"
        ).fetchall()
    }
    expected = {column.name: column for column in contract.columns}
    drift: list[dict[str, Any]] = []
    for name, column in expected.items():
        if name not in actual_schema:
            drift.append({"kind": "missing_column", "column": name, "expected_type": column.type})
        elif column.type and not types_compatible(actual_schema[name], column.type):
            drift.append(
                {
                    "kind": "type_mismatch",
                    "column": name,
                    "expected_type": column.type,
                    "actual_type": actual_schema[name],
                }
            )
    if not contract.allow_unexpected_columns:
        for name, actual_type in actual_schema.items():
            if name not in expected:
                drift.append({"kind": "unexpected_column", "column": name, "actual_type": actual_type})

    warnings: list[str] = []
    if drift and contract.schema_drift_policy == "fail":
        summary = ", ".join(f"{item['kind']}:{item['column']}" for item in drift)
        raise ValueError(f"Data contract schema drift detected: {summary}")
    if drift:
        warnings.append(f"Data contract detected {len(drift)} schema drift issue(s)")

    checks: list[dict[str, Any]] = []
    predicates: list[tuple[str, str, str, str]] = []
    for column in contract.columns:
        if column.name not in actual_schema:
            continue
        value = identifier(column.name)
        if not column.nullable:
            predicates.append((column.name, "nullable", f"{value} IS NULL", column.policy))
        if column.unique:
            predicates.append(
                (
                    column.name,
                    "unique",
                    (
                        f"{value} IS NOT NULL AND {value} IN ("
                        f"SELECT {value} FROM {identifier(relation_name)} "
                        f"WHERE {value} IS NOT NULL GROUP BY {value} HAVING count(*) > 1)"
                    ),
                    column.policy,
                )
            )
        if column.minimum is not None:
            predicates.append(
                (column.name, "minimum", f"{value} IS NOT NULL AND {value} < {sql_literal(column.minimum)}", column.policy)
            )
        if column.maximum is not None:
            predicates.append(
                (column.name, "maximum", f"{value} IS NOT NULL AND {value} > {sql_literal(column.maximum)}", column.policy)
            )
        if column.allowed_values is not None:
            allowed = ", ".join(sql_literal(item) for item in column.allowed_values)
            predicates.append(
                (column.name, "allowed_values", f"{value} IS NOT NULL AND {value} NOT IN ({allowed})", column.policy)
            )

    relation = identifier(relation_name)
    if predicates:
        selections = ", ".join(
            f"count(*) FILTER (WHERE {predicate}) AS {identifier(f'check_{index}')}"
            for index, (_, _, predicate, _) in enumerate(predicates)
        )
        counts = connection.execute(f"SELECT {selections} FROM {relation}").fetchone()
    else:
        counts = ()

    reject_predicates: list[str] = []
    reject_reasons: list[str] = []
    failed: list[str] = []
    for index, (column, check, predicate, policy) in enumerate(predicates):
        violations = int(counts[index])
        result = {
            "column": column,
            "check": check,
            "policy": policy,
            "violation_count": violations,
            "passed": violations == 0,
        }
        checks.append(result)
        if not violations:
            continue
        label = f"{column}.{check}"
        if policy == "fail":
            failed.append(f"{label} ({violations} rows)")
        elif policy == "warn":
            warnings.append(f"Quality check {label} failed for {violations} row(s)")
        else:
            reject_predicates.append(f"({predicate})")
            reject_reasons.append(f"CASE WHEN {predicate} THEN {sql_literal(label)} END")

    if failed:
        raise ValueError("Data contract validation failed: " + ", ".join(failed))

    reject_predicate = " OR ".join(reject_predicates) if reject_predicates else "FALSE"
    rejected_row_count = (
        int(connection.execute(f"SELECT count(*) FROM {relation} WHERE {reject_predicate}").fetchone()[0])
        if reject_predicates
        else 0
    )
    reason_expression = (
        f"concat_ws('; ', {', '.join(reject_reasons)})"
        if reject_reasons
        else "''"
    )
    row_count = int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
    status = "passed"
    if rejected_row_count or warnings or drift:
        status = "issues_detected"
    return QualityEvaluation(
        report={
            "status": status,
            "data_scope": "full",
            "checked_row_count": row_count,
            "rejected_row_count": rejected_row_count,
            "checks": [{key: json_safe(value) for key, value in item.items()} for item in checks],
            "schema_drift": drift,
        },
        warnings=warnings,
        reject_predicate=reject_predicate,
        reject_reason_expression=reason_expression,
        rejected_row_count=rejected_row_count,
    )


def types_compatible(actual: str, expected: str) -> bool:
    def family(value: str) -> str:
        normalized = value.upper().split("(")[0].strip()
        if normalized in {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT"}:
            return "integer"
        if normalized in {"FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL"}:
            return "numeric"
        if normalized in {"VARCHAR", "CHAR", "TEXT", "STRING"}:
            return "string"
        if normalized.startswith("TIMESTAMP"):
            return "timestamp"
        return normalized.lower()

    actual_family = family(actual)
    expected_family = family(expected)
    return actual_family == expected_family or {actual_family, expected_family} <= {"integer", "numeric"}
