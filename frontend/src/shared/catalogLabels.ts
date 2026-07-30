import type { BusinessCase, ModelArtifact, Pipeline } from "../api/client";
import { shortId } from "./formatters";

export function businessCaseName(
  businessCases: BusinessCase[],
  businessCaseId: string
) {
  return businessCases.find((item) => item.id === businessCaseId)?.name ?? "unknown BC";
}

export function pipelineName(pipelines: Pipeline[], pipelineId: string) {
  return pipelines.find((item) => item.id === pipelineId)?.name ?? "unknown pipeline";
}

export function inferenceBundleSummary(model: ModelArtifact | undefined) {
  if (!model) return "Select a model version to resolve its inference bundle.";
  if (!model.fitted_transform_artifact_id) {
    return "No matching fitted transform is registered; the backend will block this run.";
  }
  return `Model + fitted transform ${shortId(model.fitted_transform_artifact_id)} `
    + `from training run ${shortId(model.pipeline_run_id)} are pinned atomically.`;
}
