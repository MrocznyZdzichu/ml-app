from __future__ import annotations

from typing import Final
from urllib.parse import quote, unquote

from fastapi import HTTPException, status

from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.pipelines.repository import PipelineRepository, PostgresPipelineRepository
from app.modules.pipelines.run_preview import PipelineRunOutputReader


TEMPORARY_PIPELINE_OUTPUT_PREFIX: Final = "dry-run-output:"


def temporary_pipeline_output_id(run_id: str, output_id: str) -> str:
    return f"{TEMPORARY_PIPELINE_OUTPUT_PREFIX}{quote(run_id, safe='')}:{quote(output_id, safe='')}"


class TemporaryPipelineOutputResolver:
    """Resolves a dry-run Parquet as a read-only DataAsset without registering a dataset."""

    def __init__(
        self,
        repository: PipelineRepository | None = None,
        output_reader: PipelineRunOutputReader | None = None,
    ) -> None:
        self.repository = repository or PostgresPipelineRepository()
        self.output_reader = output_reader or PipelineRunOutputReader()

    @staticmethod
    def recognizes(asset_id: str) -> bool:
        return asset_id.startswith(TEMPORARY_PIPELINE_OUTPUT_PREFIX)

    def resolve(self, asset_id: str, owner_id: str) -> DataAsset:
        run_id, output_id = self._parse(asset_id)
        run = self.repository.get_run(run_id)
        if not run or run.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporary dry-run output not found")

        output, path = self.output_reader.resolve_output(run, output_id)
        created_at = run.finished_at or run.started_at or run.created_at
        return DataAsset(
            id=asset_id,
            owner_id=owner_id,
            name=f"Dry-run output · {output_id}",
            source_type=SourceType.FILE,
            format="parquet",
            description="Read-only temporary output produced by a pipeline dry-run.",
            original_filename=path.name,
            location_uri=str(output.get("location_uri") or path.as_uri()),
            file_size_bytes=path.stat().st_size,
            row_count=int(output.get("row_count") or 0),
            uploaded_by=run.created_by,
            uploaded_at=created_at,
            status=DataAssetStatus.READY,
            tags=["temporary", "dry-run"],
            metadata={
                "temporary": True,
                "origin": "pipeline_dry_run",
                "pipeline_id": run.pipeline_id,
                "pipeline_version_id": run.pipeline_version_id,
                "pipeline_run_id": run.id,
                "output_id": output_id,
                "scope": "full",
                "schema": output.get("schema") or [],
            },
            created_at=created_at,
            updated_at=created_at,
        )

    @staticmethod
    def _parse(asset_id: str) -> tuple[str, str]:
        encoded = asset_id.removeprefix(TEMPORARY_PIPELINE_OUTPUT_PREFIX)
        parts = encoded.split(":", 1)
        if len(parts) != 2 or not all(parts):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporary dry-run output not found")
        return unquote(parts[0]), unquote(parts[1])
