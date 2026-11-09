export type ArtifactDependency = {
  direction: "upstream" | "downstream";
  role: string;
  artifact_id: string;
  artifact_type: string;
  reference_id: string;
  business_case_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  pipeline_run_id: string;
  pipeline_step_id: string;
};

export type DatasetLineageReference = {
  artifact_id: string;
  artifact_type: string;
  dataset_id: string;
  logical_id: string;
  version_number: number;
  name: string;
  role: string;
  stage: string;
  format: string;
  row_count: number | null;
  pipeline_step_id: string;
  pipeline_run_id: string;
  depth: number;
};
