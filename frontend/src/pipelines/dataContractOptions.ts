export const businessCaseDataRoles = [
  "source",
  "training",
  "validation",
  "test",
  "scoring_input",
  "scoring_output",
  "monitoring_input",
  "monitoring_actuals",
  "reference"
] as const;

export type BusinessCaseDataRole = typeof businessCaseDataRoles[number];

export const businessCaseDataRoleOptions: Array<{
  value: BusinessCaseDataRole;
  label: string;
}> = businessCaseDataRoles.map((value) => ({
  value,
  label: value.replaceAll("_", " ").replace(/^\w/, (character) => character.toUpperCase())
}));

export const datasetVersionPolicies = [
  "latest",
  "pinned",
  "select_at_run",
  "select_at_run_any"
] as const;

export type DatasetVersionPolicy = typeof datasetVersionPolicies[number];

export const datasetVersionPolicyOptions: Array<{
  value: DatasetVersionPolicy;
  label: string;
}> = [
  { value: "latest", label: "Latest at run start" },
  { value: "pinned", label: "Pinned exact version" },
  { value: "select_at_run", label: "Select at run" },
  { value: "select_at_run_any", label: "Select any compatible BC dataset" }
];

export function normalizeDatasetVersionPolicy(value: unknown): DatasetVersionPolicy {
  return datasetVersionPolicies.includes(value as DatasetVersionPolicy)
    ? value as DatasetVersionPolicy
    : "latest";
}

export function requiresRuntimeDatasetSelection(policy: DatasetVersionPolicy) {
  return policy === "select_at_run" || policy === "select_at_run_any";
}
