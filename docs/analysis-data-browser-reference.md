# Analysis and Data Browser Reference

This document describes the current Analysis tools and the metadata contracts
they rely on.

## Analysis Tabs

The Analysis workspace currently contains:

- `Data Roles` - durable semantic metadata for datasets and columns.
- `Data Browsing` - interactive preview, filtering, sorting, grouping,
  aggregation, Custom SQL, drill down, and Data View creation.
- `Descriptive Analysis` - placeholder for calculated summaries.
- `Visualization and Trends` - placeholder for visual analysis.

Dataset selection is shared across Analysis tabs. Selecting a dataset in
`Data Browsing` keeps the same dataset selected when switching to `Data Roles`,
and vice versa.

## Data Roles

Data Roles are stored in dataset metadata under:

```json
{
  "data_roles": {
    "dataset_roles": ["training", "targeted"],
    "entity_id_column": "customer_id",
    "timestamp_column": "",
    "period_column": "snapshot_month",
    "target_column": "churned",
    "column_roles": {
      "customer_id": "identifier",
      "snapshot_month": "period_id",
      "plan_type": "feature_ordinal",
      "monthly_fee": "feature_continuous",
      "churned": "target"
    },
    "notes": ""
  }
}
```

### Dataset Roles

- `training` - data intended for model fitting.
- `validation` - data used for tuning and model selection.
- `test` - data reserved for final evaluation.
- `holdout` - data intentionally kept out of normal iteration.
- `scoring` - data intended for prediction without known target values.
- `targeted` - data contains target/outcome columns.
- `reference` - baseline data for comparison and monitoring.
- `monitoring` - production or later-period data used for drift/quality checks.

### Column Roles

- `identifier` - stable row/entity key such as customer or account ID.
- `timestamp` - event or observation time.
- `period_id` - period, batch, cohort, or snapshot identifier.
- `feature_continuous` - numeric variable with meaningful magnitude.
- `feature_categorical` - unordered category.
- `feature_ordinal` - ordered category.
- `target` - value to predict or explain.
- `sample_weight` - row weight used by modeling or statistics.
- `text` - free text feature.
- `boolean` - true/false feature.
- `ignored` - column intentionally excluded from analysis/modeling.

## Data Browsing

The browser works on the full dataset before applying the display limit. This
means filtering, searching, grouping, aggregation, sorting, and Custom SQL are
computed against all currently loaded records, and only the final result is
limited/paged for display.

### Column Selection

Columns Selection controls which columns are shown in the detail table and which
columns are used as the default detail columns for drill down. Presets include:

- show all,
- hide all,
- numeric only,
- non-numeric,
- model-ready,
- essentials.

### Filters

Column Filters support operator-based filtering. Available operators depend on
column type and role. Supported operators include:

- contains,
- equals,
- not equals,
- in,
- regex,
- greater than / greater than or equal,
- less than / less than or equal,
- starts with,
- ends with,
- empty,
- not empty.

For categorical and ordinal columns, `equals` uses a single-value dropdown and
`in` supports multi-value selection.

### Sorting

Sorting supports multiple rules. Rules have an explicit order and direction.
For grouped output, the result columns are arranged to match sort intent:

1. group columns in sort order,
2. `records`,
3. aggregate columns in sort order,
4. remaining grouped/aggregate columns.

### Grouping and Aggregation

Each column can have one of three roles:

- `Not used` - ignored by aggregation.
- `Group` - used as a grouping key.
- `Aggregate` - aggregated with a function.

The function selector appears only for aggregate columns. Available aggregation
functions are role-aware and include:

- count rows,
- count values,
- unique count,
- sum,
- average,
- minimum,
- maximum,
- median,
- most frequent,
- first value,
- last value.

### Aggregation Filters

Aggregation filters apply after grouping, similar to SQL `HAVING`. Use them to
filter grouped rows, for example only groups where `records > 20` or
`Average churned >= 0.15`.

### Drill Down

When the browser is showing aggregated data, each grouped row has a drill action.
Drill down opens a detail view for the selected group. The detail view:

- respects the original base filters,
- starts from the original selected detail columns,
- has its own independent search, sorting, filters, paging, and column
  selection,
- does not mutate the parent aggregated view.

### Custom SQL

Custom SQL opens a modal editor. The SQL runs against an in-memory table named
after the selected dataset. If the dataset name contains spaces or other special
characters, quote it with double quotes:

```sql
SELECT
    region,
    COUNT(*) AS records,
    AVG(churned) AS avg_churn
FROM "Customer Churn"
GROUP BY region
ORDER BY avg_churn DESC
```

Only read-only `SELECT` and `WITH` queries are supported. The editor supports:

- Tab and Shift+Tab indentation,
- indentation carry-over on new lines,
- undo and redo,
- helper buttons for columns and common SQL functions,
- wrapping selected text with supported helper snippets where useful.

When Custom SQL is active, the Custom SQL button is highlighted. Reset View
returns to the original dataset preview and clears the active SQL state.

## Data Views

Save View persists the current browser state as a Data View. A view stores:

- name,
- source dataset,
- definition,
- creator,
- creation timestamp,
- row count and column count,
- inherited data roles where applicable.

Data Views appear in Overview, Data, and Analysis. In Analysis they can be
selected like regular datasets and used with Data Roles and Data Browsing.

## Backend API

Important dataset endpoints:

- `POST /api/v1/datasets/upload` - upload CSV.
- `GET /api/v1/datasets` - list current user's datasets and views.
- `GET /api/v1/datasets/{dataset_id}/preview` - preview dataset or view.
- `POST /api/v1/datasets/{dataset_id}/query` - run read-only SQL.
- `PATCH /api/v1/datasets/{dataset_id}/metadata` - update metadata, including
  `data_roles`.
- `POST /api/v1/datasets/views` - save a Data View.
- `DELETE /api/v1/datasets/{dataset_id}` - soft-delete metadata and remove local
  physical file for file-backed datasets.

## Implementation Notes

- UI role helpers live in `frontend/src/analysis/dataRoles.ts`.
- Dataset use cases live in `backend/app/modules/datasets/service.py`.
- Query/view execution lives in `backend/app/modules/datasets/query_engine.py`.
- Source adapters live in `backend/app/modules/datasets/sources.py`.
