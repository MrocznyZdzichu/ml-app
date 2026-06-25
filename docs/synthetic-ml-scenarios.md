# Synthetic ML scenarios

Both datasets are synthetic, deterministic, and safe for demos. Regenerate them with
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

Neither scenario contains missing data or hidden sampling. Every reported analysis
should state the processed row count and any visualization binning.
