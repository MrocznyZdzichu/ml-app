# Data Engineering — Stage 1 contract

The first functional increment executes a full-data, manual Data Engineering
step inside a high-level pipeline. It deliberately does not implement
schedules, database connectors, arbitrary Python, data contracts, rejected
records, or other lifecycle step types. Normal runs create persistent Parquet
datasets with minimal artifact lineage; dry-runs remain temporary.

## High-level pipeline workflow

The user-facing pipeline is a lifecycle DAG (`contract_version: "2.0"`). The
first functional prototype exposes exactly one high-level step type:
`data_engineering`. Standard transformations and User Written SQL are nested
inside that step; they are not lifecycle steps.

```json
{
  "contract_version": "2.0",
  "steps": [
    {
      "step_id": "de_1",
      "name": "Data Engineering",
      "type": "data_engineering",
      "inputs": [],
      "output_port_id": "dataset",
      "config": {"definition": {"contract_version": "1.0", "...": "..."}}
    }
  ],
  "outputs": [
    {"output_id": "result", "source": {"step_id": "de_1", "port_id": "dataset"}}
  ],
  "parameters": {}
}
```

Existing DE-only `1.0` pipeline definitions are normalized into one
high-level DE step when they are edited or published.

## Nested DE DAG definition

An empty draft is allowed. Publishing or running requires an executable
`contract_version: "1.0"` definition:

```json
{
  "contract_version": "1.0",
  "inputs": [
    {
      "input_id": "orders",
      "dataset_id": "uploaded-csv-dataset-id",
      "output_port_id": "out"
    }
  ],
  "steps": [
    {
      "step_id": "large-orders",
      "type": "filter_rows",
      "inputs": [
        {
          "port_id": "input",
          "source": {"node_id": "orders", "port_id": "out"}
        }
      ],
      "output_port_id": "out",
      "config": {
        "conditions": [
          {"column": "amount", "operator": "gte", "value": 100}
        ],
        "combine": "and"
      }
    }
  ],
  "outputs": [
    {
      "output_id": "result",
      "input": {"node_id": "large-orders", "port_id": "out"},
      "materialization": "dataset",
      "write_mode": "replace",
      "dataset_name": "Prepared orders",
      "business_case_role": "training"
    }
  ],
  "parameters": {}
}
```

IDs are stable and unique across input, step, and output nodes. Edges reference
an explicit upstream node and port. Validation rejects missing references,
cycles, duplicate IDs and ports, incorrect operation arity, unsupported config,
and non-temporary Stage 1 outputs.

Supported operations are `select_columns`, `add_identifier`, `rename_columns`, `cast_columns`,
`filter_rows`, `sort_rows`, `deduplicate`, `impute_missing`, `derive_column`,
`aggregate`, `join`, `union`, and `map_categories`. Join inputs must use ports
`left` and `right`. Expressions and predicates are structured; raw SQL is not
accepted by standard blocks.

`add_identifier` creates a protected row-key candidate before feature
engineering. It supports SHA-256 of the complete record, SHA-256 of an ordered
column selection, and a `BIGINT` sequence starting at a configured value.
Hashes use a canonical null- and boundary-aware encoding. Sequence mode
requires an explicit sort definition; those columns should uniquely order the
rows, otherwise tied rows cannot be assigned reproducibly. Existing columns
are never overwritten.

The `custom_sql` block is the controlled **User Written SQL** escape hatch. Its
input port IDs become the only relation names available to one read-only
`SELECT`/`WITH` query. The validator rejects multiple statements, DDL/DML,
`COPY`, `ATTACH`, extension loading, direct file/URL readers, system catalogs,
and relations not declared as step inputs. It does not execute Python.

## Block editor

The Pipelines screen provides a form/list editor over the same JSON contract:

- choose one or more CSV/Parquet sources, prioritised from Business Case
  attachments by role (`source`, `training`, `scoring_input`, etc.), and inspect
  their stored or lazily refreshed schema,
- add and configure transformation blocks with explicit upstream nodes,
- choose the node exposed as the temporary output,
- save, dry-run, publish, and execute the version,
- inspect or edit the synchronized contract under **Advanced JSON definition**.

This is intentionally an ordered form editor, not a canvas scheduler or a
separate ETL-job model.

The DE inspector uses domain controls rather than encoded text fields:
checkbox column selection, visual multi-condition filters or a restricted SQL
`WHERE` predicate, rename/cast/imputation tables, multi-level sorting,
aggregation metrics, join key pairs and category mappings. SQL `WHERE` accepts
only a predicate; subqueries and additional clauses are rejected.

## Execution and audit

`POST /api/v1/pipelines/{pipeline_id}/runs` records a `queued` manual run for a
specific version and dispatches it to Celery. Passing `step_id` audits the run
as a manually requested single-step execution. In the one-step prototype its
execution plan is intentionally identical to the whole pipeline. Draft
versions require `is_dry_run: true`; official runs require a published
version. Status can be read at
`GET /api/v1/pipelines/{pipeline_id}/runs/{run_id}`.

The worker validates dataset ownership and accepts uploaded CSV plus
platform-generated Parquet datasets. A
DuckDB process executes the DAG with configured thread and memory limits and
writes ZSTD-compressed Parquet. The API never transfers the full table to the
browser.

Each completed run records full-scope input, processed, and output row counts,
plus an output manifest containing schema, row count, an explicitly limited
preview, and the `data_scope: "full"` marker. A dry-run keeps temporary Parquet
and creates no official artifact. A normal run atomically moves the Parquet to
a new deterministic dataset location, registers a `DataAsset`, `Artifact`,
Business Case attachment and minimal lineage containing input artifact IDs,
pipeline version/hash, run, step, creator, row count and output schema.
