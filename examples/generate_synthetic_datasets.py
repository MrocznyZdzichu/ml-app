"""Regenerate the checked-in synthetic ML examples with deterministic seeds."""

from __future__ import annotations

import csv
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


OUTPUT = Path(__file__).resolve().parent / "data"
IRIS_SOURCE = Path(__file__).resolve().parent / "data" / "iris.csv"
GENERAL_SOURCE = Path(__file__).resolve().parent / "data" / "general-example.csv"
REGRESSION_SOURCE = Path(__file__).resolve().parent / "data" / "regression-example.csv"
SEED = 20260624
IRIS_FEATURES = ("sepal_length", "sepal_width", "petal_length", "petal_width")
IRIS_THREE_CLASS_SCORING_ROWS = 200_000
ESTATES_SCORING_ROWS = 100_000


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


def write_iris_three_class_scoring_large(row_count: int = IRIS_THREE_CLASS_SCORING_ROWS) -> None:
    """Generate a realistic large three-class Iris scoring cohort and delayed actuals.

    The input and actuals are written separately as Parquet because this is a
    performance-test scenario. Class-specific multivariate sampling preserves
    the empirical covariance structure of the reference Iris data. Four scoring
    waves introduce a small covariate shift without exposing a time feature to
    the model, and the class allocation intentionally differs from the balanced
    reference population to make prevalence drift visible in monitoring.
    """
    if row_count < 3 or row_count % 4:
        raise ValueError("row_count must be at least 3 and divisible by four")

    rng = random.Random(SEED + 4)
    reference = iris_reference_by_species()
    species_order = ("setosa", "versicolor", "virginica")
    # 30% / 36% / 34%: plausible field prevalence, distinct from the reference
    # set's equal class count. The final class absorbs rounding.
    counts = {
        "setosa": round(row_count * 0.30),
        "versicolor": round(row_count * 0.36),
    }
    counts["virginica"] = row_count - counts["setosa"] - counts["versicolor"]
    distributions = {
        species: iris_distribution(reference[species])
        for species in species_order
    }

    generated: list[tuple[str, list[float]]] = []
    for species in species_order:
        distribution = distributions[species]
        for sequence in range(counts[species]):
            wave = sequence % 4
            values = correlated_iris_measurement(rng, distribution, wave)
            generated.append((species, values))
    rng.shuffle(generated)

    scoring_path = OUTPUT / "iris-3class-batch-scoring-200k.parquet"
    actuals_path = OUTPUT / "iris-3class-batch-scoring-200k-actuals.parquet"
    scoring_csv = scoring_path.with_suffix(".staging.csv")
    actuals_csv = actuals_path.with_suffix(".staging.csv")
    try:
        with scoring_csv.open("w", newline="", encoding="utf-8") as scoring_handle, actuals_csv.open(
            "w", newline="", encoding="utf-8"
        ) as actuals_handle:
            scoring_writer = csv.DictWriter(scoring_handle, fieldnames=("row_id", *IRIS_FEATURES), lineterminator="\n")
            actuals_writer = csv.DictWriter(actuals_handle, fieldnames=("row_id", "species", "actual_observed_at"), lineterminator="\n")
            scoring_writer.writeheader()
            actuals_writer.writeheader()
            observation_start = datetime(2026, 10, 1, tzinfo=UTC)
            for index, (species, values) in enumerate(generated, start=1):
                row_id = f"IRIS-3C-SCORE-{index:06d}"
                scoring_writer.writerow({"row_id": row_id, **dict(zip(IRIS_FEATURES, values, strict=True))})
                # Target availability occurs 28–49 days after scoring in four waves.
                observed_at = observation_start + timedelta(days=28 + ((index - 1) % 4) * 7)
                actuals_writer.writerow({
                    "row_id": row_id,
                    "species": species,
                    "actual_observed_at": observed_at.date().isoformat(),
                })
        csv_to_parquet(scoring_csv, scoring_path)
        csv_to_parquet(actuals_csv, actuals_path)
    finally:
        scoring_csv.unlink(missing_ok=True)
        actuals_csv.unlink(missing_ok=True)


