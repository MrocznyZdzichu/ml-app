"""Regenerate the checked-in synthetic ML examples with deterministic seeds."""

from __future__ import annotations

import csv
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


OUTPUT = Path(__file__).resolve().parent / "data"
IRIS_SOURCE = Path(__file__).resolve().parent / "data" / "iris.csv"
SEED = 20260624
IRIS_FEATURES = ("sepal_length", "sepal_width", "petal_length", "petal_width")


def write_dynamic_reactor() -> None:
    random.seed(SEED)
    path = OUTPUT / "dynamic-reactor-timeseries.csv"
    start = datetime(2025, 1, 1, tzinfo=UTC)
    temperature = 58.0
    previous_temperature = temperature
    previous_flow = 42.0
    heater_history = [35.0] * 3
    rows: list[dict[str, object]] = []
    for index in range(14_400):
        timestamp = start + timedelta(minutes=5 * index)
        batch_id = f"B{index // 576 + 1:03d}"
        daily = math.sin(2 * math.pi * index / 288)
        ambient = 18.0 + 5.5 * daily + random.gauss(0, 0.35)
        step = (index // 96) % 5
        heater = 31.0 + step * 9.0 + 7.0 * math.sin(2 * math.pi * index / 173) + random.gauss(0, 1.1)
        heater = max(5.0, min(92.0, heater))
        feed_flow = 40.0 + 6.0 * math.sin(2 * math.pi * index / 211) + (4.5 if (index // 288) % 3 == 1 else -1.5) + random.gauss(0, 0.55)
        flow_change = feed_flow - previous_flow
        delayed_heater = heater_history[0]
        equilibrium = ambient + 0.92 * delayed_heater - 0.34 * feed_flow
        # First-order thermal inertia plus a small response to actuator/feed derivatives.
        next_temperature = temperature + (5.0 / 47.0) * (equilibrium - temperature) + 0.045 * (heater - heater_history[-1]) - 0.11 * flow_change + random.gauss(0, 0.16)
        rows.append({
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "batch_id": batch_id,
            "heater_command_pct": round(heater, 4),
            "feed_flow_l_min": round(feed_flow, 4),
            "reactor_temperature_c": round(temperature, 4),
        })
        previous_temperature, temperature = temperature, next_temperature
        previous_flow = feed_flow
        heater_history = [*heater_history[1:], heater]
    write_csv(path, rows)


def write_equipment_clustering() -> None:
    rng = random.Random(SEED + 1)
    path = OUTPUT / "equipment-operating-regimes.csv"
    regimes = [
        # Efficient steady load, overloaded/hot, mechanically unstable.
        (0.52, (62, 118, 1.7, 71, 8.2, 0.07, 84, 0.8)),
        (0.28, (88, 191, 3.0, 91, 11.6, 0.14, 108, 1.6)),
        (0.20, (49, 136, 5.7, 79, 15.8, 0.25, 91, 3.9)),
    ]
    cumulative = [regimes[0][0], regimes[0][0] + regimes[1][0], 1.0]
    rows: list[dict[str, object]] = []
    for index in range(12_000):
        draw = rng.random()
        regime_index = 0 if draw < cumulative[0] else 1 if draw < cumulative[1] else 2
        _, center = regimes[regime_index]
        load, power, vibration, bearing_temp, acoustic, stop_rate, throughput, variability = center
        latent_load = rng.gauss(0, 1)
        rows.append({
            "observation_id": f"OBS-{index + 1:06d}",
            "machine_id": f"MC-{rng.randrange(1, 241):03d}",
            "motor_load_pct": round(load + 6.2 * latent_load + rng.gauss(0, 2.8), 4),
            "power_kw": round(power + 10.5 * latent_load + rng.gauss(0, 6.5), 4),
            "vibration_rms_mm_s": round(max(0.1, vibration + 0.28 * latent_load + rng.gauss(0, 0.42)), 4),
            "bearing_temp_c": round(bearing_temp + 2.7 * latent_load + rng.gauss(0, 2.1), 4),
            "acoustic_rms_db": round(acoustic + 0.7 * latent_load + rng.gauss(0, 0.9), 4),
            "micro_stop_rate_per_h": round(max(0, stop_rate + rng.gauss(0, 0.035)), 4),
            "throughput_units_h": round(max(1, throughput + 7.5 * latent_load + rng.gauss(0, 5.0)), 4),
            "load_variability_pct": round(max(0.1, variability + rng.gauss(0, 0.55)), 4),
        })
    rng.shuffle(rows)
    write_csv(path, rows)


def write_iris_batch_scoring() -> None:
    """Create an unlabeled scoring batch plus separately held actuals.

    Each class is sampled from the class-conditional multivariate distribution
    estimated from the checked-in Iris reference data. Rejection bounds keep the
    synthetic measurements within a small margin around observed botanical ranges.
    """

    rng = random.Random(SEED + 2)
    reference: dict[str, list[list[float]]] = {
        "versicolor": [],
        "virginica": [],
    }
    with IRIS_SOURCE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            species = str(row["species"])
            if species in reference:
                reference[species].append([float(row[name]) for name in IRIS_FEATURES])

    generated: list[tuple[str, list[float]]] = []
    for species, samples in reference.items():
        means = [
            sum(row[index] for row in samples) / len(samples)
            for index in range(len(IRIS_FEATURES))
        ]
        covariance = sample_covariance(samples, means)
        factor = cholesky(covariance)
        lower = [
            min(row[index] for row in samples)
            - 0.12 * (max(row[index] for row in samples) - min(row[index] for row in samples))
            for index in range(len(IRIS_FEATURES))
        ]
        upper = [
            max(row[index] for row in samples)
            + 0.12 * (max(row[index] for row in samples) - min(row[index] for row in samples))
            for index in range(len(IRIS_FEATURES))
        ]
        class_rows: list[list[float]] = []
        while len(class_rows) < 5_000:
            standard = [rng.gauss(0, 1) for _ in IRIS_FEATURES]
            values = [
                means[row] + sum(factor[row][column] * standard[column] for column in range(row + 1))
                for row in range(len(IRIS_FEATURES))
            ]
            if not all(lower[index] <= value <= upper[index] for index, value in enumerate(values)):
                continue
            if values[2] >= values[0] or values[3] >= values[1] or min(values) <= 0:
                continue
            class_rows.append([round(value, 3) for value in values])
        generated.extend((species, values) for values in class_rows)

    rng.shuffle(generated)
    scoring_rows: list[dict[str, object]] = []
    actual_rows: list[dict[str, object]] = []
    for index, (species, values) in enumerate(generated, start=1):
        row_id = f"IRIS-SCORE-{index:05d}"
        scoring_rows.append({
            "row_id": row_id,
            **dict(zip(IRIS_FEATURES, values, strict=True)),
        })
        actual_rows.append({"row_id": row_id, "species": species})

    write_csv(OUTPUT / "iris-batch-scoring-10k.csv", scoring_rows)
    write_csv(OUTPUT / "iris-batch-scoring-10k-actuals.csv", actual_rows)


def sample_covariance(samples: list[list[float]], means: list[float]) -> list[list[float]]:
    divisor = len(samples) - 1
    return [
        [
            sum(
                (sample[row] - means[row]) * (sample[column] - means[column])
                for sample in samples
            )
            / divisor
            for column in range(len(means))
        ]
        for row in range(len(means))
    ]


def cholesky(matrix: list[list[float]]) -> list[list[float]]:
    size = len(matrix)
    result = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            remainder = matrix[row][column] - sum(
                result[row][index] * result[column][index]
                for index in range(column)
            )
            if row == column:
                result[row][column] = math.sqrt(max(remainder, 1e-12))
            else:
                result[row][column] = remainder / result[column][column]
    return result


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    write_dynamic_reactor()
    write_equipment_clustering()
    write_iris_batch_scoring()
    print(
        "Generated dynamic-reactor-timeseries.csv, equipment-operating-regimes.csv, "
        "iris-batch-scoring-10k.csv and iris-batch-scoring-10k-actuals.csv"
    )
