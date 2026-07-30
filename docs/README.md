# Documentation map

Choose a document by task. The root [`README`](../README.md) is the quick start;
this directory contains deeper references. Files with `stage-1` in their name
retain historical filenames so existing links keep working, but their content
describes the current contract unless it explicitly says otherwise.

## I want to use or run the application

- [Development workflow](development.md) - start, rebuild, test, inspect logs,
  and tune the local runtime.
- [Python client](../ml_app_client/README.md) - supported integration surface
  with short examples.
- [Executable API examples](../examples/API-usage/README.md) - numbered,
  idempotent notebooks covering the ML lifecycle.
- [Estates demo bootstrap](estates-demo-bootstrap.md) - install the prepared
  regression demonstration.
- [Synthetic ML scenarios](synthetic-ml-scenarios.md) - meaning, assumptions,
  and limitations of the checked-in demo datasets.

## I need a product or API contract

| Area | Document | Use it for |
| --- | --- | --- |
| Data and Analysis | [Analysis and Data Browser](analysis-data-browser-reference.md) | UI behavior, full-data versus preview scope, filters, views, visualizations, and API routes |
| Profiling | [Descriptive profiling performance](descriptive-profiling-performance.md) | execution path, limits, tuning, and benchmark method |
| Data Engineering | [Data Engineering](data-engineering-stage-1.md) | nested DAG, operations, data contracts, outputs, and audit |
| Feature Engineering | [Feature Engineering](feature-engineering-stage-1.md) | fitted state, supported transformations, train/validation boundaries |
| Training | [Model Training workbench](model-training-workbench.md) | algorithms, optimization, leakage controls, and evaluation report |
| AutoML | [AutoML and AutoFE](automl-autofe-stage-1.md) | search space, fold-local FE, budgets, and honest limitations |
| Scoring | [Training and Test Scoring](model-training-scoring-stage-1.md) | evaluated scoring and immutable artifacts |
| Batch inference | [Batch Scoring](batch-scoring-stage-1.md) | production prediction datasets and inference bundles |
| Batch monitoring | [Monitoring](monitoring-pipeline-stage-1.md) | actuals join, metrics, report, and lineage |
| Online serving | [Online Model Serving](online-model-serving-stage-1.md) | services, revisions, model roles, fallback, replay, and Inference Log |
| Online monitoring | [Online Service Monitoring](online-service-monitoring-stage-1.md) | manual full-scope monitoring from retained inference history |

## I am changing the code

- [Architecture](architecture.md) explains stable service, data, security, and
  client boundaries.
- [`CODEMAP.md`](../CODEMAP.md) points to current implementation entry points.
- Scope-specific `AGENTS.md` files contain invariants that automated coding
  agents must preserve. They are not product documentation.

The code and REST schemas are the final source of truth for exact fields. Update
the relevant reference, UI client, and Python client together when a public
contract changes.

## Historical engineering records

These dated files explain why earlier changes were made. They are snapshots, not
current backlogs or capability lists:

- [Repository refactoring audit](refactoring-audit.md)
- [Repository refactoring audit - 2026-07](refactoring-audit-2026-07.md)
- [Performance audit - 2026-07](performance-audit-2026-07.md)
- [UI scalability audit - 2026-07](ui-scalability-audit-2026-07.md)

For current structure and limitations, use the root README, architecture
document, code map, and feature references above.
