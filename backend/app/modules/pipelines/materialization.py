from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.modules.business_cases.domain import (
    Artifact,
    ArtifactOrigin,
    ArtifactType,
    BusinessCaseDataAttachment,
    DataArtifactKind,
    DataRole,
)
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.pipelines.domain import PipelineRun, PipelineVersion
from app.modules.pipelines.workflow import WorkflowDefinition, data_engineering_step


class PipelineOutputMaterializer:
    def __init__(
        self,
        datasets: DatasetRepository | None = None,
        business_cases: BusinessCaseRepository | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self.datasets = datasets or PostgresDatasetRepository()
        self.business_cases = business_cases or PostgresBusinessCaseRepository()
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def materialize(
        self,
        *,
        run: PipelineRun,
        version: PipelineVersion,
        workflow: WorkflowDefinition,
        output_manifest: list[dict[str, Any]],
        step_id: str | None = None,
        input_dataset_ids: list[str] | None = None,
        step_type: str = "data_engineering",
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if step_id is None or input_dataset_ids is None:
            step = data_engineering_step(workflow)
            step_id = step.step_id
            de_definition = dict(step.config["definition"])
            input_dataset_ids = [
                str(item["dataset_id"]) for item in de_definition.get("inputs", [])
            ]
        input_artifact_ids = self._ensure_input_artifacts(
            owner_id=run.owner_id,
            business_case_id=run.business_case_id,
            dataset_ids=input_dataset_ids,
            created_by=run.created_by,
        )
        artifact_ids: list[str] = []
        materialized_manifest: list[dict[str, Any]] = []
        for raw_item in output_manifest:
            item = dict(raw_item)
            if item.get("artifact_type") == ArtifactType.FEATURE_TRANSFORM.value:
                if item.get("materialization") != "artifact":
                    materialized_manifest.append(item)
                    continue
                artifact = self._materialize_feature_transform(
                    run=run,
                    version=version,
                    step_id=step_id,
                    item=item,
                    input_artifact_ids=input_artifact_ids,
                )
                item.update({
                    "artifact_id": artifact.id,
                    "location_uri": artifact.metadata["location_uri"],
                })
                artifact_ids.append(artifact.id)
                materialized_manifest.append(item)
                continue
            if item.get("materialization") != "dataset":
                materialized_manifest.append(item)
                continue
            dataset, artifact = self._materialize_dataset(
                run=run,
                version=version,
                step_id=step_id,
                item=item,
                input_artifact_ids=input_artifact_ids,
                step_type=step_type,
            )
            item.update(
                {
                    "dataset_id": dataset.id,
                    "artifact_id": artifact.id,
                    "location_uri": dataset.location_uri,
                    "file_size_bytes": dataset.file_size_bytes,
                }
            )
            artifact_ids.append(artifact.id)
            materialized_manifest.append(item)
        return materialized_manifest, artifact_ids

    def _materialize_dataset(
        self,
        *,
        run: PipelineRun,
        version: PipelineVersion,
        step_id: str,
        item: dict[str, Any],
        input_artifact_ids: list[str],
        step_type: str,
    ) -> tuple[DataAsset, Artifact]:
        output_id = str(item["output_id"])
        dataset_id = str(uuid5(NAMESPACE_URL, f"mlapp:pipeline-output:{run.id}:{output_id}"))
        existing_dataset = self.datasets.get(dataset_id)
        now = datetime.now(timezone.utc)
        lineage = {
            "input_artifact_ids": input_artifact_ids,
            "pipeline_version_id": version.id,
            "pipeline_definition_hash": version.definition_hash,
            "pipeline_run_id": run.id,
            "pipeline_step_id": step_id,
            "created_at": now.isoformat(),
            "row_count": int(item["row_count"]),
            "output_schema": list(item.get("schema") or []),
            "created_by": run.created_by,
        }
        if existing_dataset is None:
            source_path = self._path_from_uri(str(item["location_uri"]))
            target_directory = self._safe_dataset_directory(run.owner_id, dataset_id)
            target_directory.mkdir(parents=True, exist_ok=True)
            target_path = target_directory / f"{self._safe_filename(output_id)}.parquet"
            os.replace(source_path, target_path)
            dataset = DataAsset(
                id=dataset_id,
                owner_id=run.owner_id,
                name=str(item.get("dataset_name") or output_id),
                source_type=SourceType.FILE,
                format="parquet",
                description=f"Output of pipeline run {run.id}",
                original_filename=target_path.name,
                location_uri=f"file://{target_path.as_posix()}",
                file_size_bytes=target_path.stat().st_size,
                row_count=int(item["row_count"]),
                has_header=True,
                uploaded_by=run.created_by,
                uploaded_at=now,
                status=DataAssetStatus.READY,
                tags=["pipeline-output", step_type.replace("_", "-")],
                metadata={
                    "source_schema": list(item.get("schema") or []),
                    "origin": "platform_generated",
                    "lineage": lineage,
                    "schema_hash": item.get("schema_hash", ""),
                    "feature_manifest": list(item.get("feature_manifest") or []),
                    "evaluation": dict(item.get("evaluation") or {}),
                },
                created_at=now,
                updated_at=now,
            )
            self.datasets.add(dataset)
        else:
            dataset = existing_dataset

        existing_artifact = self.business_cases.find_artifact(
            run.owner_id,
            dataset.id,
            run.business_case_id,
        )
        if existing_artifact is not None:
            return dataset, existing_artifact

        artifact = Artifact(
            id=str(uuid4()),
            owner_id=run.owner_id,
            type=ArtifactType.DATASET,
            reference_id=dataset.id,
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=run.business_case_id,
            metadata={"lineage": lineage},
            created_by=run.created_by,
            created_at=now,
        )
        self.business_cases.add_artifact(artifact)
        self.business_cases.add_data_attachment(
            BusinessCaseDataAttachment(
                id=str(uuid4()),
                owner_id=run.owner_id,
                business_case_id=run.business_case_id,
                artifact_id=artifact.id,
                data_asset_id=dataset.id,
                data_asset_kind=DataArtifactKind.DATASET,
                role=DataRole(str(item.get("business_case_role") or "source")),
                context_note=f"Generated by pipeline run {run.id}",
                created_by=run.created_by,
                created_at=now,
            )
        )
        return dataset, artifact

    def _materialize_feature_transform(
        self,
        *,
        run: PipelineRun,
        version: PipelineVersion,
        step_id: str,
        item: dict[str, Any],
        input_artifact_ids: list[str],
    ) -> Artifact:
        reference_id = str(uuid5(
            NAMESPACE_URL,
            f"mlapp:feature-transform:{run.id}:{item['output_id']}",
        ))
        existing = self.business_cases.find_artifact(
            run.owner_id,
            reference_id,
            run.business_case_id,
        )
        if existing is not None:
            return existing
        source_path = self._path_from_uri(str(item["location_uri"]))
        target_directory = self._safe_feature_transform_directory(run.owner_id, reference_id)
        target_directory.mkdir(parents=True, exist_ok=True)
        target_path = target_directory / "state.json"
        os.replace(source_path, target_path)
        lineage = {
            "input_artifact_ids": input_artifact_ids,
            "pipeline_version_id": version.id,
            "pipeline_definition_hash": version.definition_hash,
            "pipeline_run_id": run.id,
            "pipeline_step_id": step_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": run.created_by,
        }
        artifact = Artifact(
            id=str(uuid4()),
            owner_id=run.owner_id,
            type=ArtifactType.FEATURE_TRANSFORM,
            reference_id=reference_id,
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=run.business_case_id,
            metadata={
                "location_uri": f"file://{target_path.as_posix()}",
                "state_hash": item.get("state_hash", ""),
                "definition_hash": item.get("definition_hash", ""),
                "feature_manifest": list(item.get("feature_manifest") or []),
                "lineage": lineage,
            },
            created_by=run.created_by,
        )
        self.business_cases.add_artifact(artifact)
        return artifact

    def _ensure_input_artifacts(
        self,
        *,
        owner_id: str,
        business_case_id: str,
        dataset_ids: list[str],
        created_by: str,
    ) -> list[str]:
        artifact_ids: list[str] = []
        for dataset_id in dataset_ids:
            artifact = self.business_cases.find_artifact(owner_id, dataset_id, business_case_id)
            if artifact is None:
                dataset = self.datasets.get(dataset_id)
                if dataset is None or dataset.owner_id != owner_id:
                    raise ValueError(f"Lineage input dataset '{dataset_id}' was not found")
                artifact = Artifact(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    type=ArtifactType.DATASET,
                    reference_id=dataset_id,
                    origin=(
                        ArtifactOrigin.PLATFORM_GENERATED
                        if dataset.metadata.get("origin") == "platform_generated"
                        else ArtifactOrigin.UPLOADED
                    ),
                    business_case_id=business_case_id,
                    metadata={"registered_for_lineage": True},
                    created_by=created_by,
                )
                self.business_cases.add_artifact(artifact)
            artifact_ids.append(artifact.id)
        return artifact_ids

    def _path_from_uri(self, uri: str) -> Path:
        if not uri.startswith("file://"):
            raise ValueError("Pipeline output location is not a local file")
        path = Path(uri.removeprefix("file://")).resolve()
        self._assert_in_repository(path)
        if not path.is_file():
            raise ValueError("Pipeline output file was not found")
        return path

    def _safe_dataset_directory(self, owner_id: str, dataset_id: str) -> Path:
        directory = (self.repository_root / "users" / owner_id / dataset_id).resolve()
        self._assert_in_repository(directory)
        return directory

    def _safe_feature_transform_directory(self, owner_id: str, reference_id: str) -> Path:
        directory = (
            self.repository_root / "users" / owner_id / "feature-transforms" / reference_id
        ).resolve()
        self._assert_in_repository(directory)
        return directory

    def _assert_in_repository(self, path: Path) -> None:
        try:
            path.relative_to(self.repository_root)
        except ValueError as exc:
            raise ValueError("Pipeline materialization path is outside the repository root") from exc

    @staticmethod
    def _safe_filename(value: str) -> str:
        normalized = "".join(character if character.isalnum() or character in "-_." else "_" for character in value)
        return normalized or "result"