def iris_reference_by_species() -> dict[str, list[list[float]]]:
    result = {species: [] for species in ("setosa", "versicolor", "virginica")}
    with IRIS_SOURCE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            result[str(row["species"])].append([float(row[name]) for name in IRIS_FEATURES])
    return result


def iris_distribution(samples: list[list[float]]) -> dict[str, list[list[float]] | list[float]]:
    means = [sum(row[index] for row in samples) / len(samples) for index in range(len(IRIS_FEATURES))]
    ranges = [
        (min(row[index] for row in samples), max(row[index] for row in samples))
        for index in range(len(IRIS_FEATURES))
    ]
    return {"means": means, "factor": cholesky(sample_covariance(samples, means)), "ranges": ranges}


def correlated_iris_measurement(
    rng: random.Random,
    distribution: dict[str, list[list[float]] | list[float]],
    wave: int,
) -> list[float]:
    means = distribution["means"]
    factor = distribution["factor"]
    ranges = distribution["ranges"]
    assert isinstance(means, list) and isinstance(factor, list) and isinstance(ranges, list)
    # Small shared seasonal/method drift, strongest for lengths, still bounded
    # to botanical ranges with a 20% margin.
    drift = (-0.035, -0.012, 0.018, 0.042)[wave]
    while True:
        standard = [rng.gauss(0, 1) for _ in IRIS_FEATURES]
        values = [
            float(means[row]) + sum(float(factor[row][column]) * standard[column] for column in range(row + 1))
            + drift * (1.0 if row in {0, 2} else 0.45)
            for row in range(len(IRIS_FEATURES))
        ]
        lower = [float(bounds[0]) - 0.20 * (float(bounds[1]) - float(bounds[0])) for bounds in ranges]
        upper = [float(bounds[1]) + 0.20 * (float(bounds[1]) - float(bounds[0])) for bounds in ranges]
        if (
            all(lower[index] <= value <= upper[index] for index, value in enumerate(values))
            and values[2] < values[0]
            and values[3] < values[1]
            and min(values) > 0
        ):
            return [round(value, 3) for value in values]


