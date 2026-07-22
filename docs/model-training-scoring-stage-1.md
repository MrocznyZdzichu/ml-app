# Model Training and Test Scoring contract

The expanded workbench replacing the provisional estimator catalog is
documented in [model-training-workbench.md](model-training-workbench.md).

The lifecycle provides two executable high-level steps:

```text
Feature Engineering
  ├─ training ─> Model Training ─> immutable model artifact
  └─ test ───────────────────────────────┐
                                        v
                             Test Scoring ─> prediction dataset
```

Training requires an explicit `training` port. Scoring requires explicit
`data` and exact `model` artifact ports; it never resolves a mutable "latest"
intermediate result.

The estimator catalog contains executable classification and regression
families, including incremental and full-matrix algorithms; availability of a
few families depends on optional backend packages. Incremental estimators read
the full relation in bounded batches. Matrix-based estimators run a memory
preflight before materialization. All families use validated parameters and
deterministic seeds where supported, persist the ordered feature contract, and
never silently replace full-data training with a sample. The complete catalog
and resource behavior are documented in
[model-training-workbench.md](model-training-workbench.md).

When Feature Engineering exposes an explicit validation output, Training can
use a maximum epoch budget with validation-based early stopping. Patience,
minimum improvement, executed epochs, validation history and the restored best
epoch are persisted with the metrics. Validation is never inferred from a
mutable or implicit dataset.

Official runs create lineage-backed `model_version`, `metrics`, and
`training_evaluation_report` artifacts. Dry-runs keep them temporary but may
pass the model directly to scoring in the same run and expose a temporary
training-report preview. The report stores full-scope metrics, validation and
search provenance, a bounded model-parameter summary, and explainability.
Permutation importance is available as the common diagnostic; supported linear
and tree winners also receive SHAP. Explainability uses a deterministic bounded
sample that is reported separately from the full metric scope.

Scoring processes every input row in bounded batches and writes Parquet with
the required source row ID, prediction, optional class probability, and
optional actual target. With actuals, it reports full-scope accuracy or
MAE/RMSE. Official output is a `prediction_dataset` attached to the Business
Case as `scoring_output`.

Classification outputs use an explicit ranking-score contract:

- binary classifiers always write `prediction_score`, oriented toward the
  persisted positive class (by default `classes_[1]`);
- probabilistic binary classifiers additionally write
  `positive_class_probability`, which is exactly `P(y = positive_class)`, not
  the maximum probability of whichever class was predicted;
- margin classifiers write their `decision_function` value as
  `prediction_score`, which supports ROC/AUC but is not presented as a
  calibrated probability;
- multiclass classifiers write per-class probability or decision-score columns
  and persist the index-to-label mapping in `score_contract`;
- regressors do not emit artificial classification score/probability columns.

The dataset metadata records class labels, positive class, score kind and column
mapping so later analysis does not have to infer semantics from column names.

Registry refreshes use `GET /api/v1/models?summary=true` and
`GET /api/v1/scoring-reports?summary=true`. These bounded discovery contracts
exclude large metrics, trial histories, model parameters and evaluation bodies.
The model summary still contains the fitted-transform and workflow definitions
needed to configure batch scoring. `GET /api/v1/models/{model_id}` and
`GET /api/v1/scoring-reports/{report_id}` return the complete immutable detail.

Arbitrary Python steps, distributed training, and automatic production
deployment remain outside the current scope. AutoML and fold-local AutoFE are
executable lifecycle blocks documented in
[automl-autofe-stage-1.md](automl-autofe-stage-1.md).

## Custom lifecycle composition

The custom workflow editor exposes every currently executable lifecycle block:
Data Engineering, Feature Engineering, Training, AutoML, Test Scoring, and
Monitoring. Training and AutoML are mutually exclusive alternatives. The
recommended action follows the current DAG rather than a fixed visual style:

`DE -> FE -> Training or AutoML -> Test Scoring -> Monitoring`

An empty workflow therefore recommends Data Engineering. Test Scoring keeps
the actual target in its prediction dataset, so an optional Monitoring step may
consume that output directly and produce a full-scope performance report in the
same run. Production monitoring with delayed actuals remains a separate
workflow with an explicit target join.
