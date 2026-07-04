from app.core.security import Principal
from app.modules.business_cases.domain import ArtifactType
from app.modules.business_cases.repository import InMemoryBusinessCaseRepository
from app.modules.pipelines.domain import (
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTrigger,
    PipelineVersion,
    PipelineVersionStatus,
)
from app.modules.pipelines.materialization import ScoringReportMaterializer
from app.modules.pipelines.workflow import WorkflowDefinition
from app.modules.scoring_reports.schemas import ScoringReportRead
from app.modules.scoring_reports.service import ScoringReportService


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate({
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "training_1",
                "name": "Train churn model",
                "type": "training",
                "output_port_id": "model",
                "config": {"definition": {}},
            },
            {
                "step_id": "scoring_1",
                "name": "Test scoring",
                "type": "scoring",
                "inputs": [{
                    "port_id": "model",
                    "source": {"step_id": "training_1", "port_id": "model"},
                }],
                "output_port_id": "predictions",
                "config": {"definition": {"report_name": "Churn holdout quality"}},
            },
        ],
        "outputs": [{
            "output_id": "predictions",
            "source": {"step_id": "scoring_1", "port_id": "predictions"},
        }],
    })


def _version(workflow: WorkflowDefinition) -> PipelineVersion:
    return PipelineVersion(
        id="version-1",
        owner_id="owner-1",
        pipeline_id="pipeline-1",
        business_case_id="bc-1",
        version_number=1,
        status=PipelineVersionStatus.PUBLISHED,
        definition=workflow.model_dump(mode="json"),
        definition_hash="definition-hash",
        created_by="owner-1",
    )


def _run(run_id: str, *, dry_run: bool = False) -> PipelineRun:
    return PipelineRun(
        id=run_id,
        owner_id="owner-1",
        pipeline_id="pipeline-1",
        pipeline_version_id="version-1",
        business_case_id="bc-1",
        status=PipelineRunStatus.RUNNING,
        trigger_type=PipelineRunTrigger.MANUAL,
        is_dry_run=dry_run,
        created_by="owner-1",
    )


def _manifest(run_number: int) -> list[dict]:
    return [
        {
            "output_id": "model",
            "artifact_type": "model_version",
            "artifact_id": f"model-artifact-{run_number}",
            "pipeline_step_id": "training_1",
        },
        {
            "output_id": "predictions",
            "artifact_type": "prediction_dataset",
            "artifact_id": f"prediction-artifact-{run_number}",
            "dataset_id": f"prediction-dataset-{run_number}",
            "pipeline_step_id": "scoring_1",
            "output_stage": "final",
            "row_count": 100 + run_number,
            "evaluation": {
                "contract_version": "1.0",
                "kind": "model_performance",
                "status": "available",
                "problem_type": "binary_classification",
                "data_scope": {
                    "mode": "full",
                    "evaluated_row_count": 100 + run_number,
                    "excluded_row_count": 0,
                },
                "metrics": [{"id": "accuracy", "label": "Accuracy", "value": 0.9}],
                "warnings": [],
                "monitoring": {"baseline_eligible": True, "requires_actuals": True},
            },
        },
    ]


def test_full_runs_create_versioned_report_artifacts_with_lineage() -> None:
    artifacts = InMemoryBusinessCaseRepository()
    materializer = ScoringReportMaterializer(artifacts)
    workflow = _workflow()
    version = _version(workflow)

    for number in (1, 2):
        manifests, artifact_ids = materializer.materialize(
            run=_run(f"run-{number}"),
            version=version,
            workflow=workflow,
            output_manifest=_manifest(number),
        )
        assert manifests[0]["artifact_type"] == "report"
        assert manifests[0]["evaluation"]["data_scope"]["mode"] == "full"
        assert artifact_ids == [manifests[0]["artifact_id"]]

    reports = ScoringReportService(artifacts).list_reports(
        Principal("owner-1", "owner@example.com", "Owner")
    )

    assert len(reports) == 2
    assert len({report.logical_id for report in reports}) == 1
    assert [(report.pipeline_run_id, report.version_number) for report in reports] == [
        ("run-2", 2),
        ("run-1", 1),
    ]
    assert reports[0].prediction_dataset_id == "prediction-dataset-2"
    assert reports[0].model_artifact_id == "model-artifact-2"
    assert reports[0].name == "Churn holdout quality"
    assert reports[0].lineage["input_artifact_ids"] == [
        "model-artifact-2",
        "prediction-artifact-2",
    ]
    assert ScoringReportRead.model_validate(reports[0]).evaluated_row_count == 102
    assert len(artifacts.list_artifacts("owner-1", ArtifactType.REPORT)) == 2


def test_dry_run_never_registers_a_report_artifact() -> None:
    artifacts = InMemoryBusinessCaseRepository()
    workflow = _workflow()

    manifests, artifact_ids = ScoringReportMaterializer(artifacts).materialize(
        run=_run("dry-run-1", dry_run=True),
        version=_version(workflow),
        workflow=workflow,
        output_manifest=_manifest(1),
    )

    assert manifests == []
    assert artifact_ids == []
    assert artifacts.list_artifacts("owner-1", ArtifactType.REPORT) == []
