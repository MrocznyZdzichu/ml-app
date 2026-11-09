import type { ModelEvaluationSnapshot } from "./modelEvaluation";

export type ScoringReport = {
  id: string;
  owner_id: string;
  name: string;
  logical_id: string;
  version_number: number;
  business_case_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  pipeline_run_id: string;
  pipeline_step_id: string;
  problem_type: string;
  prediction_dataset_id: string;
  prediction_artifact_id: string;
  model_artifact_id: string;
  evaluated_row_count: number;
  evaluation: ModelEvaluationSnapshot;
  lineage: Record<string, unknown>;
  created_at: string;
};
