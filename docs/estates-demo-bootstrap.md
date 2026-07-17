# Estates Sell Prices demo bootstrap

`examples/bootstrap_estates_sell_prices.py` provides an idempotent starting
point for a new ML App installation. Its versioned source manifest is
`examples/estates_bootstrap_manifest.py`.

## Installed prerequisites

The bootstrap verifies or creates:

- the globally named `Estates Sell Prices` Business Case;
- the 10,000-row `sale-prices` training dataset with role `source`;
- the 100,000-row scoring cohort with role `scoring_input`;
- the matching 100,000-row actuals dataset with role `monitoring_actuals`;
- the published `Estates Sell Prices - AutoFEML` training pipeline.

All files are streamed from `examples/data`. Repeated execution reuses attached
datasets and the published pipeline instead of creating new versions.

## Access and name conflicts

Business Case names are globally unique and case-insensitive. The workflow is:

1. Reuse the visible Business Case when it exists.
2. Create it when the name is unused.
3. If creation returns `409` and the Business Case remains invisible, stop with
   `AuthorizationError` and request access from an administrator or BC manager.
4. Require at least `contributor` before repairing datasets or pipelines.

The database uniqueness constraint makes concurrent Business Case creation
race-safe. Pipeline and attachment checks make normal repeated bootstrap runs
idempotent.

## Runtime artifact boundary

The current development installation also contains scoring and monitoring
pipelines produced around completed training and scoring runs. Those definitions
pin installation-specific model artifacts, fitted Feature Engineering state,
prediction datasets, and lineage. The portable manifest deliberately excludes
those UUIDs.

After bootstrap:

1. Run `Estates Sell Prices - AutoFEML` to create a new model and fitted state.
2. Infer a batch-scoring pipeline from that successful run.
3. Run batch scoring to create an immutable prediction dataset.
4. Infer and run monitoring with the attached actuals dataset.

This preserves reproducibility and prevents a new installation from appearing
to have executable model lifecycle artifacts that it has never produced.
