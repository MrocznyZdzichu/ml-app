# Synthetic ML scenarios

The generated datasets are synthetic, deterministic, and safe for demos. Regenerate them with
`python examples/generate_synthetic_datasets.py`. The seed is fixed at `20260624`.

## Dynamic reactor temperature — time-series regression

Business case: a process engineer wants a five-minute-ahead forecast of reactor
temperature. Early warning lets the control system reduce heater power before a
quality or safety limit is crossed, while avoiding an unnecessarily conservative
setpoint.

File: `examples/data/dynamic-reactor-timeseries.csv` (14,400 ordered observations,
50 days at five-minute intervals). It deliberately exposes only one temperature
column, `reactor_temperature_c`, plus timestamp, batch identifier and raw heater
and feed-flow signals. There are no prepared lag, derivative or future-target
columns. For a five-minute-ahead forecast, create the target by shifting
`reactor_temperature_c` by one row inside the chronological sequence; longer
horizons require larger shifts.

The generator remains a noisy first-order thermal system with a hidden multi-step
heater delay, thermal inertia, actuator ramps, feed-flow disturbances and an
unobserved periodic ambient-temperature driver. These dependencies are present in
the trajectory but are not handed to the model as engineered features. The data
scientist must diagnose autocorrelation, choose lag windows and derivatives, and
determine useful exogenous-signal delays. Random row splitting is invalid: evaluate
chronologically (for example first 70% train, next 15% validation, final 15% test)
and never use future rows to construct features.

## Equipment operating regimes — unsupervised clustering

Business case: a reliability team has telemetry but no trustworthy failure labels.
It wants to discover recurring operating regimes, characterize inefficient or
mechanically unstable behavior, and route the resulting segments to engineers for
interpretation before creating maintenance rules.

File: `examples/data/equipment-operating-regimes.csv` (12,000 observations from 240
machines). Numeric features describe load, power, vibration, bearing temperature,
acoustics, micro-stops, throughput, and load variability. The data contains three
overlapping latent regimes, but deliberately exposes no ground-truth cluster label:
clustering remains unsupervised. Scale numeric features, compare several cluster
counts with silhouette/stability measures, and use the PCA projection chart to
inspect separation. `observation_id` and `machine_id` are identifiers, not model
features.

Neither of these first two scenarios contains missing data or hidden sampling. Every reported analysis
should state the processed row count and any visualization binning.

## Iris batch scoring — two-class classification

Business case: validate the operational batch-scoring path for the Iris classifier
on a fresh, unlabeled delivery. The scoring input represents measurements whose
species will become available later, so performance evaluation must not occur in
the batch-scoring pipeline.

Files:

- `examples/data/iris-batch-scoring-10k.csv`: 10,000 scoring records with a stable
  `row_id` and the four measurement columns used by the reference Iris model. It
  deliberately contains no `species` target.
- `examples/data/iris-batch-scoring-10k-actuals.csv`: separately held actuals with
  `row_id` and `species`, intended only for a future target-joining and monitoring
  pipeline.

The hidden population is balanced: 5,000 Versicolor and 5,000 Virginica records.
For each class, the generator estimates the full four-dimensional sample covariance
matrix from `examples/data/iris.csv` and draws correlated multivariate observations.
Rejection bounds limit every measurement to the observed class range plus a 12%
margin and enforce basic botanical relationships such as petal length below sepal
length. Values are in centimeters, rounded to three decimal places, and contain no
missing data.

This is a synthetic operational batch, not independent biological evidence. Its
class balance is intentionally controlled and its distribution is derived from the
small 100-row, two-class reference subset, so it is suitable for pipeline validation
but not for estimating real-world prevalence or generalization.

## Iris three-class scoring performance cohort

Business case: stress-test the complete three-class batch-scoring and delayed-
actuals path on a sizable but locally practical cohort. It is intended for the
`Iris Species Recognition` Business Case, including a 3-class AutoML model.

Files:

- `examples/data/iris-3class-batch-scoring-200k.parquet`: exactly 200,000
  scoring records with `row_id`, `sepal_length`, `sepal_width`, `petal_length`
  and `petal_width`. It deliberately contains no `species` column.
- `examples/data/iris-3class-batch-scoring-200k-actuals.parquet`: 200,000
  delayed labels with `row_id`, `species` and `actual_observed_at`.

Use `row_id` as the stable key in scoring and target joining. `species` is the
actual target. The input contains 60,000 Setosa (30%), 72,000 Versicolor (36%)
and 68,000 Virginica (34%) observations, so prevalence differs from the balanced
reference set. Each species is generated from the full empirical four-dimensional
covariance of `iris.csv`; measurements keep the original cross-feature
correlations and botanical constraints. Four collection waves add a small bounded
covariate drift (stronger in length measurements), while labels become available
28, 35, 42 or 49 days after scoring. There are no missing values and actuals join
one-to-one with inputs. This is a deterministic synthetic benchmark (seed
`20260624`), not biological evidence or a real-world prevalence estimate.

The files are Parquet compressed with Zstandard. The generator streams CSV staging
rows and converts them with DuckDB, so generation does not materialize the 200k
cohort as a Python object graph. A generator contract test verifies schema,
counts, class allocation, key coverage and deterministic regenerated values on a
smaller 4,000-row instance.

## Customer churn batch scoring and delayed actuals

Business case: a subscription-retention team trained a churn classifier on
`examples/data/general-example.csv`. At the start of each monthly campaign it
scores active customers without knowing their future outcome. After the observation
window closes, the CRM supplies actual churn outcomes for performance monitoring.
Batch scoring and target joining are deliberately separate workflows.

Files:

- `examples/data/general-churn-batch-scoring-10k.csv`: 10,000 customers from the
  July-September 2026 scoring cohorts. Its schema matches the training features,
  including the stable `customer_id`, and deliberately excludes `churned`.
- `examples/data/general-churn-batch-scoring-10k-actuals.csv`: delayed outcomes
  containing only `customer_id` and the binary `churned` target. It is the actuals
  input for a monitoring pipeline, not an input to batch scoring.

The generator uses the complete training file as a label-stratified empirical
population model, creates new non-overlapping customer identifiers, perturbs every
numeric observation, and applies mild operational drift: fees and usage increase,
discounts contract, competitor pricing becomes slightly more attractive, and NPS
softens. Categorical combinations and target relationships remain grounded in the
training scenario. The scoring cohort has exactly 600 churners (6.0%), compared
with 478 (4.78%) in the 10,000-row training dataset, making prevalence drift visible
without turning the example into an extreme stress test.

There are no missing values or sampled analysis results. The two files join
one-to-one on `customer_id`; scoring contains 10,000 rows and monitoring actuals
cover all 10,000. This synthetic batch is intended to validate scoring, lineage,
target joining, and monitoring behavior. It is not evidence of production model
quality or real customer prevalence.
