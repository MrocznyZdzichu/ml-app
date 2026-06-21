# Analysis and Data Browser Reference

This document describes the current Analysis tools and the metadata contracts
they rely on.

## Analysis Tabs

The Analysis workspace currently contains:

- `Data Roles` - durable semantic metadata for datasets and columns.
- `Data Browsing` - interactive preview, filtering, sorting, grouping,
  aggregation, Custom SQL, drill down, and Data View creation.
- `Descriptive Analysis` - explicit, role-aware descriptive profiling with
  univariate, comparison, target-aware, and segment summaries.
- `Visualization and Trends` - interactive, full-dataset dashboard composition and visual analysis.

Dataset selection is shared by Data Roles, Data Browsing, and Descriptive
Analysis. Visualization and Trends keeps an independent, session-scoped dataset
and dashboard state so entering the tab does not automatically execute work.

## Descriptive Analysis

Descriptive Analysis profiles a selected dataset only after the analyst clicks
`Run profiling`. Selecting a dataset loads lightweight configuration context for
target and target-type choices, but the heavier profiling work remains explicit.

For uploaded CSV datasets and materialized Data Views, profiling is submitted
to a background worker. The worker materializes a reusable Parquet
representation and computes statistics,
relationships, and segment aggregates over every row with DuckDB. Raw profile
rows are not transferred to the browser. The existing progress state remains
visible while the frontend polls the background job.

Successful profiles and their computed summaries are cached in frontend memory
for the authenticated session.
Switching to another dataset and then returning restores the latest profile and
its view settings without another profiling request. Cache entries are ignored
when the dataset `updated_at` value changes, and the entire cache is cleared on
logout or page refresh/close. Profiles are not written to localStorage or other
persistent browser storage. Restoring a matching entry reuses calculated column
profiles, relations, density/scatter data, segment results, and quality notes
instead of recalculating them from cached rows.

### Dataset Profile

The top Dataset Profile panel lets the analyst configure:

- dataset,
- target column,
- target type: automatic, categorical/classification, or continuous/regression,
- whether ignored and identifier columns are included,
- profiling range.

Automatic target-type inference treats boolean, text, categorical, ordinal, and
low-cardinality numeric targets as categorical. This keeps binary numeric
targets such as churn `0/1` in the classification-style path unless the analyst
overrides the setting.

### Profiling Range

Profiling Range controls the amount of work performed:

- Dataset summary and quality notes,
- Univariate column profiles,
- Target vs feature relations,
- Multivariate segment scan,
- Graphic summaries,
- graphic source-point limit,
- maximum target/comparison relation features,
- maximum segment scan features.

`Graphic summaries` is enabled by default. When disabled, profiling still
calculates tables and metrics but skips histogram, density, and scatterplot data
and rendering.

The graphic source-point limit does not limit the rows used by profile
statistics. Histograms, group distributions, correlations, contingency tables,
and segment scans aggregate the complete uploaded file. The limit only bounds
raw observations retained for graphics such as scatterplots.

### Univariate Profile

Univariate Profile is collapsible and has its own column selection modal. It
shows count, missing rate, unique count, mode, and numeric descriptive measures.

Numeric columns with low cardinality are displayed as discrete distributions
when graphic summaries are enabled. Continuous numeric columns use histograms.
When graphic summaries are disabled, only tabular facts and metrics are shown.

### Target vs Features

Target vs Features is also collapsible. By default it compares features against
the selected target, but `Compare by` can be changed to another column for more
general bivariate exploration.

The section supports:

- column selection with a modal selector,
- collapsible relation cards per feature,
- `Show all` and `Collapse all` for relation cards,
- ranking by relationship strength.

For a continuous feature compared with a categorical target/comparison column,
the card shows group-level rows, min, max, median, average, and standard
deviation. With graphic summaries enabled, it also shows KDE-like density curves
for each comparison group on a shared axis.

For two continuous variables, the card shows Pearson correlation, Spearman
correlation, R-squared, regression slope, intercept, and covariance. With
graphic summaries enabled, it also shows a scatterplot with a trend line.

Categorical-vs-categorical relations include a contingency table with counts,
row-normalized target percentages, lift, and Pearson residuals per cell.
The card also reports chi-square, degrees of freedom, Cramer's V, and the share
of sparse expected cells. Sparse tables display an exploratory-use warning.

For ordinal features with a binary target, the card additionally reports a
Spearman trend against the selected target value. Numeric ordinal labels are
ordered numerically. Backend full-file profiles use lexicographic order for
non-numeric labels and identify that basis explicitly, so analysts can verify
whether it matches the domain order.

### Multivariate Segment Scan

The segment scan evaluates every pair among the configured number of eligible
low-cardinality features. Ignored, identifier, and target columns are excluded.
Combinations below 3% of the profiled dataset (with an absolute minimum of five
rows) are excluded to reduce unstable small-group extremes. The UI shows the 12
highest-ranked results rather than only the single largest raw deviation.

For a categorical target, a binary target is focused on its less frequent class;
all classes are evaluated for a multiclass target. Each result reports:

