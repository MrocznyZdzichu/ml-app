"""Idempotently bootstrap the portable Estates Sell Prices demo prerequisites."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from examples.estates_bootstrap_manifest import (
    BUSINESS_CASE,
    DATASETS,
    PIPELINE,
    build_automl_definition,
)
from ml_app_client import AuthorizationError, MLAppClient


ROLE_RANK = {
    "report_viewer": 0,
    "reader": 1,
    "contributor": 2,
    "manager": 3,
    "owner": 4,
}


def _data_directory() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "data",
        Path.cwd() / "examples" / "data",
        Path.cwd() / "data",
    ]
    directory = next((item for item in candidates if item.is_dir()), None)
    if directory is None:
        raise FileNotFoundError("Could not locate the examples/data directory")
    return directory


def _attached_datasets(client: MLAppClient, business_case_id: str) -> dict[str, dict[str, Any]]:
    attachments = client.list_business_case_attachments(business_case_id)
    attached_ids = {str(item["data_asset_id"]) for item in attachments}
    return {
        str(dataset["name"]): dict(dataset)
        for dataset in client.list_datasets()
        if str(dataset.get("id")) in attached_ids
    }


def bootstrap(client: MLAppClient) -> dict[str, Any]:
    business_case, created = client.ensure_business_case(**BUSINESS_CASE)
    access_role = str(
        business_case.get("access_role") or ("owner" if created else "")
    )
    print(
        f"{'CREATED' if created else 'FOUND'} Business Case "
        f"{business_case['name']!r} (id={business_case['id']}, role={access_role})"
    )
    if ROLE_RANK.get(access_role, -1) < ROLE_RANK["contributor"]:
        raise AuthorizationError(
            f"Business Case {business_case['name']!r} is visible with role {access_role!r}, "
            "but contributor access is required to repair demo prerequisites."
        )

    attached = _attached_datasets(client, str(business_case["id"]))
    data_directory = _data_directory()
    datasets_by_key: dict[str, dict[str, Any]] = {}
    for spec in DATASETS:
        existing = attached.get(str(spec["name"]))
        if existing is not None:
            datasets_by_key[str(spec["key"])] = existing
            print(
                f"FOUND dataset {existing['name']!r} v{existing['version_number']} "
                f"(id={existing['id']})"
            )
            continue
        path = data_directory / str(spec["filename"])
        uploaded = client.upload_dataset(
            path,
            name=str(spec["name"]),
            description=str(spec["description"]),
            tags=["demo", "estates", "bootstrap"],
        )
        client.attach_dataset(
            str(business_case["id"]),
            uploaded.id,
            role=str(spec["role"]),
            context_note="Created by the portable Estates demo bootstrap manifest v1.0",
            primary_key_column=str(spec["primary_key_column"]),
            target_column=str(spec["target_column"]),
        )
        datasets_by_key[str(spec["key"])] = dict(uploaded.raw)
        print(
            f"CREATED dataset {uploaded.name!r} v{uploaded.version_number} "
            f"(id={uploaded.id}, rows={uploaded.row_count})"
        )

    pipelines = client.list_pipelines(str(business_case["id"]))
    matches = [item for item in pipelines if item.get("name") == PIPELINE["name"]]
    if len(matches) > 1:
        raise RuntimeError(f"Pipeline name {PIPELINE['name']!r} is ambiguous")
    if matches:
        pipeline = matches[0]
        if not pipeline.get("published_version_count") and pipeline.get("draft_version_number"):
            client.publish_pipeline_draft(str(pipeline["id"]))
            print(f"PUBLISHED existing pipeline draft {pipeline['name']!r}")
        else:
            print(
                f"FOUND pipeline {pipeline['name']!r} "
                f"(latest published v{pipeline.get('latest_published_version_number')})"
            )
    else:
        training = datasets_by_key["training"]
        pipeline = client.create_pipeline(
            business_case_id=str(business_case["id"]),
            definition=build_automl_definition(str(training["logical_id"])),
            **PIPELINE,
        )
        version = client.publish_pipeline_draft(str(pipeline["id"]))
        print(
            f"CREATED and PUBLISHED pipeline {pipeline['name']!r} "
            f"v{version['version_number']} (id={pipeline['id']})"
        )

    print("\nStatic demo prerequisites are ready.")
    print("Next: run the AutoFEML pipeline to create a model and fitted transform.")
    print("Then create batch-scoring and monitoring pipelines from those new artifacts.")
    return {
        "business_case": business_case,
        "datasets": datasets_by_key,
        "pipeline": pipeline,
        "created_business_case": created,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", help="Interactive login name when ML_APP_ACCESS_TOKEN is unset")
    args = parser.parse_args()
    client = MLAppClient.from_env()
    try:
        if not os.getenv("ML_APP_ACCESS_TOKEN", "").strip():
            login = args.login or input("Login: ")
            client.login(login, getpass.getpass("Password: "))
        bootstrap(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
