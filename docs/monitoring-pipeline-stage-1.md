# Monitoring pipeline — stage 1

Monitoring is a separate workflow from batch scoring. It never mutates the
immutable prediction dataset.

The executable template contains two high-level steps:

```text
prediction dataset + actuals dataset
  -> Process & Join (Data Engineering DAG)
       -> casts, category mappings, filters and quality checks
       -> validated key join
       -> prediction dataset enriched with target
  -> Performance Report
       -> bounded full-scope model metrics
```

## Contract

- `Infer from scoring run` pins one concrete immutable prediction dataset,
  scoring pipeline version and successful run.
- The actuals version remains an explicit pipeline input.
- Predictions use the `scoring_output` Business Case role.
- Actuals use the `monitoring_actuals` Business Case role.
- Prediction and actual keys may have different column names and compatible
  casts can be performed before the join.
- Actual labels can be normalized with `map_categories`, for example
  `setosa -> 0` and `versicolor -> 1`, then cast to the estimator output type.
- Null or duplicate keys fail the run to prevent accidental many-to-many joins.
- The execution uses a left join from predictions to actuals.
- Metrics use every joined row containing both prediction and target values.
- Missing actuals and actuals without predictions are reported separately.

## Outputs and lineage

An official run creates a new immutable Parquet Process & Join dataset
containing the joined target and a new report artifact. The report stores bounded
aggregates and chart data, not row-level copies. Dataset and report lineage
references the selected prediction and actuals artifacts, the pipeline version,
run, step and—when available—the pinned model artifact from batch scoring.

A dry-run creates only a temporary Parquet preview and does not register a
dataset or report.
