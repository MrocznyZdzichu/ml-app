# Model Training and Test Scoring — Stage 1

The expanded workbench replacing the provisional estimator catalog is
documented in [model-training-workbench.md](model-training-workbench.md).

This increment adds two executable high-level steps:

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

Stage 1 supports incremental logistic SGD, Passive-Aggressive PA-I and
Perceptron classification, plus incremental linear SGD and Passive-Aggressive
PA-I regression. They process the complete declared relation in bounded
batches, use a deterministic seed, reject invalid numeric features, and persist
their ordered feature contract. There is no silent sampling. Each algorithm has
its own validated parameter allowlist; changing the algorithm resets the UI to
safe defaults for that estimator.

When Feature Engineering exposes an explicit validation output, Training can
use a maximum epoch budget with validation-based early stopping. Patience,
minimum improvement, executed epochs, validation history and the restored best
epoch are persisted with the metrics. Validation is never inferred from a
mutable or implicit dataset.

Official runs create lineage-backed `model_version` and `metrics` artifacts.
Dry-runs keep them temporary but may pass the model directly to scoring in the
same run.

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

Deployment, online endpoints, arbitrary Python and distributed training remain
outside this historical increment. AutoML and fold-local AutoFE were delivered
in later increments and are documented in `automl-autofe-stage-1.md`; they are
now executable lifecycle blocks rather than future placeholders.

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
