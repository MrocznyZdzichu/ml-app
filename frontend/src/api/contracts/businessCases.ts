import type { BusinessCaseAccessRole } from "./businessCaseAccess";

export type BusinessCase = {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  problem_type: string;
  status: string;
  business_owner: string;
  primary_metric: string;
  target_column: string;
  business_goal: string;
  success_criteria: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  access_role: BusinessCaseAccessRole;
};

export type BusinessCaseDataAttachment = {
  id: string;
  owner_id: string;
  business_case_id: string;
  artifact_id: string;
  data_asset_id: string;
  data_asset_kind: "dataset" | "data_view";
  role: string;
  context_note: string;
  primary_key_column: string;
  target_column: string;
  created_by: string;
  created_at: string;
  data_asset_name?: string;
  data_asset_status?: string;
  data_asset_source_type?: string;
  data_asset_logical_id?: string;
  data_asset_version_number?: number;
  data_asset_pipeline_id?: string;
  data_asset_pipeline_template?: string;
};
