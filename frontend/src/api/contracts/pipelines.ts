import type { ModelEvaluationSnapshot } from "./modelEvaluation";
import type { ModelArtifact } from "./models";

export type Pipeline = {
  id: string;
  owner_id: string;
  business_case_id: string;
  name: string;
  description: string;
  type: string;
  status: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  latest_published_version_number: number | null;
  published_version_count: number;
  draft_version_number: number | null;
  template: string;
};

export type PipelineVersion = {
  id: string;
  owner_id: string;
  pipeline_id: string;
  business_case_id: string;
  version_number: number;
  status: string;
  definition: Record<string, unknown>;
  definition_hash: string;
  created_by: string;
  created_at: string;
  published_by: string;
  published_at: string | null;
};

export type PipelineRun = {
  id: string;
  owner_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  business_case_id: string;
  status: string;
  trigger_type: string;
  runtime_parameters: Record<string, unknown>;
  is_dry_run: boolean;
  requested_step_id: string;
  input_row_count: number | null;
  processed_row_count: number | null;
  output_row_count: number | null;
  rejected_row_count: number | null;
  warnings: string[];
  events: PipelineRunEvent[];
  output_artifact_ids: string[];
  output_manifest: Array<{
    output_id: string;
    artifact_type?: "dataset" | "prediction_dataset" | "feature_transform" | "model_version" | "metrics" | "report";
    materialization: "temporary" | "dataset" | "artifact";
    location_uri: string;
    row_count?: number;
    schema?: Array<{ name: string; type: string }>;
    schema_hash?: string;
    state_hash?: string;
    feature_manifest?: Array<Record<string, unknown>>;
    data_scope: "full";
    is_dry_run: boolean;
    dataset_name?: string;
    business_case_role?: string;
    dataset_id?: string;
    logical_id?: string;
    version_number?: number;
    artifact_id?: string;
    pipeline_step_id?: string;
    output_stage?: "intermediate" | "final";
    quality_output_kind?: "rejected_records";
    source_output_id?: string;
    evaluation?: ModelEvaluationSnapshot | Record<string, unknown>;
    report_type?: "training_evaluation_report" | "monitoring_performance_report";
    report_name?: string;
    report?: TrainingEvaluationReport | Record<string, unknown>;
    score_contract?: Record<string, unknown>;
    row_id_column?: string;
    prediction_column?: string;
    split_evaluation?: Record<string, unknown>;
    model_name?: string;
    algorithm?: string;
    problem_type?: string;
    target_column?: string;
    feature_columns?: string[];
    model_hash?: string;
    metrics?: Record<string, number>;
    training_config?: Record<string, unknown>;
    model_parameters?: ModelArtifact["model_parameters"];
    quality?: {
      status: "not_configured" | "passed" | "issues_detected";
      data_scope: "full";
      checked_row_count?: number;
      rejected_row_count?: number;
      checks: Array<{
        column: string;
        check: string;
        policy: "fail" | "warn" | "reject";
        violation_count: number;
        passed: boolean;
      }>;
      schema_drift: Array<Record<string, unknown>>;
    };
    file_size_bytes?: number;
    preview?: {
      records: Array<Record<string, unknown>>;
      returned_count: number;
      limit: number;
      sampled: boolean;
    };
  }>;
  error_message: string;
  created_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type TrainingEvaluationReport = {
  contract_version: "1.0";
  report_type: "training_evaluation_report";
  name: string;
  created_at: string;
  data_scope: {
    mode: "full" | "sample";
    row_count: number;
    sampled: boolean;
    sample_size: number;
    sampling_method: string;
    seed: number | null;
  };
  sections: {
    summary?: Record<string, unknown>;
    metrics?: Record<string, unknown>;
    validation?: Record<string, unknown>;
    search?: Record<string, unknown>;
    feature_engineering?: Record<string, unknown>;
    model_parameters?: Record<string, unknown>;
    explainability?: {
      status?: string;
      reason?: string;
      scope?: Record<string, unknown>;
      permutation_importance?: Array<{ feature: string; mean_importance: number; std?: number }>;
      shap?: {
        status?: string;
        explainer?: string;
        reason?: string;
        values?: Array<{ feature: string; mean_absolute_shap: number }>;
      };
      notes?: string[];
    };
  };
  diagnostics: Array<Record<string, unknown>>;
  warnings: string[];
};

export type PipelineStepRun = {
  id: string;
  owner_id: string;
  pipeline_run_id: string;
  pipeline_step_id: string;
  step_type: string;
  status: string;
  input_row_count: number | null;
  processed_row_count: number | null;
  output_row_count: number | null;
  warnings: string[];
  events: PipelineRunEvent[];
  output_manifest: PipelineRun["output_manifest"];
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
};

export type PipelineRunStatus = Pick<
  PipelineRun,
  | "id"
  | "pipeline_id"
  | "pipeline_version_id"
  | "business_case_id"
  | "status"
  | "trigger_type"
  | "is_dry_run"
  | "requested_step_id"
  | "input_row_count"
  | "processed_row_count"
  | "output_row_count"
  | "rejected_row_count"
  | "error_message"
  | "created_at"
  | "started_at"
  | "finished_at"
>;

export type PipelineRunEvent = {
  timestamp: string;
  level: "info" | "warning" | "error" | string;
  type: string;
  step_id: string;
  message: string;
  details: Record<string, unknown>;
};

export type PipelineRunDetails = {
  run: PipelineRun;
  pipeline_version: {
    id: string;
    version_number: number;
    definition_hash: string;
    status: string;
  };
  resolved_inputs: Array<{
    input_id: string;
    step_id: string;
    logical_id: string;
    version_policy: string;
    dataset_id: string;
    version_number: number;
    dataset_name: string;
  }>;
  steps: PipelineStepRun[];
  outputs: PipelineRun["output_manifest"];
  lineage: Array<{
    artifact_id: string;
    artifact_type: string;
    reference_id: string;
    origin: string;
    lineage: Record<string, unknown>;
  }>;
};

export type PipelineRunOutputPreview = {
  output_id: string;
  pipeline_step_id: string;
  row_count: number;
  limit: number;
  offset: number;
  returned_count: number;
  records: Array<Record<string, unknown>>;
  has_next: boolean;
  has_previous: boolean;
  columns: Array<{ name: string; type: string }>;
};

export type PipelineRunOutputProfile = {
  output_id: string;
  pipeline_step_id: string;
  row_count: number;
  profiled_column_count: number;
  total_column_count: number;
  columns: Array<{
    name: string;
    null_count: number;
    non_null_count: number;
    approx_distinct_count: number;
    top_values: Array<{ value: unknown; count: number; share: number }>;
  }>;
};
