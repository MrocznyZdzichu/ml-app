import { SlidersHorizontal } from "lucide-react";

import type { DataAsset, Pipeline } from "../api/client";

export function datasetPipelineId(dataset: DataAsset | undefined): string {
  if (!dataset) return "";
  const output = asRecord(dataset.metadata.pipeline_output);
  return typeof output.pipeline_id === "string" ? output.pipeline_id : "";
}

export function isUploadedDataset(dataset: DataAsset | undefined): boolean {
  return Boolean(dataset)
    && dataset?.source_type !== "view"
    && !datasetPipelineId(dataset)
    && dataset?.metadata.origin !== "platform_generated";
}

export function pipelineMatches(
  pipelineId: string,
  pipelines: Pipeline[],
  purpose: string,
  selectedPipelineId: string
): boolean {
  if (selectedPipelineId && pipelineId !== selectedPipelineId) return false;
  if (!purpose) return true;
  return pipelines.find((pipeline) => pipeline.id === pipelineId)?.template === purpose;
}

export function ArtifactFilters({
  pipelines,
  purpose,
  pipelineId,
  onPurposeChange,
  onPipelineChange,
  uploadedOnly,
  onUploadedOnlyChange
}: {
  pipelines: Pipeline[];
  purpose: string;
  pipelineId: string;
  onPurposeChange: (value: string) => void;
  onPipelineChange: (value: string) => void;
  uploadedOnly?: boolean;
  onUploadedOnlyChange?: (value: boolean) => void;
}) {
  const purposes = [...new Set(pipelines.map((pipeline) => pipeline.template).filter(Boolean))].sort();
  const visiblePipelines = pipelines.filter((pipeline) => !purpose || pipeline.template === purpose);

  return (
    <div className="artifact-filters" aria-label="Artifact filters">
      {onUploadedOnlyChange && (
        <label className="artifact-filter-toggle">
          <input
            checked={Boolean(uploadedOnly)}
            onChange={(event) => onUploadedOnlyChange(event.target.checked)}
            type="checkbox"
          />
          <span>Uploaded only</span>
        </label>
      )}
      <label>
        <span><SlidersHorizontal size={14} /> Pipeline template</span>
        <select
          aria-label="Filter by pipeline template"
          value={purpose}
          onChange={(event) => {
            onPurposeChange(event.target.value);
            onPipelineChange("");
          }}
          disabled={Boolean(uploadedOnly)}
        >
          <option value="">All templates</option>
          {purposes.map((value) => (
            <option key={value} value={value}>{pipelinePurposeLabel(value)}</option>
          ))}
        </select>
      </label>
      <label>
        <span>Pipeline</span>
        <select
          aria-label="Filter by pipeline"
          value={pipelineId}
          onChange={(event) => onPipelineChange(event.target.value)}
          disabled={Boolean(uploadedOnly)}
        >
          <option value="">All pipelines</option>
          {visiblePipelines.map((pipeline) => (
            <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>
          ))}
        </select>
      </label>
    </div>
  );
}

function pipelinePurposeLabel(value: string) {
  if (value === "training") return "Training";
  if (value === "batch_scoring") return "Batch scoring";
  if (value === "monitoring") return "Monitoring";
  if (value === "custom") return "Custom";
  return value.replaceAll("_", " ");
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}
