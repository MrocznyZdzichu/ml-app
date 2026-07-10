# Model Training workbench

The high-level Training pipeline and its typed ports are unchanged. This
workbench is the nested domain editor and execution engine of the existing
`Model Training` step.

## Algorithm catalog

The backend owns a versioned catalog exposed at
`GET /api/v1/pipelines/model-training/catalog`. The frontend renders estimator
and hyperparameter controls from this catalog, so validation, defaults, search
spaces, availability, scale guidance, and UI labels have one source of truth.

The initial catalog contains 52 executable classification and regression
algorithms:

- linear, sparse, robust, and generalized linear models;
- online SGD, Passive-Aggressive, and Perceptron learners;
- linear, RBF, polynomial, and Nu SVM/SVR variants;
- decision trees, random forests, extremely randomized trees;
- AdaBoost, classic gradient boosting, and histogram boosting;
- XGBoost, LightGBM, and CatBoost CPU adapters;
- configurable dense MLP neural networks for tabular data;
- Gaussian, Bernoulli, and Complement Naive Bayes;
- LDA, QDA, k-nearest neighbours, and explicit dummy baselines.

Each entry declares compatible problem types, typed parameters, defaults,
curated optimization ranges, dependency availability, probability support,
execution mode, and a scale profile.

## Optimization

`TrainingDefinition.optimization` supports:

- `single`;
- `grid_search`;
- `random_search`;
- `optuna`;
- `automl`.

Every search has an explicit trial limit, wall-clock budget, primary metric,
validation strategy, fold count, and deterministic seed. AutoML searches both
the estimator family and its conditional hyperparameters. The selected
algorithm, resolved parameters, best score, per-fold scores, bounded trial
history, elapsed time, failures, and timeout state are persisted in the model
and metrics artifacts. The selected estimator is refitted on the complete
training partition.

## Evaluation and leakage controls

An explicit validation output from Feature Engineering is preferred for model
selection. It is transformed with state fitted only on the training partition.

Cross-validation consumes the auditable `__mlapp_cv_fold` plan when Feature
Engineering provides it, including ordered expanding-window semantics for time
folds. If no plan exists, deterministic stratified K-fold or K-fold splitting
is available only for an input without fitted FE transformations.

The engine refuses to report CV scores when upstream preprocessing state was
fitted once on the complete training partition. Correct fold-local refitting
requires the original FE recipe and is a separate execution capability; until
then the user must provide an explicit validation partition. The platform never
silently substitutes a sample or a potentially leaked score.

## Full-data and resource behavior

Incremental estimators scan every selected training row in bounded batches.
Algorithms that require a complete matrix perform a conservative memory
preflight and then enforce the measured allocation against
`resource_limits.max_memory_mb`. Exceeding the limit fails with the full row and
feature scope in the error and recommends either increasing the explicit budget
or selecting a streaming estimator.

Search parallelism is explicit and bounded. Estimators and searches do not
silently sample the input. Run counters include the full training rows processed
across folds/trials and the final refit.

## Compatibility with scoring and monitoring

The output remains an immutable `model_version` artifact using the existing
`model` port and bundle contract. Batch and test scoring continue to consume the
same feature list and produce the same score contract. Arbitrary class labels
are encoded internally for XGBoost and LightGBM and decoded before predictions
are persisted, so downstream monitoring keeps the original target vocabulary.

The bounded model-parameter summary now supports both linear coefficients and
tree feature importance. Training metrics and optimization provenance remain
separate from row-level prediction datasets.
