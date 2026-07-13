# AutoML + AutoFE — Stages 1–6

The first integrated AutoFE increment is limited to binary classification,
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

Stage 4 introduces a versioned recipe contract (`contract_version: 2.0`) and a
first bounded vertical slice of numeric feature generation and selection. New
pipeline drafts can compare each model capability baseline with an enhanced
recipe that:

- learns full-scope or fold-train winsorization bounds;
- adds signed `log1p` features while retaining the original numeric features;
- applies the model-compatible numeric scaling profile; and
- learns a constant/low-variance filter after feature generation.

Every learned bound and selector decision is fitted only on the permitted
training scope. Fold-local CV therefore learns distinct winsorization and
variance states inside every fold, while validation, test and scoring reuse the
pinned fitted state. The recipe contract, transform definition, selector,
stable recipe hash, resolved features and outcome are recorded per leaderboard
candidate. Candidates that cannot receive the minimum global trial/time budget
are recorded as `skipped` rather than silently treated as evaluated.

Definitions published before Stage 4 retain their historical search space.
Numeric feature search is enabled explicitly for new UI drafts, and the recipe
cap can be increased to compare baseline and enhanced capability profiles.

Stage 5 makes the numeric recipe space conditional instead of treating all
numeric improvements as one indivisible profile. New UI drafts independently
compare baseline, winsorized, signed-log and winsorized-plus-signed-log variants.
For scale-sensitive estimators they may additionally compare standard, robust,
min-max and disabled scaling. Tree profiles do not generate redundant scaling
variants, while non-negative estimators exclude signed-log variants that would
violate their input contract. The default UI cap is 12 and the absolute bounded
cap is 24; the global trial and time budgets still govern actual execution.

The joint-study provenance distinguishes generated, configured and executed
recipe counts. Every candidate excluded by the explicit recipe cap or by the
minimum trial/time allocation is retained as `skipped`, together with its recipe
contract and reason. Published definitions keep the historical recipe generator
unless the version-2 numeric search flag is explicitly enabled.

Stage 6 adds an opt-in two-phase scheduler, enabled by default for new UI drafts.
Every executable recipe first receives the configured small exploration budget
on the same holdout or raw fold plan. Successful recipes are ranked
deterministically by score and recipe ID; up to the configured top-K then share
all remaining global trials and wall-clock time in a deepening phase. Deepening
uses a deterministic seed offset so sampled estimator configurations are not a
replay of exploration, while the data split and leakage boundary stay unchanged.

The leaderboard stores both phase results and their allocated/consumed budgets.
Recipes are marked `promoted`, `pruned`, `explored`, `failed`, or `skipped`, with
promotion/pruning reasons. A failed deepening phase falls back to that recipe's
successful exploration result. The global `max_trials` and timeout remain hard
caps across both phases, and only the final winning path is persisted. Published
definitions without the scheduler flag keep the historical flat allocation.

Stage 7 adds the profile-aware numeric Planner v2, enabled for new UI drafts.
The planner extends the one-pass full-scope DuckDB profile with target-free
numeric aggregates: minimum, maximum, mean, population standard deviation,
skewness, zero share and non-null coverage. These statistics are used only to
propose bounded recipe candidates; the target is never inspected by feature
generation rules.

Planner v2 can:

- select `log1p`, square-root or signed-`log1p` only for non-constant columns
  whose absolute skewness crosses the configured threshold;
- rank numeric column pairs by target-free variability and coverage;
- create bounded multiply, subtract and zero-safe divide interactions;
- cap all generated columns by both an explicit width limit and a memory-aware
  capacity derived from the complete row count and training memory budget; and
- persist every generation reason, selected pair, transform, feature count and
  budget decision in recipe contract `3.0` and the model leaderboard.

The baseline and Stage 4-6 recipes remain candidates, so profile-aware features
must win the same leakage-safe joint validation rather than being enabled
unconditionally. Learned transformations and selectors remain fold-local.
Scoring reuses the exact winning recipe and fitted state through the atomic
inference bundle.

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
uses bounded one-hot/frequency encoding for all estimators. Planner v2 includes
target-free, rule-selected nonlinear transforms and arithmetic interactions.
The implemented selector remains unsupervised constant/low-variance filtering;
supervised feature selection, native categorical execution, target encoding,
learned symbolic interactions, Yeo-Johnson and quantile transformations are not
claimed yet.

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
