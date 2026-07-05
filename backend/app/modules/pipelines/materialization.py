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


class ScoringReportMaterializer:
    """Registers immutable scoring evaluations without copying row-level data."""

    def __init__(
        self,
        business_cases: BusinessCaseRepository | None = None,
    ) -> None:
        self.business_cases = business_cases or PostgresBusinessCaseRepository()

    def materialize(
        self,
        *,
        run: PipelineRun,
        version: PipelineVersion,
        workflow: WorkflowDefinition,
        output_manifest: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if run.is_dry_run:
            return [], []
        report_manifests: list[dict[str, Any]] = []
        report_artifact_ids: list[str] = []
        model_outputs = [
            item
            for item in output_manifest
            if item.get("artifact_type") == ArtifactType.MODEL_VERSION.value
        ]
        for prediction in output_manifest:
            if (
                prediction.get("artifact_type")
                not in {ArtifactType.PREDICTION_DATASET.value, "report_source"}
                or not isinstance(prediction.get("evaluation"), dict)
            ):
                continue
            step_id = str(prediction.get("pipeline_step_id") or "")
            output_id = str(prediction.get("output_id") or "predictions")
            reference_id = str(uuid5(
                NAMESPACE_URL,
                f"mlapp:scoring-report:{run.id}:{step_id}:{output_id}",
            ))
            existing = self.business_cases.find_artifact(
                run.owner_id,
                reference_id,
                run.business_case_id,
            )
            if existing is None:
                logical_report_id = str(uuid5(
                    NAMESPACE_URL,
                    (
                        f"mlapp:scoring-report-family:{run.owner_id}:"
                        f"{run.pipeline_id}:{step_id}"
                    ),
                ))
                prediction_artifact_id = str(
                    prediction.get("prediction_artifact_id")
                    or prediction.get("artifact_id")
                    or ""
                )
                matching_model = self._model_for_scoring_step(
                    workflow,
                    step_id,
                    model_outputs,
                )
                model_artifact_id = str(
                    prediction.get("model_artifact_id")
                    or (matching_model or {}).get("artifact_id")
                    or ""
                )
                input_artifact_ids = [
                    artifact_id
                    for artifact_id in (model_artifact_id, prediction_artifact_id)
                    if artifact_id
                ]
                now = datetime.now(timezone.utc)
                lineage = {
                    "input_artifact_ids": input_artifact_ids,
                    "input_lineage": [
                        {
                            "input_port_id": "model",
                            "artifact_ids": [model_artifact_id] if model_artifact_id else [],
                        },
                        {
                            "input_port_id": "predictions",
                            "artifact_ids": [prediction_artifact_id]
                            if prediction_artifact_id else [],
                        },
                    ],
                    "pipeline_id": run.pipeline_id,
                    "pipeline_version_id": version.id,
                    "pipeline_definition_hash": version.definition_hash,
                    "pipeline_run_id": run.id,
                    "pipeline_step_id": step_id,
                    "created_at": now.isoformat(),
                    "row_count": int(prediction.get("row_count") or 0),
                    "created_by": run.created_by,
                }
                scoring_step = next(
                    (step for step in workflow.steps if step.step_id == step_id),
                    None,
                )
                step_name = scoring_step.name if scoring_step is not None else "Scoring"
                report_name = str(
                    (
                        (scoring_step.config.get("definition") or {}).get("report_name")
                        if scoring_step is not None else ""
                    )
                    or f"{step_name} report"
                )
                existing = Artifact(
                    id=str(uuid4()),
                    owner_id=run.owner_id,
                    type=ArtifactType.REPORT,
                    reference_id=reference_id,
                    origin=ArtifactOrigin.PLATFORM_GENERATED,
                    business_case_id=run.business_case_id,
                    metadata={
                        "report_name": report_name,
                        "logical_report_id": logical_report_id,
                        "evaluation": dict(prediction["evaluation"]),
                        "prediction_dataset_id": prediction.get("dataset_id", ""),
                        "prediction_artifact_id": prediction_artifact_id,
                        "model_artifact_id": model_artifact_id,
                        "lineage": lineage,
                    },
                    created_by=run.created_by,
                    created_at=now,
                )
                self.business_cases.add_artifact(existing)
            report_artifact_ids.append(existing.id)
            report_manifests.append({
                "output_id": f"{output_id}_scoring_report",
                "artifact_type": ArtifactType.REPORT.value,
                "materialization": "artifact",
                "artifact_id": existing.id,
                "reference_id": existing.reference_id,
                "pipeline_step_id": step_id,
                "output_stage": prediction.get("output_stage", "final"),
                "row_count": int(prediction.get("row_count") or 0),
                "data_scope": "full",
                "is_dry_run": False,
                "evaluation": dict(prediction["evaluation"]),
            })
        return report_manifests, report_artifact_ids

    @staticmethod
    def _model_for_scoring_step(
        workflow: WorkflowDefinition,
        scoring_step_id: str,
        model_outputs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        scoring_step = next(
            (step for step in workflow.steps if step.step_id == scoring_step_id),
            None,
        )
        source_step_ids = {
            port.source.step_id
            for port in (scoring_step.inputs if scoring_step is not None else [])
        }
        return next(
            (
                model
                for model in reversed(model_outputs)
                if str(model.get("pipeline_step_id") or "") in source_step_ids
            ),
            model_outputs[-1] if model_outputs else None,
        )


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
        input_artifact_ids: list[str] | None = None,
        input_lineage: list[dict[str, Any]] | None = None,
        step_type: str = "data_engineering",
        output_stage: str = "final",
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if step_id is None or input_dataset_ids is None:
            step = data_engineering_step(workflow)
            step_id = step.step_id
            de_definition = dict(step.config["definition"])
            input_dataset_ids = [
                str(item["dataset_id"]) for item in de_definition.get("inputs", [])
            ]
        ensured_input_artifact_ids = self._ensure_input_artifacts(
            owner_id=run.owner_id,
            business_case_id=run.business_case_id,
            dataset_ids=input_dataset_ids,
            created_by=run.created_by,
        )
        input_artifact_ids = list(dict.fromkeys([
            *(input_artifact_ids or []),
            *ensured_input_artifact_ids,
        ]))
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
                    input_lineage=input_lineage or [],
                )
                item.update({
                    "artifact_id": artifact.id,
                    "location_uri": artifact.metadata["location_uri"],
                })
                artifact_ids.append(artifact.id)
                materialized_manifest.append(item)
                continue
            if item.get("artifact_type") in {
                ArtifactType.MODEL_VERSION.value,
                ArtifactType.METRICS.value,
            }:
                if item.get("materialization") != "artifact":
                    materialized_manifest.append(item)
                    continue
                artifact = self._materialize_file_artifact(
                    run=run,
                    version=version,
                    step_id=step_id,
                    item=item,
                    input_artifact_ids=input_artifact_ids,
                    input_lineage=input_lineage or [],
                )
                item.update({
                    "artifact_id": artifact.id,
                    "reference_id": artifact.reference_id,
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
                input_lineage=input_lineage or [],
                step_type=step_type,
                output_stage=output_stage,
            )
            item.update(
                {
                    "artifact_type": artifact.type.value,
                    "dataset_id": dataset.id,
                    "logical_id": dataset.logical_id,
                    "version_number": dataset.version_number,
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
        input_lineage: list[dict[str, Any]],
        step_type: str,
        output_stage: str,
    ) -> tuple[DataAsset, Artifact]:
        output_id = str(item["output_id"])
        dataset_id = str(uuid5(
            NAMESPACE_URL,
            f"mlapp:pipeline-output:{run.id}:{step_id}:{output_id}",
        ))
        logical_id = str(uuid5(
            NAMESPACE_URL,
            f"mlapp:pipeline-dataset-series:{run.pipeline_id}:{step_id}:{output_id}",
        ))
        existing_dataset = self.datasets.get(dataset_id)
        now = datetime.now(timezone.utc)
        lineage = {
            "input_artifact_ids": input_artifact_ids,
            "input_lineage": input_lineage,
            "pipeline_id": run.pipeline_id,
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
                logical_id=logical_id,
                version_number=0,
                version_stage=output_stage,
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
                    "split_evaluation": dict(item.get("split_evaluation") or {}),
                    "metrics": dict(item.get("metrics") or {}),
                    "score_contract": dict(item.get("score_contract") or {}),
                    "model_artifact_id": str(item.get("model_artifact_id") or ""),
                    "pipeline_output": {
                        "pipeline_id": run.pipeline_id,
                        "pipeline_step_id": step_id,
                        "output_id": output_id,
                        "stage": output_stage,
                        "role": str(item.get("business_case_role") or ""),
                    },
                },
                created_at=now,
                updated_at=now,
            )
            self.datasets.add_version(dataset)
        else:
            dataset = existing_dataset

        existing_artifact = self.business_cases.find_artifact(
            run.owner_id,
            dataset.id,
            run.business_case_id,
        )
        if existing_artifact is not None:
            return dataset, existing_artifact

        artifact_type = (
            ArtifactType.PREDICTION_DATASET
            if item.get("artifact_type") == ArtifactType.PREDICTION_DATASET.value
            else ArtifactType.DATASET
        )
        artifact = Artifact(
            id=str(uuid4()),
            owner_id=run.owner_id,
            type=artifact_type,
            reference_id=dataset.id,
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=run.business_case_id,
            metadata={"lineage": lineage},
            created_by=run.created_by,
            created_at=now,
        )
        self.business_cases.add_artifact(artifact)
        existing_attachment = next(
            (
                attachment
                for attachment in self.business_cases.list_data_attachments(run.business_case_id)
                if (
                    (attached := self.datasets.get(attachment.data_asset_id)) is not None
                    and attached.logical_id == dataset.logical_id
                )
            ),
            None,
        )
        if existing_attachment is None:
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
        else:
            existing_attachment.artifact_id = artifact.id
            existing_attachment.data_asset_id = dataset.id
            existing_attachment.context_note = f"Latest version generated by pipeline run {run.id}"
            self.business_cases.update_data_attachment(existing_attachment)
        return dataset, artifact

    def _materialize_file_artifact(
        self,
        *,
        run: PipelineRun,
        version: PipelineVersion,
        step_id: str,
        item: dict[str, Any],
        input_artifact_ids: list[str],
        input_lineage: list[dict[str, Any]],
    ) -> Artifact:
        artifact_type = ArtifactType(str(item["artifact_type"]))
        reference_id = str(uuid5(
            NAMESPACE_URL,
            f"mlapp:{artifact_type.value}:{run.id}:{step_id}:{item['output_id']}",
        ))
        existing = self.business_cases.find_artifact(
            run.owner_id,
            reference_id,
            run.business_case_id,
        )
        if existing is not None:
            return existing
        source_path = self._path_from_uri(str(item["location_uri"]))
        target_directory = (
            self.repository_root
            / "users"
            / run.owner_id
            / f"{artifact_type.value.replace('_', '-')}s"
            / reference_id
        ).resolve()
        self._assert_in_repository(target_directory)
        target_directory.mkdir(parents=True, exist_ok=True)
        target_path = target_directory / source_path.name
        os.replace(source_path, target_path)
        now = datetime.now(timezone.utc)
        lineage = {
            "input_artifact_ids": input_artifact_ids,
            "input_lineage": input_lineage,
            "pipeline_version_id": version.id,
            "pipeline_definition_hash": version.definition_hash,
            "pipeline_run_id": run.id,
            "pipeline_step_id": step_id,
            "created_at": now.isoformat(),
            "created_by": run.created_by,
        }
        logical_model_id = (
            str(uuid5(
                NAMESPACE_URL,
                f"mlapp:model-family:{run.owner_id}:{run.pipeline_id}:{step_id}:{item['output_id']}",
            ))
            if artifact_type == ArtifactType.MODEL_VERSION
            else ""
        )
        artifact = Artifact(
            id=str(uuid4()),
            owner_id=run.owner_id,
            type=artifact_type,
            reference_id=reference_id,
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=run.business_case_id,
            metadata={
                "location_uri": f"file://{target_path.as_posix()}",
                "model_name": item.get("model_name", ""),
                "algorithm": item.get("algorithm", ""),
                "problem_type": item.get("problem_type", ""),
                "feature_columns": list(item.get("feature_columns") or []),
                "target_column": item.get("target_column", ""),
                "model_hash": item.get("model_hash", ""),
                "logical_model_id": logical_model_id,
                "metrics": dict(item.get("metrics") or {}),
                "training_config": dict(item.get("training_config") or {}),
                "model_parameters": dict(item.get("model_parameters") or {}),
                "lineage": lineage,
            },
            created_by=run.created_by,
            created_at=now,
        )
        self.business_cases.add_artifact(artifact)
        return artifact

    def _materialize_feature_transform(
        self,
        *,
        run: PipelineRun,
        version: PipelineVersion,
        step_id: str,
        item: dict[str, Any],
        input_artifact_ids: list[str],
        input_lineage: list[dict[str, Any]],
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
            "input_lineage": input_lineage,
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
