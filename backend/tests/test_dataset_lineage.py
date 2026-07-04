from app.modules.business_cases.domain import Artifact, ArtifactOrigin, ArtifactType
from app.modules.business_cases.lineage import DatasetLineageResolver
from app.modules.business_cases.repository import InMemoryBusinessCaseRepository
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.repository import InMemoryDatasetRepository


def _dataset(dataset_id: str, name: str, version: int) -> DataAsset:
    return DataAsset(
        id=dataset_id,
        owner_id="owner-1",
        name=name,
        source_type=SourceType.FILE,
        format="parquet",
        logical_id=f"logical-{name}",
        version_number=version,
        row_count=100,
        status=DataAssetStatus.READY,
    )


def test_dataset_lineage_resolves_named_versioned_datasets_and_port_roles() -> None:
    artifacts = InMemoryBusinessCaseRepository()
    datasets = InMemoryDatasetRepository()
    source = _dataset("source-dataset", "Raw customers", 1)
    training = _dataset("training-dataset", "Training features", 3)
    datasets.add(source)
    datasets.add(training)
    source_artifact = Artifact(
        id="source-artifact",
        owner_id="owner-1",
        type=ArtifactType.DATASET,
        reference_id=source.id,
        origin=ArtifactOrigin.UPLOADED,
    )
    training_artifact = Artifact(
        id="training-artifact",
        owner_id="owner-1",
        type=ArtifactType.DATASET,
        reference_id=training.id,
        origin=ArtifactOrigin.PLATFORM_GENERATED,
        metadata={"lineage": {
            "pipeline_step_id": "fe_1",
            "input_lineage": [{
                "input_port_id": "training",
                "artifact_ids": [source_artifact.id],
            }],
        }},
    )
    model_artifact = Artifact(
        id="model-artifact",
        owner_id="owner-1",
        type=ArtifactType.MODEL_VERSION,
        reference_id="model-reference",
        origin=ArtifactOrigin.PLATFORM_GENERATED,
        metadata={"lineage": {
            "pipeline_step_id": "training_1",
            "input_lineage": [{
                "input_port_id": "training",
                "artifact_ids": [training_artifact.id],
            }],
        }},
    )
    for artifact in (source_artifact, training_artifact, model_artifact):
        artifacts.add_artifact(artifact)

    resolved = DatasetLineageResolver(artifacts, datasets).resolve(model_artifact)

    assert [(item["name"], item["version_number"], item["role"]) for item in resolved] == [
        ("Raw customers", 1, "source"),
        ("Training features", 3, "training"),
    ]