def csv_to_parquet(csv_path: Path, parquet_path: Path) -> None:
    import duckdb

    connection = duckdb.connect()
    try:
        escaped_csv = str(csv_path).replace("'", "''")
        escaped_parquet = str(parquet_path).replace("'", "''")
        connection.execute(
            f"COPY (SELECT * FROM read_csv_auto('{escaped_csv}', header=true)) "
            f"TO '{escaped_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    finally:
        connection.close()


def write_churn_batch_scoring() -> None:
    """Create an out-of-time churn scoring cohort and separately held actuals.

    The checked-in training population is used as an empirical, label-stratified
    population model. Numeric fields are perturbed and a small, documented
    operational drift is applied, while categorical combinations and the target
    relationships from the training scenario remain intact.
    """

    rng = random.Random(SEED + 3)
    with GENERAL_SOURCE.open(encoding="utf-8", newline="") as handle:
        training_rows = list(csv.DictReader(handle))

    by_outcome = {
        outcome: [row for row in training_rows if row["churned"] == outcome]
        for outcome in ("0", "1")
    }
    outcomes = ["1"] * 600 + ["0"] * 9_400
    rng.shuffle(outcomes)
    scoring_rows: list[dict[str, object]] = []
    actual_rows: list[dict[str, object]] = []

    for index, outcome in enumerate(outcomes, start=1):
        source = rng.choice(by_outcome[outcome])
        customer_id = f"CHURN-SCORE-{index:05d}"
        scoring_rows.append({
            "customer_id": customer_id,
            "snapshot_month": ("2026-07", "2026-08", "2026-09")[(index - 1) % 3],
            "region": source["region"],
            "acquisition_channel": source["acquisition_channel"],
            "customer_segment": source["customer_segment"],
            "plan_type": source["plan_type"],
            "age": round(clamp(float(source["age"]) + rng.gauss(0, 0.8), 18, 85)),
            "tenure_months": round(
                clamp(float(source["tenure_months"]) + rng.choice((-1, 0, 1, 2, 3)), 0, 120)
            ),
            "household_income": round(
                clamp(float(source["household_income"]) * math.exp(rng.gauss(0.012, 0.025)), 18_000, 300_000),
                2,
            ),
            "credit_score": round(
                clamp(float(source["credit_score"]) + rng.gauss(-3, 11), 300, 850)
            ),
            "monthly_fee": round(
                clamp(float(source["monthly_fee"]) * (1.025 + rng.gauss(0, 0.018)), 5, 500),
                2,
            ),
            "avg_monthly_usage_gb": round(
                clamp(float(source["avg_monthly_usage_gb"]) * (1.07 + rng.gauss(0, 0.035)), 0, 2_000),
                2,
            ),
            "app_sessions_30d": round(
                clamp(float(source["app_sessions_30d"]) * (1.03 + rng.gauss(0, 0.055)), 0, 1_000)
            ),
            "support_tickets_90d": round(
                clamp(float(source["support_tickets_90d"]) + rng.choice((-1, 0, 0, 0, 1)), 0, 30)
            ),
            "late_payments_12m": round(
                clamp(float(source["late_payments_12m"]) + rng.choice((0, 0, 0, 1)), 0, 12)
            ),
            "discount_pct": round(
                clamp(float(source["discount_pct"]) * (0.92 + rng.gauss(0, 0.025)), 0, 60),
                2,
            ),
            "data_overage_charges": round(
                clamp(float(source["data_overage_charges"]) * (1.08 + rng.gauss(0, 0.05)), 0, 250),
                2,
            ),
            "competitor_price_index": round(
                clamp(float(source["competitor_price_index"]) * (0.985 + rng.gauss(0, 0.012)), 0.5, 1.5),
                3,
            ),
            "nps_score": round(
                clamp(float(source["nps_score"]) + rng.gauss(-2.0, 3.5), -100, 100)
            ),
        })
        actual_rows.append({"customer_id": customer_id, "churned": outcome})

    write_csv(OUTPUT / "general-churn-batch-scoring-10k.csv", scoring_rows)
    write_csv(OUTPUT / "general-churn-batch-scoring-10k-actuals.csv", actual_rows)


def write_estates_batch_scoring(row_count: int = ESTATES_SCORING_ROWS) -> None:
    """Create an out-of-time property cohort and delayed sale-price actuals.

    The checked-in regression population supplies realistic joint combinations of
    location, property and listing attributes. Numeric attributes are perturbed,
    while the hidden sale price responds to those changes, regional market drift
    and transaction noise. Rows are streamed through staging CSV files so the
    default 100k cohort is never materialized as a second large Python object graph.
    """
    if row_count < 1:
        raise ValueError("row_count must be positive")

    rng = random.Random(SEED + 5)
    with REGRESSION_SOURCE.open(encoding="utf-8", newline="") as handle:
        training_rows = list(csv.DictReader(handle))

    scoring_path = OUTPUT / "estates-sale-prices-batch-scoring-100k.parquet"
    actuals_path = OUTPUT / "estates-sale-prices-batch-scoring-100k-actuals.parquet"
    scoring_csv = scoring_path.with_suffix(".staging.csv")
    actuals_csv = actuals_path.with_suffix(".staging.csv")
    feature_names = tuple(name for name in training_rows[0] if name != "sale_price_pln")
    scoring_months = ("2027-01", "2027-02", "2027-03", "2027-04")
    regional_market_factor = {
        "central": 1.075,
        "north": 1.058,
        "south": 1.049,
        "east": 1.041,
        "west": 1.064,
    }

    try:
        with scoring_csv.open("w", newline="", encoding="utf-8") as scoring_handle, actuals_csv.open(
            "w", newline="", encoding="utf-8"
        ) as actuals_handle:
            scoring_writer = csv.DictWriter(scoring_handle, fieldnames=feature_names, lineterminator="\n")
            actuals_writer = csv.DictWriter(
                actuals_handle,
                fieldnames=("property_id", "sale_price_pln", "actual_observed_at"),
                lineterminator="\n",
            )
            scoring_writer.writeheader()
            actuals_writer.writeheader()

            for index in range(1, row_count + 1):
                source = rng.choice(training_rows)
                wave = (index - 1) % len(scoring_months)
                property_id = f"EST-SCORE-{index:06d}"
                source_area = float(source["floor_area_sqm"])
                floor_area = round(clamp(source_area * math.exp(rng.gauss(0, 0.045)), 18, 650), 1)
                source_district = int(source["district_score"])
                district_score = round(clamp(source_district + rng.gauss(0.8, 2.2), 20, 100))
                source_center_distance = float(source["distance_to_center_km"])
                center_distance = round(
                    clamp(source_center_distance + rng.gauss(0, 0.32), 0.1, 45), 2
                )
                transit_distance = round(
                    clamp(float(source["distance_to_transit_m"]) + rng.gauss(-12, 55), 20, 5_000)
                )
                rooms = round(clamp(int(source["rooms"]) + rng.choice((0, 0, 0, 0, -1, 1)), 1, 12))
                school_rating = round(clamp(int(source["school_rating"]) + rng.choice((-1, 0, 0, 0, 1)), 1, 10))
                building_age = round(clamp(int(source["building_age_years"]) + 1, 0, 180))
                days_on_market = round(
                    clamp(float(source["days_on_market"]) * math.exp(rng.gauss(-0.035, 0.12)), 1, 730)
                )

                scoring_row = {
                    "property_id": property_id,
                    "snapshot_month": scoring_months[wave],
                    "region": source["region"],
                    "district_score": district_score,
                    "property_type": source["property_type"],
                    "floor_area_sqm": floor_area,
                    "rooms": rooms,
                    "building_age_years": building_age,
                    "floor_number": source["floor_number"],
                    "has_elevator": source["has_elevator"],
                    "distance_to_center_km": center_distance,
                    "distance_to_transit_m": transit_distance,
                    "school_rating": school_rating,
                    "energy_class": source["energy_class"],
                    "condition_level": source["condition_level"],
                    "heating_type": source["heating_type"],
                    "parking_type": source["parking_type"],
                    "listing_channel": source["listing_channel"],
                    "days_on_market": days_on_market,
                }
                scoring_writer.writerow(scoring_row)

                # The target remains hidden from scoring. It reflects the changed
                # property attributes plus moderate out-of-time market appreciation.
                price_factor = (
                    (floor_area / source_area) ** 0.82
                    * math.exp(0.006 * (district_score - source_district))
                    * math.exp(-0.010 * (center_distance - source_center_distance))
                    * math.exp(0.012 * (school_rating - int(source["school_rating"])))
                    * regional_market_factor[str(source["region"])]
                    * (1 + 0.006 * wave)
                    * math.exp(rng.gauss(0, 0.055))
                )
                sale_price = round(
                    clamp(float(source["sale_price_pln"]) * price_factor, 90_000, 15_000_000)
                    / 1_000
                ) * 1_000
                observed_at = datetime(2027, 3, 15, tzinfo=UTC) + timedelta(
                    days=wave * 31 + rng.randrange(0, 29)
                )
                actuals_writer.writerow({
                    "property_id": property_id,
                    "sale_price_pln": sale_price,
                    "actual_observed_at": observed_at.date().isoformat(),
                })

        csv_to_parquet(scoring_csv, scoring_path)
        csv_to_parquet(actuals_csv, actuals_path)
    finally:
        scoring_csv.unlink(missing_ok=True)
        actuals_csv.unlink(missing_ok=True)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


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
    write_iris_three_class_scoring_large()
    write_churn_batch_scoring()
    write_estates_batch_scoring()
    print(
        "Generated dynamic-reactor-timeseries.csv, equipment-operating-regimes.csv, "
        "Iris batch-scoring files, the 200k Iris three-class performance cohort, churn batch-scoring files, "
        "and the 100k estates regression scoring cohort"
    )