- support (the segment's share of eligible target rows),
- segment target rate and the population baseline,
- absolute percentage-point difference and relative lift,
- a 95% Wilson interval for the segment rate,
- WRAcc (`support * (segment rate - baseline)`) as a coverage-adjusted ranking
  measure.

For a continuous target, each result reports the segment mean, population mean,
their difference, an approximate 95% interval around the segment mean, and
Cohen's d against the rest of the population. Ranking uses support multiplied by
Cohen's d, balancing standardized separation with segment coverage.

The scan is exploratory subgroup discovery. Reusing the same data to generate
and inspect many candidate segments creates selection and multiple-comparison
risk, so displayed intervals are descriptive and results do not establish
causality. Confirm important segments on validation data or with a model that
controls for confounding variables.

### Large Dataset Execution

Uploaded CSV files are copied to repository storage in chunks, so upload no
longer creates a second complete in-memory byte buffer. A streaming pass records
the row count and source schema. Dataset selection reads only lightweight schema
context and does not trigger Parquet materialization.

The first explicit profile creates `dataset.mlapp.parquet` beside the source CSV
and then performs the full scan. Later profiles reuse that artifact while the
source file modification time is unchanged. DuckDB can spill analytical work to
a dataset-local temporary directory rather than requiring the full relation in
RAM. Celery result data contains only compact aggregates and expires from Redis
after one hour; the existing frontend cache remains session-scoped.

Saved SQL and Browser Data Views are resolved recursively to their physical
source, compiled into validated DuckDB queries, and materialized as reusable,
definition-versioned Parquet artifacts. Filters, search, projection, grouping,
aggregation filters, and sorting are pushed into DuckDB. The cached view is
invalidated when its source Parquet or definition changes. Visualization and
descriptive profiling therefore use the complete Data View result without
materializing raw rows in the browser or Python process.

## Visualization and Trends

Selecting a dataset prepares schema context but does not create a dashboard.
The analyst starts with an empty canvas, adds charts manually, or explicitly
requests Smart start. Canvas state is saved in session storage per dataset;
returning to a dataset during the same browser session restores its layout.

Supported views include line, bar, scatter/density-bin, histogram, and KPI.
Charts can be moved and resized on a fine 48-column grid. Alignment guides snap
edges and centers, collision detection rejects overlapping placements, Tidy
layout creates a balanced grid, and Clear canvas removes all cards.

Chart configuration supports axes, primary and additional aggregations,
categorical grouping, and All/None/explicit group selection. A group keeps one
high-contrast color while its metrics use ordered line patterns (solid, dashed,
dash-dot, dotted, and further variants). Legends are scrollable and preserve
the rendered line pattern. Axes use adaptive ticks; charts support exact-value
tooltips, cursor-centered wheel zoom, buttons, range scrolling, and pan.

For numeric X axes in line and bar charts, `X epsilon` optionally reduces dense
continuous coordinates before aggregation. `epsilon = 0` preserves exact X
values. A positive epsilon creates non-overlapping buckets of width `2 × ε`,
anchored at zero and represented by their center. For example, `ε = 0.2`
aggregates values in `[0.8, 1.2)` into the point centered at `x = 1`. Epsilon is
stored independently for each chart, and tooltips report the bucket range and
row count.

The visualization endpoint scans the complete Parquet relation with DuckDB.
Line/bar aggregates, histograms, KPI values, group choices, and scatter density
bins therefore use the full selected dataset or Data View. Only bounded chart
results cross the API boundary. The UI reports `rows analyzed` and
`Full dataset · server-side`; it does not present a schema preview sample as an
analytical result.

When the number of aggregated points exceeds the response contract, the chart
explicitly marks the display as capped. Aggregation still scans the complete
selected relation, and `valid_count` continues to describe all matching rows;
only the points transferred to and rendered by the browser are bounded.

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

The interactive browser table is a bounded exploratory preview and reports both
returned and total row counts. Local filtering, searching, grouping,
aggregation, and sorting affect the currently returned preview rows. Custom SQL
uses the current interactive query path and also returns a bounded result.

Saving the state as a Data View changes the execution path: the persisted
filters, search, grouping, aggregation filters, projection, sorting, or SQL are
compiled into DuckDB and applied to the complete source relation. Downstream
visualization and descriptive analysis therefore operate on the full transformed
view rather than the browser preview.

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

Custom SQL opens a modal editor. During interactive Data Browser execution, SQL
runs against a bounded in-memory SQLite table named after the selected dataset.
If the dataset name contains spaces or other special characters, quote it with
double quotes:

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
After Save View, the same SQL definition is executed and cached by DuckDB over
the source Parquet for scalable downstream analysis.

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
selected like regular datasets and used with Data Roles, Data Browsing,
Visualization and Trends, and Descriptive Analysis. SQL and Browser views are
materialized as definition-versioned Parquet relations and can themselves be
used as sources of nested views.

## Backend API

Important dataset endpoints:

- `POST /api/v1/datasets/upload` - upload CSV.
- `GET /api/v1/datasets` - list current user's datasets and views.
- `GET /api/v1/datasets/{dataset_id}/preview` - preview dataset or view.
- `POST /api/v1/datasets/{dataset_id}/query` - run read-only SQL.
- `POST /api/v1/datasets/{dataset_id}/visualization` - execute a bounded,
  full-dataset chart query.
- `POST /api/v1/datasets/{dataset_id}/visualization/groups` - return complete
  grouping context with a bounded categorical result.
- `PATCH /api/v1/datasets/{dataset_id}/metadata` - update metadata, including
  `data_roles`.
- `POST /api/v1/datasets/views` - save a Data View.
- `DELETE /api/v1/datasets/{dataset_id}` - soft-delete metadata and remove local
  physical file for file-backed datasets.

## Implementation Notes

- UI role helpers live in `frontend/src/analysis/dataRoles.ts`.
- Dataset use cases live in `backend/app/modules/datasets/service.py`.
- Interactive query execution lives in
  `backend/app/modules/datasets/query_engine.py`; columnar relations, saved view
  pushdown, and cache materialization live in
  `backend/app/modules/datasets/columnar.py`.
- Full-dataset chart queries live in
  `backend/app/modules/datasets/visualizations.py`.
- Source adapters live in `backend/app/modules/datasets/sources.py`.
