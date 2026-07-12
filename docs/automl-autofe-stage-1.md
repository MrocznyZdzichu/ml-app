# AutoML + AutoFE — Stages 1 and 2

The first integrated AutoFE increment is limited to binary classification,
multiclass classification, and regression over tabular data. Clustering and
time-series-specific feature generation are intentionally outside this stage.

## Execution contract

When `TrainingDefinition.auto_feature_engineering.enabled` is true, the AutoML
step consumes the Data Engineering output before a feature matrix exists. It:

1. profiles the complete declared training scope in DuckDB;
2. derives bounded model-aware recipes from one profiling pass;
3. creates or consumes an explicit validation holdout before fitting state;
4. fits the recipe only on the training partition;
5. transforms validation with that same fitted state;
6. jointly compares recipe, estimator-family and hyperparameter candidates;
7. refits the winning recipe and estimator on the complete training partition;
8. resolves the runtime Feature Manifest and persists the fitted transform,
   model, metrics, and complete study provenance with the
   model and metrics artifacts.

There is no silent row sampling. Approximate distinct counts are used only for
bounded categorical-planning decisions and are explicitly recorded as an
approximation together with the number of profiled rows.

If an explicit validation input is not connected, the definition must provide
a stable `row_id_column`. Classification uses a deterministic stratified
holdout and regression uses a deterministic random holdout. The target and row
ID are excluded from estimator features.

## Planner and model capability profiles

The shared `balanced` base recipe supports:

- median imputation and optional missingness indicators for numeric columns;
- standard, robust, min-max, or disabled numeric scaling;
- bounded one-hot encoding for low-cardinality categoricals;
- bounded frequency encoding for higher-cardinality categoricals;
- calendar components for ordinary tabular datetime columns;
- exclusion of unsupported physical types;
- conservative exclusion of near-unique categorical columns whose names look
  like identifiers.

The generated feature matrices are run-scoped intermediate Parquet files. The
engine-neutral fitted transform remains a registered artifact required for
reproducible scoring.

Stage 2 exposes declarative FE capabilities in the backend-owned algorithm
catalog and groups candidates into bounded profiles:

- `scaled_dense`: standard scaling for linear, kernel, distance-based, neural,
  and other scale-sensitive estimators;
- `tree_unscaled`: imputation without numeric scaling for decision trees,
  forests, and boosting families;
- `non_negative`: min-max scaling for estimators requiring non-negative input.

All profiles reuse one full-scope DuckDB profiling result. The configured trial
and wall-clock budgets are divided between the selected profiles. Candidate
matrices and models are temporary and removed after evaluation. The winner is
refitted once and only its engine-neutral fitted transform and model are
persisted. The joint study records every recipe profile, compatible algorithms,
resolved feature count, trial history, score, failure, and final selection. If
the configured recipe cap excludes an estimator capability profile, the run
records the skipped algorithms and emits an explicit warning instead of silently
treating them as evaluated.

## Honest limitations

Current coordination changes numeric preprocessing by estimator capability and
uses bounded one-hot/frequency encoding for all estimators. Native categorical
execution, supervised feature selection, target encoding, and learned feature
interactions are not claimed yet.

Cross-validation is rejected while integrated AutoFE is enabled. Leakage-safe
CV requires fitting a fresh feature recipe inside every fold. Fold-local FE is
the next execution stage; current joint comparison uses one leakage-safe
holdout shared by every candidate.

## Reusing Data Engineering in AutoML drafts

An AutoML pipeline created from the AutoML template exposes **Infer Data
Engineering**. The dialog lists only pipelines with the `training` purpose in
the same Business Case and requires an explicit pipeline version. Applying the
action copies only the nested Data Engineering definition into the existing
AutoML DE step. The target step ID and downstream workflow connections remain
stable, and the copied definition is immediately editable.

The resulting draft records the source pipeline ID and name, exact version ID
and number, version status, definition hash, and source DE step ID. This is a
copy-time authoring convenience, not a runtime dependency between pipelines;
later edits or runs of the source pipeline cannot change the AutoML draft.
