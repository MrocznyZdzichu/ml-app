from __future__ import annotations

from typing import Any

from app.modules.business_cases.domain import Artifact, ArtifactOrigin, ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository


class DatasetLineageResolver:
    """Resolves a bounded artifact DAG into user-facing dataset references."""

    def __init__(
        self,
        artifacts: BusinessCaseRepository | None = None,
        datasets: DatasetRepository | None = None,
    ) -> None:
        self.artifacts = artifacts or PostgresBusinessCaseRepository()
        self.datasets = datasets or PostgresDatasetRepository()

    def resolve(
        self,
        root: Artifact,
        *,
        max_depth: int = 12,
        max_nodes: int = 200,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        visited: set[str] = {root.id}
        stack: list[tuple[Artifact, int, str]] = [(root, 0, "")]
        while stack and len(visited) <= max_nodes:
            current, depth, inherited_role = stack.pop()
            if depth >= max_depth:
                continue
            lineage = dict(current.metadata.get("lineage") or {})
            bindings = self._bindings(lineage)
            for binding in bindings:
                role = self._role(str(binding.get("input_port_id") or ""), inherited_role)
                for artifact_id in binding.get("artifact_ids") or []:
                    artifact = self.artifacts.get_artifact(str(artifact_id))
                    if artifact is None or artifact.owner_id != root.owner_id:
                        continue
                    if artifact.type in {
                        ArtifactType.DATASET,
                        ArtifactType.DATA_VIEW,
                        ArtifactType.PREDICTION_DATASET,
                    }:
                        item = self._dataset_item(artifact, role, depth + 1)
                        if item and not any(
                            existing["artifact_id"] == artifact.id for existing in result
                        ):
                            result.append(item)
                    if artifact.id not in visited:
                        visited.add(artifact.id)
                        stack.append((artifact, depth + 1, role))
        return sorted(
            result,
            key=lambda item: (
                self._role_order(str(item["role"])),
                int(item["depth"]),
                str(item["name"]),
            ),
        )

    @staticmethod
    def _bindings(lineage: dict[str, Any]) -> list[dict[str, Any]]:
        bindings = lineage.get("input_lineage")
        if isinstance(bindings, list) and bindings:
            return [item for item in bindings if isinstance(item, dict)]
        return [{
            "input_port_id": "",
            "artifact_ids": list(lineage.get("input_artifact_ids") or []),
        }]

    def _dataset_item(
        self,
        artifact: Artifact,
        inherited_role: str,
        depth: int,
    ) -> dict[str, Any] | None:
        dataset = self.datasets.get(artifact.reference_id)
        if dataset is None or dataset.owner_id != artifact.owner_id:
            return None
        pipeline_output = dict(dataset.metadata.get("pipeline_output") or {})
        role = inherited_role or str(pipeline_output.get("role") or "")
        if depth > 1 and role not in {"test", "validation", "prediction"}:
            role = (
                "source"
                if artifact.origin in {
                    ArtifactOrigin.UPLOADED,
                    ArtifactOrigin.EXTERNAL_REGISTERED,
                }
                else "intermediate"
            )
        if not role:
            role = (
                "source"
                if artifact.origin in {
                    ArtifactOrigin.UPLOADED,
                    ArtifactOrigin.EXTERNAL_REGISTERED,
                }
                else "intermediate"
            )
        lineage = dict(dataset.metadata.get("lineage") or artifact.metadata.get("lineage") or {})
        return {
            "artifact_id": artifact.id,
            "artifact_type": artifact.type.value,
            "dataset_id": dataset.id,
            "logical_id": dataset.logical_id,
            "version_number": dataset.version_number,
            "name": dataset.name,
            "role": role,
            "stage": dataset.version_stage,
            "format": dataset.format,
            "row_count": dataset.row_count,
            "pipeline_step_id": str(lineage.get("pipeline_step_id") or ""),
            "pipeline_run_id": str(lineage.get("pipeline_run_id") or ""),
            "depth": depth,
        }

    @staticmethod
    def _role(port_id: str, inherited: str) -> str:
        return {
            "training": "training",
            "validation": "validation",
            "test": "test",
            "data": "test",
            "predictions": "prediction",
        }.get(port_id, inherited)

    @staticmethod
    def _role_order(role: str) -> int:
        return {
            "source": 0,
            "intermediate": 1,
            "training": 2,
            "validation": 3,
            "test": 4,
            "prediction": 5,
        }.get(role, 6)


class ArtifactDependencyResolver:
    """Returns direct, version-aware dependency edges for any registered artifact.

    The resolver intentionally works on the common Artifact registry instead of
    duplicating relationship rules in datasets, models and reports. New artifact
    types only need to persist standard lineage fields to appear here.
    """

    def __init__(self, artifacts: BusinessCaseRepository | None = None) -> None:
        self.artifacts = artifacts or PostgresBusinessCaseRepository()

    def resolve(
        self,
        *,
        owner_id: str,
        reference_id: str,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        artifacts = self.artifacts.list_artifacts(owner_id)
        roots = [
            artifact for artifact in artifacts
            if artifact.reference_id == reference_id
            and (artifact_type is None or artifact.type.value == artifact_type)
        ]
        # Pipelines, versions and runs are execution objects rather than
        # Artifact rows. Their outputs provide the graph anchor, preserving the
        # same endpoint and UI affordance for all current object types.
        if artifact_type in {"pipeline", "pipeline_version", "pipeline_run"}:
            field = {
                "pipeline": "pipeline_id",
                "pipeline_version": "pipeline_version_id",
                "pipeline_run": "pipeline_run_id",
            }[artifact_type]
            roots = [
                artifact for artifact in artifacts
                if str(dict(artifact.metadata.get("lineage") or {}).get(field) or "") == reference_id
            ]
        if not roots:
            return []
        root_ids = {artifact.id for artifact in roots}
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()

        for root in roots:
            lineage = dict(root.metadata.get("lineage") or {})
            for binding in DatasetLineageResolver._bindings(lineage):
                role = self._role(str(binding.get("input_port_id") or ""))
                for artifact_id in binding.get("artifact_ids") or []:
                    source = next((item for item in artifacts if item.id == str(artifact_id)), None)
                    if source:
                        self._append(edges, seen, "upstream", role, source, root)
            self._append_execution_edges(edges, seen, root, lineage)

        for candidate in artifacts:
            if candidate.id in root_ids:
                continue
            lineage = dict(candidate.metadata.get("lineage") or {})
            for binding in DatasetLineageResolver._bindings(lineage):
                role = self._role(str(binding.get("input_port_id") or ""))
                if root_ids.intersection(str(item) for item in binding.get("artifact_ids") or []):
                    for root in roots:
                        self._append(edges, seen, "downstream", role, root, candidate)
            if root.reference_id in set(str(item) for item in lineage.get("input_artifact_ids") or []):
                for root in roots:
                    self._append(edges, seen, "downstream", "input", root, candidate)
        return edges

    @staticmethod
    def _role(port_id: str) -> str:
        return {
            "training": "training input",
            "validation": "validation input",
            "test": "holdout test input",
            "data": "scoring or report input",
            "model": "model used for scoring",
            "predictions": "prediction set",
            "fitted_transform": "fitted feature transform",
        }.get(port_id, "input")

    @staticmethod
    def _append(
        edges: list[dict[str, Any]],
        seen: set[tuple[str, str, str, str]],
        direction: str,
        role: str,
        source: Artifact,
        target: Artifact,
    ) -> None:
        related = source if direction == "upstream" else target
        key = (direction, role, related.type.value, related.reference_id)
        if key in seen:
            return
        seen.add(key)
        lineage = dict(target.metadata.get("lineage") or {})
        edges.append({
            "direction": direction,
            "role": role,
            "artifact_id": related.id,
            "artifact_type": related.type.value,
            "reference_id": related.reference_id,
            "business_case_id": related.business_case_id or "",
            "pipeline_id": str(lineage.get("pipeline_id") or ""),
            "pipeline_version_id": str(lineage.get("pipeline_version_id") or ""),
            "pipeline_run_id": str(lineage.get("pipeline_run_id") or ""),
            "pipeline_step_id": str(lineage.get("pipeline_step_id") or ""),
        })

    def _append_execution_edges(
        self,
        edges: list[dict[str, Any]],
        seen: set[tuple[str, str, str, str]],
        root: Artifact,
        lineage: dict[str, Any],
    ) -> None:
        for kind, field, role in (
            ("pipeline", "pipeline_id", "used in pipeline"),
            ("pipeline_version", "pipeline_version_id", "concrete pipeline version"),
            ("pipeline_run", "pipeline_run_id", "generated by pipeline run"),
        ):
            reference_id = str(lineage.get(field) or "")
            if not reference_id:
                continue
            key = ("upstream", role, kind, reference_id)
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "direction": "upstream",
                "role": role,
                "artifact_id": "",
                "artifact_type": kind,
                "reference_id": reference_id,
                "business_case_id": root.business_case_id or "",
                "pipeline_id": str(lineage.get("pipeline_id") or ""),
                "pipeline_version_id": str(lineage.get("pipeline_version_id") or ""),
                "pipeline_run_id": str(lineage.get("pipeline_run_id") or ""),
                "pipeline_step_id": str(lineage.get("pipeline_step_id") or ""),
            })
