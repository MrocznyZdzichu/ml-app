# Batch Scoring — Stage 1

Batch scoring and model-performance monitoring are separate workflows.

```text
Batch scoring
  scoring dataset -> inference-safe DE -> fitted FE transform -> pinned model
                  -> immutable prediction dataset

Monitoring (future)
  prediction dataset + actuals -> target join -> performance metrics/report
```

## Batch-scoring contract

- The scoring dataset is selected explicitly for every run from datasets attached
  to the same Business Case.
- The run records the exact immutable dataset version.
- The model version and fitted Feature Engineering state are pinned artifacts.
- Feature Engineering runs only in `transform` mode. It never fits statistics or
  categories on scoring data.
- Batch input has no target column and the scoring step does not create a
  performance evaluation or Scoring Report.
- A successful official run creates an immutable Parquet prediction dataset with
  the source row ID, prediction and the model's score/probability columns.
- Row IDs are validated over the full input and must be non-null and unique.
- Artifact lineage includes the input dataset, fitted transform, model version,
  pipeline version and run.

## Inference-safe Data Engineering

The generated scoring workflow reuses only deterministic preparation needed to
meet the model input contract:

- column projection;
- renaming and type casts;
- stable hash-based identifiers;
- deterministic derived columns;
- fixed category mappings.

Training-only filtering, sorting, deduplication, aggregation, joins, unions,
batch-fitted imputation, custom SQL and sequence IDs are not automatically
accepted in the batch-scoring preparation snapshot. Target-dependent
configuration is removed or rejected.

## Monitoring boundary

Predictions are never updated in place when actuals arrive. A later monitoring
pipeline will join an immutable prediction dataset with an actuals dataset using
declared business keys and observation-time rules, then create a new labeled
prediction artifact and performance report.
