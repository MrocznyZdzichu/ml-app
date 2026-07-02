# Feature Engineering — Stage 1 contract

The first Feature Engineering increment adds a second executable high-level
pipeline step. A workflow may contain Data Engineering followed by Feature
Engineering, or a standalone Feature Engineering step whose inputs point to
owned datasets.

Feature Engineering is not another list of data-cleaning blocks. Its defining
contract separates an immutable feature recipe from state fitted on a declared
training input:

```text
PipelineVersion recipe
        + training dataset
        -> fitted feature transform artifact
        -> training / validation / test feature datasets
```

Validation, test, and scoring inputs are transformed with the training state.
They never contribute statistics or category dictionaries.

## Holdout splits and cross-validation plans

The step can consume pre-existing training/validation/test datasets or derive a
deterministic holdout before fitting any transformation:

- random split keyed by a stable row ID and seed,
- stratified split preserving target-class proportions,
- group split keeping every entity in exactly one partition,
- chronological split using the oldest rows for training and newest for test.

Generated splits write separate training, validation, and test Parquet outputs.
Their requested shares, exact realized row counts, strategy, seed, and relevant
column bindings are persisted in each output manifest.
The high-level FE step exposes those datasets through matching `training`,
`validation`, and `test` DAG ports. Downstream lifecycle steps must bind the
partitions explicitly; execution never infers a validation or test dataset from
the first or latest output. Fit mode additionally exposes a
`fitted_transform` artifact port.

Optional cross-validation adds `__mlapp_cv_fold` to the training output.
Supported plans are K-fold, stratified K-fold, group folds, and ordered time
folds. Fold counts and row counts are persisted for audit. This is a **fold
plan**, not model evaluation: no estimator is trained in Feature Engineering.
The future Training step must join the plan to the prepared input and fit a
fresh copy of the FE recipe inside each fold. Using one preprocessing state
fitted on the whole training partition to report CV metrics would leak
information between folds.

## Supported operations

The nested `FeatureEngineeringDefinition` supports:

- missing-value imputation using constant, training mean, median, or mode,
- standard, min-max, and robust numeric scaling,
- bounded ordinal, one-hot, and frequency encoding,
- rare/unseen category policies,
- date/time component extraction and optional cyclical values,
- explicit add, subtract, multiply, and divide interactions,
- square, square-root, exponential, logarithmic, `log1p`, and absolute-value transforms,
- controlled scalar DuckDB SQL expressions that cannot contain queries,
  subqueries, external reads, or arbitrary Python,
- PCA fitted on the complete training partition and reused unchanged for
  validation, test, and scoring.

One-hot encoding requires an explicit maximum of at most 500 categories. The
engine derives its dictionary from all training rows, preserves deterministic
category order, and exposes an `other` column or fails on unseen categories
according to the selected policy.

PCA computes full-data moments in DuckDB and performs eigendecomposition only
on the bounded feature-by-feature covariance matrix. A block accepts at most
200 numeric inputs and 50 components. Missing values must be handled earlier
in recipe order. Means, components, explained variance, and optional whitening
state are stored in the fitted transform artifact.

The current increment deliberately excludes target encoding, WoE, supervised
feature selection, arbitrary Python, embeddings, historical windows, and
point-in-time joins. Those require cross-fitting, entity/event-time contracts,
or a separate resource and security model.

## Fit and transform modes

`fit_transform` requires one input with role `training`. Optional validation and
test inputs may point to separate datasets. The run:

1. scans every training row in DuckDB,
2. fits each stateful transformation in recipe order,
3. applies the fitted state to every declared input,
4. writes one full-scope Parquet dataset per configured output,
5. writes an engine-neutral JSON fitted-state artifact.

Transformation order is executable semantics. Every block sees the columns
created by all earlier blocks, and the final feature-role contract is evaluated
against the resulting schema. Feature datasets retain all recipe output
columns, while the feature manifest marks the explicitly selected model
features and keeps other columns as protected metadata or passthrough.

`transform` requires a pinned `fitted_state_artifact_id`. The platform rejects
missing, foreign, or non-feature artifacts and verifies the recipe hash before
execution. It never resolves a state artifact by a mutable "latest" alias.

The state is JSON rather than pickle/joblib. It contains scalar statistics,
category dictionaries, the definition and recipe hashes, feature roles, and the
output feature manifest. This keeps the initial executor auditable and avoids
loading executable Python serialization.

## Output contracts and audit

Official feature datasets are Zstandard-compressed Parquet assets registered in
the Business Case. Dataset metadata includes:

- full row count and `data_scope: full`,
- output schema and deterministic schema hash,
- feature manifest with stable feature IDs, types, and roles,
- input artifact IDs, pipeline version/hash, run ID, and step ID.

The fitted transform is an `Artifact` with type `feature_transform`. It records
the state hash, recipe/definition hashes, feature manifest, location, and the
same lineage anchors. Dry-runs keep both datasets and state temporary.

Every executed high-level step also creates a `PipelineStepRun` with status,
timestamps, row counts, warnings, output manifest, and an isolated error.
Running only the FE step executes its required DE ancestor and stops after FE;
the platform never silently chooses a previous intermediate output.

## Scale and execution

DuckDB remains the first execution adapter. Inputs are lazy CSV/Parquet
relations, intermediate DE output is passed to FE as Parquet, and no full table
crosses the API or browser boundary. Fitted statistics are aggregate queries
over all training rows.

Actual estimator fitting and fold-metric aggregation are not implemented yet.
A feature dataset fitted once on all training rows is appropriate for an
explicit holdout workflow and final model fit, but must not be used to report
fold-based metrics as though preprocessing had been fitted independently in
each fold.
