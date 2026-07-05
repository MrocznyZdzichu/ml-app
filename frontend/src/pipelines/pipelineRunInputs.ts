import type { DataAsset } from "../api/client";
import type { WorkflowDefinition } from "./workflowContract";
import {
  normalizeDatasetVersionPolicy,
  type DatasetVersionPolicy
} from "./dataContractOptions";

export type PipelineRunInput = {
  key: string;
  name: string;
  datasetId: string;
  logicalId: string;
  policy: DatasetVersionPolicy;
};

export function resolvePipelineRunInputs(
  definition: WorkflowDefinition,
  datasets: DataAsset[]
): PipelineRunInput[] {
  return definition.steps.flatMap((step) => {
    const nested = recordValue(recordValue(step.config).definition);
    const inputs = Array.isArray(nested.inputs) ? nested.inputs : [];
    return inputs.flatMap((value) => {
      const input = recordValue(value);
      const policy = normalizeDatasetVersionPolicy(input.version_policy);
      const datasetId = stringValue(input.dataset_id);
      if (!datasetId && policy !== "select_at_run_any") return [];
      const inputId = stringValue(input.input_id);
      const dataset = datasets.find(
        (item) => item.logical_id === datasetId || item.id === datasetId
      );
      return [{
        key: `${step.step_id}:${inputId}`,
        name: policy === "select_at_run_any"
          ? `${inputId.replaceAll("_", " ") || "Dataset"} input`
          : dataset?.name ?? (inputId || "Dataset input"),
        datasetId,
        logicalId: dataset?.logical_id ?? datasetId,
        policy
      }];
    });
  });
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}
