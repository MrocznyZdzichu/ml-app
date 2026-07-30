from app.modules.business_cases.domain import Artifact, BusinessCase, BusinessCaseDataAttachment
from app.modules.business_cases.domain import ArtifactType

class InMemoryBusinessCaseRepository:
    def __init__(self) -> None:
        self._business_cases: dict[str, BusinessCase] = {}
        self._artifacts: dict[str, Artifact] = {}
        self._data_attachments: dict[str, BusinessCaseDataAttachment] = {}

    def add_business_case(self, business_case: BusinessCase) -> BusinessCase:
        self._business_cases[business_case.id] = business_case
        return business_case

    def list_business_cases(self, owner_id: str) -> list[BusinessCase]:
        return [item for item in self._business_cases.values() if item.owner_id == owner_id]

    def list_all_business_cases(self) -> list[BusinessCase]:
        return list(self._business_cases.values())

    def list_business_cases_by_ids(self, business_case_ids: set[str]) -> list[BusinessCase]:
        return [
            item for item in self._business_cases.values()
            if item.id in business_case_ids
        ]

    def page_business_cases(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
    ) -> tuple[list[BusinessCase], int]:
        needle = search.strip().casefold()
        items = [
            item
            for item in self._business_cases.values()
            if (business_case_ids is None or item.id in business_case_ids)
            and (
                not needle
                or any(
                    needle in str(value or "").casefold()
                    for value in (
                        item.name,
                        item.description,
                        item.problem_type.value,
                        item.status.value,
                        item.primary_metric,
                        item.target_column,
                    )
                )
            )
        ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[offset : offset + limit], len(items)

    def page_business_case_catalog(
        self,
        *,
        limit: int,
        offset: int,
        search: str = "",
    ) -> tuple[list[BusinessCase], int]:
        needle = search.strip().casefold()
        items = [
            item
            for item in self._business_cases.values()
            if not needle or needle in item.name.casefold()
        ]
        items.sort(key=lambda item: (item.name.casefold(), item.id))
        return items[offset : offset + limit], len(items)

    def business_case_name_exists(self, name: str, *, exclude_id: str = "") -> bool:
        normalized = name.strip().casefold()
        return any(
            item.id != exclude_id and item.name.strip().casefold() == normalized
            for item in self._business_cases.values()
        )

    def get_business_case(self, business_case_id: str) -> BusinessCase | None:
        return self._business_cases.get(business_case_id)

    def update_business_case(self, business_case: BusinessCase) -> BusinessCase:
        self._business_cases[business_case.id] = business_case
        return business_case

    def add_artifact(self, artifact: Artifact) -> Artifact:
        self._artifacts[artifact.id] = artifact
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def get_artifacts(self, artifact_ids: set[str]) -> dict[str, Artifact]:
        return {
            artifact_id: self._artifacts[artifact_id]
            for artifact_id in artifact_ids
            if artifact_id in self._artifacts
        }

    def update_artifact(self, artifact: Artifact) -> Artifact:
        self._artifacts[artifact.id] = artifact
        return artifact

    def list_artifacts(self, owner_id: str, artifact_type: ArtifactType | None = None) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.owner_id == owner_id and (artifact_type is None or item.type == artifact_type)
        ]

    def list_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None, artifact_type: ArtifactType | None = None
    ) -> list[Artifact]:
        return [item for item in self._artifacts.values()
                if (business_case_ids is None or item.business_case_id in business_case_ids)
                and (artifact_type is None or item.type == artifact_type)]

    def list_model_version_artifacts(self, logical_model_id: str) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.MODEL_VERSION
            and str(item.metadata.get("logical_model_id") or "") == logical_model_id
        ]

    def list_model_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.MODEL_VERSION
            and (business_case_ids is None or item.business_case_id in business_case_ids)
        ]

    def page_serving_model_summaries(
        self,
        business_case_id: str,
        *,
        limit: int,
        offset: int,
        search: str = "",
        model_ids: set[str] | None = None,
    ) -> tuple[list[tuple[Artifact, int]], int]:
        all_models = sorted(
            self.list_model_summary_artifacts_for_business_cases({business_case_id}),
            key=lambda item: (item.created_at, item.id),
        )
        version_by_id: dict[str, int] = {}
        family_counts: dict[str, int] = {}
        for artifact in all_models:
            logical_id = str(
                artifact.metadata.get("logical_model_id") or artifact.id
            )
            family_counts[logical_id] = family_counts.get(logical_id, 0) + 1
            version_by_id[artifact.id] = family_counts[logical_id]
        needle = search.strip().casefold()
        filtered = [
            artifact
            for artifact in all_models
            if str(artifact.metadata.get("stage") or "") in {"staging", "production"}
            and (model_ids is None or artifact.id in model_ids)
            and (
                not needle
                or any(
                    needle in str(value or "").casefold()
                    for value in (
                        artifact.metadata.get("model_name"),
                        artifact.metadata.get("algorithm"),
                        artifact.id,
                    )
                )
            )
        ]
        filtered.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        page = filtered[offset : offset + limit]
        return [(item, version_by_id[item.id]) for item in page], len(filtered)

    def page_model_family_summaries(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        stage: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
    ) -> tuple[list[tuple[Artifact, int]], int]:
        families: dict[str, list[Artifact]] = {}
        for artifact in self.list_model_summary_artifacts_for_business_cases(
            business_case_ids
        ):
            logical_id = str(
                artifact.metadata.get("logical_model_id") or artifact.id
            )
            families.setdefault(logical_id, []).append(artifact)
        needle = search.strip().casefold()
        items: list[tuple[Artifact, int]] = []
        for versions in families.values():
            versions.sort(
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
            latest = versions[0]
            metadata = latest.metadata
            lineage = dict(metadata.get("lineage") or {})
            if stage and str(metadata.get("stage") or "developed") != stage:
                continue
            if pipeline_id and str(lineage.get("pipeline_id") or "") != pipeline_id:
                continue
            if needle and not any(
                needle in str(value or "").casefold()
                for value in (
                    metadata.get("model_name"),
                    metadata.get("algorithm"),
                    metadata.get("problem_type"),
                    metadata.get("logical_model_id"),
                )
            ):
                continue
            items.append((latest, len(versions)))
        items.sort(key=lambda item: (item[0].created_at, item[0].id), reverse=True)
        return items[offset : offset + limit], len(items)

    def list_feature_transform_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.FEATURE_TRANSFORM
            and (business_case_ids is None or item.business_case_id in business_case_ids)
        ]

    def list_feature_transform_summary_artifacts_for_run_ids(
        self, run_ids: set[str]
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.FEATURE_TRANSFORM
            and str((item.metadata.get("lineage") or {}).get("pipeline_run_id") or "")
            in run_ids
        ]

    def list_scoring_report_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.REPORT
            and (business_case_ids is None or item.business_case_id in business_case_ids)
        ]

    def page_scoring_report_family_summaries(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        problem_type: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        sort_by: str = "created",
        sort_direction: str = "desc",
    ) -> tuple[list[tuple[Artifact, int]], int]:
        families: dict[str, list[Artifact]] = {}
        for artifact in self.list_scoring_report_summary_artifacts_for_business_cases(
            business_case_ids
        ):
            logical_id = str(
                artifact.metadata.get("logical_report_id") or artifact.id
            )
            families.setdefault(logical_id, []).append(artifact)
        needle = search.strip().casefold()
        items: list[tuple[Artifact, int]] = []
        for versions in families.values():
            versions.sort(
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
            latest = versions[0]
            metadata = latest.metadata
            lineage = dict(metadata.get("lineage") or {})
            evaluation = dict(metadata.get("evaluation") or {})
            if problem_type and str(evaluation.get("problem_type") or "") != problem_type:
                continue
            if pipeline_id and str(lineage.get("pipeline_id") or "") != pipeline_id:
                continue
            if needle and not any(
                needle in str(value or "").casefold()
                for value in (
                    metadata.get("report_name"),
                    metadata.get("logical_report_id"),
                    evaluation.get("problem_type"),
                )
            ):
                continue
            items.append((latest, len(versions)))
        def sort_value(item: tuple[Artifact, int]):
            artifact = item[0]
            metadata = artifact.metadata
            lineage = dict(metadata.get("lineage") or {})
            evaluation = dict(metadata.get("evaluation") or {})
            scope = dict(evaluation.get("data_scope") or {})
            values = {
                "report": str(metadata.get("report_name") or ""),
                "business_case": artifact.business_case_id or "",
                "pipeline": str(lineage.get("pipeline_id") or ""),
                "problem": str(evaluation.get("problem_type") or ""),
                "scope": int(scope.get("evaluated_row_count") or 0),
                "created": artifact.created_at,
            }
            return values.get(sort_by, artifact.created_at)

        items.sort(key=sort_value, reverse=sort_direction != "asc")
        return items[offset : offset + limit], len(items)

    def list_scoring_report_family_summary_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.REPORT
            and (
                business_case_ids is None
                or item.business_case_id in business_case_ids
            )
            and str(item.metadata.get("logical_report_id") or item.id)
            == logical_report_id
        ]

    def list_scoring_report_family_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        return self.list_scoring_report_family_summary_artifacts(
            business_case_ids,
            logical_report_id,
        )

    def find_feature_transform_artifact(
        self,
        business_case_id: str,
        pipeline_run_id: str,
        pipeline_step_id: str,
    ) -> Artifact | None:
        return next((
            item for item in self._artifacts.values()
            if item.type == ArtifactType.FEATURE_TRANSFORM
            and item.business_case_id == business_case_id
            and str((item.metadata.get("lineage") or {}).get("pipeline_run_id") or "") == pipeline_run_id
            and str((item.metadata.get("lineage") or {}).get("pipeline_step_id") or "") == pipeline_step_id
        ), None)

    def find_artifact(self, owner_id: str, reference_id: str, business_case_id: str | None) -> Artifact | None:
        for artifact in self._artifacts.values():
            if (
                artifact.owner_id == owner_id
                and artifact.reference_id == reference_id
                and artifact.business_case_id == business_case_id
            ):
                return artifact
        return None

    def add_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        self._data_attachments[attachment.id] = attachment
        return attachment

    def get_data_attachment(self, attachment_id: str) -> BusinessCaseDataAttachment | None:
        return self._data_attachments.get(attachment_id)

    def update_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        self._data_attachments[attachment.id] = attachment
        return attachment

    def delete_data_attachment(self, attachment_id: str) -> None:
        self._data_attachments.pop(attachment_id, None)

    def list_data_attachments(self, business_case_id: str) -> list[BusinessCaseDataAttachment]:
        return [
            item
            for item in self._data_attachments.values()
            if item.business_case_id == business_case_id
        ]

    def page_data_attachments(
        self,
        business_case_id: str,
        *,
        limit: int,
        offset: int,
        search: str = "",
        role: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        deleted_only: bool = False,
    ) -> tuple[list[BusinessCaseDataAttachment], int]:
        needle = search.strip().casefold()
        items = [
            item
            for item in self.list_data_attachments(business_case_id)
            if (not role or item.role.value == role)
            and (not pipeline_id or item.data_asset_pipeline_id == pipeline_id)
            and (
                not pipeline_type
                or item.data_asset_pipeline_template == pipeline_type
            )
            and (
                not uploaded_only
                or (
                    item.data_asset_source_type != "view"
                    and not item.data_asset_pipeline_id
                )
            )
            and (
                (item.data_asset_status == "deleted")
                if deleted_only
                else item.data_asset_status != "deleted"
            )
            and (
                not needle
                or any(
                    needle in str(value or "").casefold()
                    for value in (
                        item.data_asset_name,
                        item.data_asset_id,
                        item.context_note,
                        item.role.value,
                    )
                )
            )
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[offset : offset + limit], len(items)
