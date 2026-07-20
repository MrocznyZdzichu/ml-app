# Documentation map

Start with the document that matches the task. Files whose names still contain
`stage-1` keep their historical filenames so existing links do not break; their
content describes the current contract unless marked otherwise.

## Product and architecture

- [Estates demo bootstrap](estates-demo-bootstrap.md) — idempotent installation prerequisites and lifecycle boundary.

- [Architecture](architecture.md) — service boundaries, storage, analytics, and ML artifacts.
- [Development](development.md) — local workflow, checks, runtime tuning, and repository hygiene.
- [Synthetic ML scenarios](synthetic-ml-scenarios.md) — business meaning and generation contracts for demo data.

## Data and analysis

- [Analysis and Data Browser](analysis-data-browser-reference.md) — user behavior and API contracts.
- [Descriptive profiling performance](descriptive-profiling-performance.md) — execution path, limits, and benchmark.
- [Data Engineering](data-engineering-stage-1.md) — nested DE DAG, operations, execution, and audit.
- [Feature Engineering](feature-engineering-stage-1.md) — manual FE contract and its boundary with AutoFE.

## Machine learning lifecycle

- [Model Training workbench](model-training-workbench.md) — algorithms, optimization, leakage controls, and reports.
- [AutoML and AutoFE](automl-autofe-stage-1.md) — joint search, fold-local FE, selection, categorical encoding, and limits.
- [Training and Test Scoring](model-training-scoring-stage-1.md) — executable artifact path and score contract.
- [Batch Scoring](batch-scoring-stage-1.md) — immutable production predictions and inference bundle.
- [Monitoring](monitoring-pipeline-stage-1.md) — target joining, metrics, report, and lineage.
- [Online Model Serving](online-model-serving-stage-1.md) — versioned services, roles, secure predictions, fallback, replay, and Inference Log.

## Historical audits

- [Repository refactoring audit](refactoring-audit.md)
- [Repository refactoring audit — 2026-07](refactoring-audit-2026-07.md)

Audit files are dated snapshots. Use them to understand why a refactor was
made, not as the source of truth for current product capabilities.
