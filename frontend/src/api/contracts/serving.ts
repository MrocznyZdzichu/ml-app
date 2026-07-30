import type { ModelEvaluationSnapshot } from "./modelEvaluation";

export type DeploymentRole = "champion" | "challenger" | "shadow" | "fallback";

export type Deployment = {
  id: string;
  owner_id: string;
  business_case_id: string;
  name: string;
  slug: string;
  status: "requested" | "building" | "running" | "degraded" | "failed" | "stopped" | "archived";
  active_revision_id: string;
  endpoint_url: string | null;
  retention_days: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  active_revision: DeploymentRevision | null;
};

export type DeploymentRevision = {
  id: string;
  deployment_id: string;
  version_number: number;
  assignments: Array<{ model_id: string; role: DeploymentRole }>;
  created_by: string;
  reason: string;
  created_at: string;
};

export type ModelServingUsage = {
  model_id: string;
  deployment_id: string;
  deployment_name: string;
  deployment_slug: string;
  deployment_status: Deployment["status"];
  endpoint_url: string | null;
  revision_id: string;
  revision_version: number;
  role: DeploymentRole;
};

export type ScoreResponse = {
  request_id: string;
  correlation_id: string;
  deployment_id: string;
  deployment_revision_id: string;
  model_id: string;
  served_role: DeploymentRole;
  fallback_used: boolean;
  predictions: Array<{
    prediction_id: string;
    record_id: string;
    prediction: unknown;
    outputs: Record<string, unknown>;
  }>;
  warnings: string[];
};

export type InferenceInputField = {
  name: string;
  value_type: "number" | "integer" | "string" | "boolean";
  required: boolean;
  default_value: unknown;
  description: string;
  minimum: number | null;
  maximum: number | null;
  options: unknown[];
};

export type InferenceInputContract = {
  deployment_id: string;
  deployment_revision_id: string;
  model_id: string;
  role: DeploymentRole;
  fields: InferenceInputField[];
  example_features: Record<string, unknown>;
};

export type DeploymentModelOption = {
  model_id: string;
  name: string;
  version: string;
  business_case_id: string;
  stage: string;
  contract_signature: string;
  compatible_with_active_champion: boolean;
  allowed_roles: DeploymentRole[];
};

export type InferenceRequest = {
  id: string;
  deployment_id: string;
  deployment_revision_id: string;
  requested_by: string;
  correlation_id: string;
  status: "accepted" | "succeeded" | "failed";
  record_count: number;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  warnings: string[];
  error_code: string;
  error_message: string;
  champion_model_id: string;
  served_model_id: string;
  served_role: string;
  fallback_used: boolean;
  latency_ms: number | null;
  created_at: string;
  completed_at: string | null;
};

export type InferenceRequestSummary = Omit<
  InferenceRequest,
  "request_payload" | "response_payload"
>;

export type InferencePage = {
  items: InferenceRequest[];
  next_cursor: string | null;
};

export type InferenceSummaryPage = {
  items: InferenceRequestSummary[];
  next_cursor: string | null;
};

export type ChallengerReplay = {
  id: string;
  deployment_id: string;
  deployment_revision_id: string;
  challenger_model_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  max_requests: number;
  processed_requests: number;
  processed_records: number;
  failed_requests: number;
  error_message: string;
  created_at: string;
};

export type OnlineMonitoringRun = {
  id: string;
  deployment_id: string;
  business_case_id: string;
  owner_id: string;
  requested_by: string;
  status: "queued" | "running" | "succeeded" | "failed";
  since: string;
  until: string;
  source_before: string;
  actuals_dataset_id: string;
  aggregation_granularity: "none" | "hour" | "day" | "week" | "month";
  actuals_artifact_id: string;
  join_strategy: "auto" | "prediction_id" | "request_record_id" | "record_id" | "not_applicable";
  actuals_prediction_id_column: string;
  actuals_request_id_column: string;
  actuals_record_id_column: string;
  actuals_target_column: string;
  problem_type: string;
  target_column: string;
  time_basis: "scored_at";
  processed_request_count: number;
  processed_row_count: number;
  matched_row_count: number;
  missing_actuals_count: number;
  unmatched_actuals_count: number;
  snapshot_dataset_id: string;
  joined_dataset_id: string;
  report_artifact_id: string;
  report: Record<string, unknown>;
  warnings: string[];
  error_message: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  archived_at: string | null;
  archived_by: string;
  archive_reason: string;
};

export type OnlineMonitoringBucketEvaluation = {
  bucket_start: string;
  bucket_end: string;
  label: string;
  evaluation: ModelEvaluationSnapshot;
};
