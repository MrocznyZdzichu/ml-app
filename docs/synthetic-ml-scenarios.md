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
