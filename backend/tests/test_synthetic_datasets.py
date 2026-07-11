import csv
import math
import statistics
from pathlib import Path

import duckdb

from examples import generate_synthetic_datasets as generator


def test_synthetic_dataset_generator_is_reproducible_and_preserves_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(generator, "OUTPUT", tmp_path)
    generator.write_dynamic_reactor()
    generator.write_equipment_clustering()
    generator.write_iris_batch_scoring()
    generator.write_churn_batch_scoring()
    first = {path.name: path.read_bytes() for path in tmp_path.glob("*.csv")}

    generator.write_dynamic_reactor()
    generator.write_equipment_clustering()
    generator.write_iris_batch_scoring()
    generator.write_churn_batch_scoring()
    second = {path.name: path.read_bytes() for path in tmp_path.glob("*.csv")}
    assert first == second

    with (tmp_path / "dynamic-reactor-timeseries.csv").open(encoding="utf-8", newline="") as handle:
        reactor = list(csv.DictReader(handle))
    assert len(reactor) == 14_400
    assert reactor[0]["timestamp"] < reactor[-1]["timestamp"]
    assert list(reactor[0]) == [
        "timestamp", "batch_id", "heater_command_pct", "feed_flow_l_min", "reactor_temperature_c"
    ]
    assert [name for name in reactor[0] if "temp" in name.lower()] == ["reactor_temperature_c"]
    assert len({row["batch_id"] for row in reactor}) == 25
    temperatures = [float(row["reactor_temperature_c"]) for row in reactor]
    heater = [float(row["heater_command_pct"]) for row in reactor]
    assert correlation(temperatures[:-1], temperatures[1:]) > 0.95
    temperature_changes = [right - left for left, right in zip(temperatures, temperatures[1:])]
    heater_changes = [right - left for left, right in zip(heater, heater[1:])]
    delayed_response = [
        correlation(heater_changes if lag == 0 else heater_changes[:-lag], temperature_changes[lag:])
        for lag in range(9)
    ]
    assert delayed_response.index(max(delayed_response)) == 4
    assert delayed_response[4] > 0.35

    with (tmp_path / "equipment-operating-regimes.csv").open(encoding="utf-8", newline="") as handle:
        equipment = list(csv.DictReader(handle))
    assert len(equipment) == 12_000
    assert "cluster" not in " ".join(equipment[0]).lower()
    assert len({row["machine_id"] for row in equipment}) == 240
    assert all(float(row["vibration_rms_mm_s"]) > 0 for row in equipment)

    with (tmp_path / "iris-batch-scoring-10k.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        iris_scoring = list(csv.DictReader(handle))
    with (tmp_path / "iris-batch-scoring-10k-actuals.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        iris_actuals = list(csv.DictReader(handle))

    assert len(iris_scoring) == len(iris_actuals) == 10_000
    assert list(iris_scoring[0]) == [
        "row_id", "sepal_length", "sepal_width", "petal_length", "petal_width"
    ]
    assert list(iris_actuals[0]) == ["row_id", "species"]
    assert len({row["row_id"] for row in iris_scoring}) == 10_000
    assert {row["row_id"] for row in iris_scoring} == {
        row["row_id"] for row in iris_actuals
    }
    species_by_id = {row["row_id"]: row["species"] for row in iris_actuals}
    assert set(species_by_id.values()) == {"versicolor", "virginica"}
    assert list(species_by_id.values()).count("versicolor") == 5_000
    assert list(species_by_id.values()).count("virginica") == 5_000
    assert "species" not in iris_scoring[0]

    reference = iris_reference_by_species()
    generated = {
        species: [
            [float(row[name]) for name in generator.IRIS_FEATURES]
            for row in iris_scoring
            if species_by_id[row["row_id"]] == species
        ]
        for species in ("versicolor", "virginica")
    }
    for species in generated:
        for column_index in range(len(generator.IRIS_FEATURES)):
            reference_mean = statistics.fmean(
                row[column_index] for row in reference[species]
            )
            generated_mean = statistics.fmean(
                row[column_index] for row in generated[species]
            )
            assert abs(generated_mean - reference_mean) < 0.08
        for left_index, right_index in ((0, 2), (2, 3)):
            reference_correlation = correlation(
                [row[left_index] for row in reference[species]],
                [row[right_index] for row in reference[species]],
            )
            generated_correlation = correlation(
                [row[left_index] for row in generated[species]],
                [row[right_index] for row in generated[species]],
            )
            assert abs(generated_correlation - reference_correlation) < 0.12

    generator.write_iris_three_class_scoring_large(row_count=4_000)
    large_scoring_path = tmp_path / "iris-3class-batch-scoring-200k.parquet"
    large_actuals_path = tmp_path / "iris-3class-batch-scoring-200k-actuals.parquet"
    connection = duckdb.connect()
    try:
        large_scoring = connection.execute(
            f"SELECT * FROM read_parquet('{str(large_scoring_path).replace(chr(39), chr(39) * 2)}') ORDER BY row_id"
        ).fetchall()
        large_actuals = connection.execute(
            f"SELECT * FROM read_parquet('{str(large_actuals_path).replace(chr(39), chr(39) * 2)}') ORDER BY row_id"
        ).fetchall()
    finally:
        connection.close()
    assert len(large_scoring) == len(large_actuals) == 4_000
    assert len({row[0] for row in large_scoring}) == 4_000
    assert {row[1] for row in large_actuals} == {"setosa", "versicolor", "virginica"}
    assert [row[1] for row in large_actuals].count("setosa") == 1_200
    assert [row[1] for row in large_actuals].count("versicolor") == 1_440
    assert [row[1] for row in large_actuals].count("virginica") == 1_360
    assert all(row[2] for row in large_actuals)
    assert all(len(row) == 5 for row in large_scoring)
    generator.write_iris_three_class_scoring_large(row_count=4_000)
    connection = duckdb.connect()
    try:
        regenerated = connection.execute(
            f"SELECT * FROM read_parquet('{str(large_scoring_path).replace(chr(39), chr(39) * 2)}') ORDER BY row_id"
        ).fetchall()
    finally:
        connection.close()
    assert large_scoring == regenerated

    with (tmp_path / "general-churn-batch-scoring-10k.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        churn_scoring = list(csv.DictReader(handle))
    with (tmp_path / "general-churn-batch-scoring-10k-actuals.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        churn_actuals = list(csv.DictReader(handle))
    with generator.GENERAL_SOURCE.open(encoding="utf-8", newline="") as handle:
        churn_training = list(csv.DictReader(handle))

    expected_features = [name for name in churn_training[0] if name != "churned"]
    assert len(churn_scoring) == len(churn_actuals) == 10_000
    assert list(churn_scoring[0]) == expected_features
    assert list(churn_actuals[0]) == ["customer_id", "churned"]
    assert "churned" not in churn_scoring[0]
    assert len({row["customer_id"] for row in churn_scoring}) == 10_000
    assert {row["customer_id"] for row in churn_scoring}.isdisjoint(
        row["customer_id"] for row in churn_training
    )
    assert {row["customer_id"] for row in churn_scoring} == {
        row["customer_id"] for row in churn_actuals
    }
    assert {row["snapshot_month"] for row in churn_scoring} == {
        "2026-07", "2026-08", "2026-09"
    }
    assert sum(row["churned"] == "1" for row in churn_actuals) == 600
    assert all(18 <= int(row["age"]) <= 85 for row in churn_scoring)
    assert all(300 <= int(row["credit_score"]) <= 850 for row in churn_scoring)


def iris_reference_by_species() -> dict[str, list[list[float]]]:
    result: dict[str, list[list[float]]] = {"versicolor": [], "virginica": []}
    with generator.IRIS_SOURCE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["species"] in result:
                result[row["species"]].append([
                    float(row[name]) for name in generator.IRIS_FEATURES
                ])
    return result


def correlation(left: list[float], right: list[float]) -> float:
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator
