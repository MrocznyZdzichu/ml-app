"""Generate the optional synthetic training file used by the API notebook."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def build_training_file(new_rows: int = 20_000, seed: int = 20260717) -> Path:
    """Create a fixed-size 10k canonical + 20k realistic synthetic CSV."""
    source = Path(__file__).resolve().parents[1] / "data" / "regression-example.csv"
    original = pd.read_csv(source)
    rng = np.random.default_rng(seed)
    synthetic = original.sample(new_rows, replace=True, random_state=seed).reset_index(drop=True)

    numeric = [
        "floor_area_sqm", "rooms", "building_age_years", "distance_to_center_km",
        "distance_to_transit_m", "district_score", "school_rating", "days_on_market",
        "sale_price_pln",
    ]
    synthetic[numeric] = synthetic[numeric].apply(pd.to_numeric)
    area_factor = rng.lognormal(0, 0.08, new_rows)
    old_area = synthetic["floor_area_sqm"].to_numpy(float)
    old_center = synthetic["distance_to_center_km"].to_numpy(float)
    old_district = synthetic["district_score"].to_numpy(float)
    synthetic["floor_area_sqm"] = np.round(np.clip(old_area * area_factor, 18, 450), 1)
    synthetic["rooms"] = np.clip(np.rint(synthetic["floor_area_sqm"] / rng.uniform(22, 34, new_rows)), 1, 12).astype(int)
    synthetic["building_age_years"] = np.clip(synthetic["building_age_years"] + rng.integers(0, 3, new_rows), 0, 180).astype(int)
    synthetic["distance_to_center_km"] = np.round(np.clip(old_center + rng.normal(0, 0.8, new_rows), 0.1, 60), 2)
    synthetic["distance_to_transit_m"] = np.clip(np.rint(synthetic["distance_to_transit_m"] + rng.normal(0, 90, new_rows)), 20, 5000).astype(int)
    synthetic["district_score"] = np.clip(np.rint(old_district + rng.normal(0, 3, new_rows)), 1, 100).astype(int)
    synthetic["school_rating"] = np.clip(np.rint(synthetic["school_rating"] + rng.normal(0, 0.6, new_rows)), 1, 10).astype(int)
    synthetic["days_on_market"] = np.clip(np.rint(synthetic["days_on_market"] * rng.lognormal(0, 0.12, new_rows)), 1, 365).astype(int)
    price_factor = (
        area_factor ** 0.82
        * np.exp(0.006 * (synthetic["district_score"].to_numpy(float) - old_district))
        * np.exp(-0.010 * (synthetic["distance_to_center_km"].to_numpy(float) - old_center))
        * rng.lognormal(np.log(1.045), 0.05, new_rows)
    )
    synthetic["sale_price_pln"] = (np.clip(synthetic["sale_price_pln"] * price_factor, 90_000, 15_000_000) / 1000).round().astype(int) * 1000
    synthetic["snapshot_month"] = rng.choice(["2027-01", "2027-02", "2027-03", "2027-04"], new_rows)
    synthetic["property_id"] = [f"API-RETRAIN-{seed}-{index:06d}" for index in range(1, new_rows + 1)]

    output = Path(tempfile.gettempdir()) / "sale-prices-api-retraining.csv"
    pd.concat([original, synthetic[original.columns]], ignore_index=True).to_csv(output, index=False)
    return output
