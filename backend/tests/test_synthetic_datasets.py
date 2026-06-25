import csv
import math
import statistics
from pathlib import Path

from examples import generate_synthetic_datasets as generator


def test_synthetic_dataset_generator_is_reproducible_and_preserves_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(generator, "OUTPUT", tmp_path)
    generator.write_dynamic_reactor()
    generator.write_equipment_clustering()
    first = {path.name: path.read_bytes() for path in tmp_path.glob("*.csv")}

    generator.write_dynamic_reactor()
    generator.write_equipment_clustering()
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


def correlation(left: list[float], right: list[float]) -> float:
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator
