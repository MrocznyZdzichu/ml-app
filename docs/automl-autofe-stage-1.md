# AutoML + AutoFE — current implementation

The current integrated AutoFE scope is limited to binary classification,
multiclass classification, and regression over tabular data. Clustering and
time-series-specific feature generation are intentionally outside this stage.

## Execution contract

When `TrainingDefinition.auto_feature_engineering.enabled` is true, the AutoML
step consumes the Data Engineering output before a feature matrix exists. It:

1. profiles the complete declared training scope in DuckDB;
2. derives bounded model-aware recipes from one profiling pass;
3. creates or consumes an explicit validation holdout, or creates deterministic
   raw folds for explicit fold-local cross-validation;
4. fits the recipe only on the permitted training partition or fold-train rows;
5. transforms validation or fold-validation rows with that same fitted state;
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
ID and platform-owned `__mlapp_*` technical columns are excluded from estimator
features and AutoFE transformations.

## Recipe space and model capabilities

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

The backend algorithm catalog groups estimators into three input profiles:

- `scaled_dense`: standard scaling for linear, kernel, distance-based, neural,
  and other scale-sensitive estimators;
- `tree_unscaled`: imputation without numeric scaling for decision trees,
  forests, and boosting families;
- `non_negative`: min-max scaling for estimators requiring non-negative input.

All candidates reuse one full-scope DuckDB profile. Candidate matrices and
models are run-scoped and temporary; only the refitted winner is persisted. The
study records recipe identity, compatible algorithms, resolved feature count,
trial history, score, failures, skipped candidates, and final selection.

Numeric recipes can independently compare:

- fold-local winsorization;
- signed `log1p` variants that retain the original column;
- standard, robust, min-max, or disabled scaling when compatible;
- distribution-driven log/square-root transforms and bounded arithmetic
  interactions; and
- constant/low-variance filtering.

Every learned bound and selector decision is fitted only on the permitted
training scope. Each candidate stores a versioned recipe contract, stable hash,
resolved features, and outcome. Candidates excluded by capabilities or budget
are recorded as `skipped`, not treated as evaluated.

Published definitions retain their historical search flags. New drafts opt into
the broader conditional space. Tree profiles avoid redundant scaling, and
non-negative estimators reject variants that can create negative values. The UI
defaults to 12 recipes and the backend enforces an absolute cap of 24.

The optional two-phase scheduler first explores every executable recipe, then
gives the remaining budget to deterministic top-K winners. It records allocated
and consumed budgets plus `promoted`, `pruned`, `explored`, `failed`, or
`skipped` status. Failed deepening falls back to successful exploration.

Distribution-driven numeric generation uses target-free minimum, maximum, mean,
standard deviation, skewness, zero share, and non-null coverage to:

- select `log1p`, square-root or signed-`log1p` only for non-constant columns
  whose absolute skewness crosses the configured threshold;
- rank numeric column pairs by target-free variability and coverage;
- create bounded multiply, subtract and zero-safe divide interactions;
- cap all generated columns by both an explicit width limit and a memory-aware
  capacity derived from the complete row count and training memory budget; and
- persist every generation reason, selected pair, transform, feature count and
  budget decision in recipe contract `3.0` and the model leaderboard.

Generated features must win the same leakage-safe validation as baseline
recipes. Scoring reuses the exact winner through the atomic inference bundle.

## Trial and time budgets

`max_trials` is a cap for the complete joint study. With the two-phase scheduler,
the exploration minimum is assigned first and the remaining budget is divided
between promoted recipes. With flat scheduling it is divided between all
selected FE recipe profiles. It is not a guaranteed number of completed trials
per profile. The wall-clock budget is divided as well. A recipe may therefore
finish fewer allocated trials when its timeout expires, while retaining its
best successful trial. With cross-validation, the approximate model-fit cost is
`completed trials × fold count`, plus fold-local FE preparation and the final
winner refit.

The editor reports the global cap, approximate per-recipe allocation, fold count
and estimated maximum fits. Result views report the configured joint budget and
completed trials across recipes, and distinguish timeout from reaching the
trial cap. Search spaces contain only complete executable combinations. For
example, histogram gradient boosting does not automatically sample
`loss=quantile` until the conditional `quantile` value is represented in the
search-space contract, although users may still configure it explicitly.

## Honest limitations

Current coordination changes numeric preprocessing by estimator capability and
jointly compares bounded one-hot/frequency, hashing, cross-fitted target mean,
and ordered target encoding. The target-free numeric planner includes
rule-selected nonlinear transforms and arithmetic interactions.
Planner v3 adds fold-local supervised selection with mutual information,
ANOVA/F-test, chi-square for non-negative classification inputs, embedded L1 and
ExtraTrees importance. Every selector uses the complete permitted training
scope, performs score-ordered correlation pruning, persists selected/dropped
features and records between-fold selection frequency. Compact, balanced and
wide widths are separate joint-search candidates. A hard memory preflight fails
instead of sampling when the complete selector matrix exceeds its budget.

Planner v4 adds bounded categorical hashing, cross-fitted target-mean encoding
and ordered target encoding. Binary classification stores one positive-class
encoding; multiclass stores bounded one-vs-rest outputs. Validation, test and
scoring reuse global smoothed statistics from the pinned fitted state, while a
training row never receives an encoding fitted from its own target. Unknown
categories use the training prior (or a deterministic hash bucket). Existing
one-hot/frequency recipes remain competitors.

Native categorical execution is deliberately not claimed yet. The catalog can
identify capable estimators, but the common training matrix adapter is numeric;
native execution needs a dedicated CatBoost-compatible matrix and scoring
adapter. No numerically encoded recipe is labelled as native. Learned symbolic
interactions, Yeo-Johnson and quantile transformations also remain future work.

Before the trial/time scheduler runs, a deterministic family round-robin applies
the configured recipe cap across base/numeric, supervised-selection,
categorical, and combined candidates. This prevents an earlier numeric generator
from consuming the complete cap before later families are represented. The
generated and scheduled family counts, order and cap are stored in provenance.
Definitions without v3/v4 feature flags retain the historical ordered-prefix
selection, preserving published search spaces.

The UI deliberately avoids planner-version names. Configuration is grouped by
data split and experiment size, budget allocation, numeric preparation,
target-guided selection, and categorical encoding. Information tooltips explain
the effect and trade-offs of technical parameters without changing their
backend contract.

## Immutable training report

Every successful Training and AutoML step now emits a separate immutable
`training_evaluation_report` artifact in addition to model and metrics
artifacts. The shared report envelope reserves a distinct
`monitoring_performance_report` type without changing the monitoring workflow.
The training report stores full-scope metrics, validation/search provenance,
the selected AutoFE recipe, fitted selector decisions, model parameter summary,
diagnostics and bounded explainability.

Permutation importance and SHAP are calculated only for the selected winner on
a deterministic, explicitly reported sample. Linear and tree estimators use
native bounded SHAP explainers; unsupported estimators retain permutation
importance with an explicit reason. Explainability sampling is never presented
as the scope of model metrics. Reports are accessible from official run
artifacts and temporary dry-run previews.

## Fold-local cross-validation

Integrated AutoFE supports explicit `cross_validation` for tabular
classification and regression. Fold assignment is deterministic, uses the
stable row ID and configured seed, and happens on the raw pre-FE relation.
Classification uses stratified folds; regression uses deterministic K-fold.

For every estimator/hyperparameter candidate and every fold, the engine fits a
fresh copy of the complete FE recipe only on fold training rows, transforms the
fold validation rows with that fitted state, and records the fold score. The
same raw folds are reused for every recipe and model candidate. After selection,
the winning recipe and estimator are refitted on the complete training scope.
The study provenance records fold counts, row counts, seed, assignment stage,
recipe hashes, fold scores, and resolved feature counts.

Fold-local feature matrices are cached inside the candidate run. The cache key
binds the recipe hash, raw train/validation fold relations, fold number and
seed. The first trial materializes each fold once; subsequent model and
hyperparameter trials reuse those Parquet outputs. Cache hits/misses and keys
are recorded, and the complete candidate directory is removed when its recipe
study ends.

Every successful trial records a bounded full-training-scope OOF summary:
prediction coverage/count, fold count, mean, row-weighted mean, standard
deviation and min/max fold score. Row-level predictions for every losing trial
are deliberately not persisted because that would multiply dataset-sized
artifacts by trials and recipes. Provenance explicitly reports
`predictions_persisted: false`; persisting only the winning OOF dataset remains
a separate artifact-retention decision.

Existing holdout definitions remain unchanged. Human-authored FE pipelines also
remain supported; if their transformations were fitted on the complete training
partition, they cannot be reused for CV. Fold-local AutoFE therefore requires a
pre-FE input (normally the Data Engineering output). This guard prevents a
globally fitted human recipe from being misreported as leakage-safe CV.

Fold-local trials currently run serially for deterministic run-directory and
memory isolation. Group/time folds, a retained winning OOF dataset, and
fold-local execution of arbitrary human-authored FE recipes remain future work.

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
