import { SlidersHorizontal } from "lucide-react";

import type { DataAsset, Pipeline } from "../api/client";

const pipelineIndexCache = new WeakMap<Pipeline[], Map<string, Pipeline>>();

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
  let pipelineById = pipelineIndexCache.get(pipelines);
  if (!pipelineById) {
    pipelineById = new Map(pipelines.map((pipeline) => [pipeline.id, pipeline]));
    pipelineIndexCache.set(pipelines, pipelineById);
  }
  return pipelineById.get(pipelineId)?.template === purpose;
}

export function ArtifactFilters({
  pipelines,
  purpose,
  pipelineId,
  onPurposeChange,
  onPipelineChange,
  uploadedOnly,
  onUploadedOnlyChange,
  role,
  roleOptions,
  onRoleChange
}: {
  pipelines: Pipeline[];
  purpose: string;
  pipelineId: string;
  onPurposeChange: (value: string) => void;
  onPipelineChange: (value: string) => void;
  uploadedOnly?: boolean;
  onUploadedOnlyChange?: (value: boolean) => void;
  role?: string;
  roleOptions?: Array<{ value: string; label: string }>;
  onRoleChange?: (value: string) => void;
}) {
  const purposes = [...new Set(pipelines.map((pipeline) => pipeline.template).filter(Boolean))].sort();
  const visiblePipelines = pipelines.filter((pipeline) => !purpose || pipeline.template === purpose);

  return (
    <div className={`artifact-filters${onRoleChange ? " artifact-filters-with-role" : ""}`} aria-label="Artifact filters">
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
      {onRoleChange && (
        <label>
          <span>Data role</span>
          <select
            aria-label="Filter by data role"
            value={role ?? ""}
            onChange={(event) => onRoleChange(event.target.value)}
          >
            <option value="">All roles</option>
            {(roleOptions ?? []).map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

function pipelinePurposeLabel(value: string) {
  if (value === "training") return "Training";
  if (value === "automl") return "AutoML";
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
