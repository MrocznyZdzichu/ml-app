from __future__ import annotations

import re

import duckdb


MAX_USER_SQL_LENGTH = 100_000
BLOCKED_KEYWORDS = {
    "alter",
    "attach",
    "call",
    "checkpoint",
    "comment",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "export",
    "import",
    "insert",
    "install",
    "load",
    "merge",
    "pragma",
    "set",
    "truncate",
    "update",
    "vacuum",
}
BLOCKED_RELATION_FUNCTIONS = {
    "arrow_scan",
    "delta_scan",
    "duckdb_extensions",
    "duckdb_secrets",
    "excel_scan",
    "glob",
    "http_get",
    "httpfs",
    "iceberg_scan",
    "mysql_scan",
    "parquet_scan",
    "postgres_scan",
    "read_blob",
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_json_auto",
    "read_ndjson",
    "read_parquet",
    "read_text",
    "read_xlsx",
    "sqlite_scan",
}


def validate_user_sql(sql: str) -> str:
    query = sql.strip()
    if not query:
        raise ValueError("User Written SQL query cannot be empty")
    if len(query) > MAX_USER_SQL_LENGTH:
        raise ValueError(f"User Written SQL cannot exceed {MAX_USER_SQL_LENGTH} characters")

    connection = duckdb.connect(database=":memory:")
    try:
        statements = connection.extract_statements(query)
    except duckdb.Error as exc:
        raise ValueError(f"User Written SQL syntax is invalid: {exc}") from exc
    finally:
        connection.close()
    if len(statements) != 1 or str(statements[0].type) != "StatementType.SELECT":
        raise ValueError("User Written SQL must contain exactly one read-only SELECT or WITH query")

    searchable = _strip_literals_and_comments(query).lower()
    words = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", searchable))
    blocked = sorted(words & BLOCKED_KEYWORDS)
    if blocked:
        raise ValueError(f"User Written SQL contains forbidden keyword: {blocked[0]}")
    blocked_functions = sorted(words & BLOCKED_RELATION_FUNCTIONS)
    if blocked_functions:
        raise ValueError(f"User Written SQL contains forbidden external function: {blocked_functions[0]}")
    if {"information_schema", "pg_catalog"} & words or any(word.startswith("duckdb_") for word in words):
        raise ValueError("User Written SQL cannot access system catalog relations")
    if re.search(r"\b(from|join)\s*['\"]", searchable):
        raise ValueError("User Written SQL cannot read a file or URI directly")
    return query.removesuffix(";").rstrip()


def validate_filter_sql(expression: str) -> str:
    predicate = expression.strip()
    if not predicate:
        raise ValueError("SQL WHERE condition cannot be empty")
    searchable = _strip_literals_and_comments(predicate).lower()
    words = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", searchable))
    forbidden_clauses = words & {
        "select", "with", "union", "from", "join", "order", "group",
        "having", "limit", "offset", "qualify", "copy", "attach",
    }
    if forbidden_clauses:
        raise ValueError(
            f"SQL WHERE condition contains forbidden clause: {sorted(forbidden_clauses)[0]}"
        )
    validate_user_sql(f"SELECT * FROM input WHERE {predicate}")
    return predicate


def bind_user_sql_to_inputs(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    input_relations: dict[str, str],
) -> str:
    query = validate_user_sql(sql)
    try:
        referenced_relations = set(connection.get_table_names(query))
    except duckdb.Error as exc:
        raise ValueError(f"User Written SQL could not be bound: {exc}") from exc
    unknown = sorted(referenced_relations - set(input_relations))
    if unknown:
        raise ValueError(
            "User Written SQL references relations outside its declared inputs: "
            + ", ".join(unknown)
        )
    ctes = ", ".join(
        f'{identifier(alias)} AS (SELECT * FROM {identifier(relation)})'
        for alias, relation in input_relations.items()
    )
    match = re.match(r"(?is)^with\s+(recursive\s+)?", query)
    if match:
        recursive = "RECURSIVE " if match.group(1) else ""
        return f"WITH {recursive}{ctes}, {query[match.end():]}"
    return f"WITH {ctes} {query}"


def _strip_literals_and_comments(sql: str) -> str:
    result: list[str] = []
    index = 0
    state = "code"
    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "code":
            if char == "'":
                state = "single"
                result.append("'")
            elif char == '"':
                state = "double"
                result.append(" ")
            elif char == "-" and following == "-":
                state = "line_comment"
                result.extend((" ", " "))
                index += 1
            elif char == "/" and following == "*":
                state = "block_comment"
                result.extend((" ", " "))
                index += 1
            else:
                result.append(char)
        elif state == "single":
            result.append("'" if char == "'" else " ")
            if char == "'" and following == "'":
                result.append(" ")
                index += 1
            elif char == "'":
                state = "code"
        elif state == "double":
            result.append(" ")
            if char == '"' and following == '"':
                result.append(" ")
                index += 1
            elif char == '"':
                state = "code"
        elif state == "line_comment":
            result.append("\n" if char == "\n" else " ")
            if char == "\n":
                state = "code"
        else:
            result.append(" ")
            if char == "*" and following == "/":
                result.append(" ")
                index += 1
                state = "code"
        index += 1
    return "".join(result)


def identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("SQL identifier cannot be empty or contain NUL")
    return '"' + value.replace('"', '""') + '"'
