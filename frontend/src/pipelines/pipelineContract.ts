export type PipelinePortReference = {
  node_id: string;
  port_id: string;
};

export type PipelineInputDefinition = {
  input_id: string;
  dataset_id: string;
  output_port_id: string;
  version_policy: "latest" | "select_at_run";
};

export type PipelineStepDefinition = {
  step_id: string;
  type: PipelineStepType;
  inputs: Array<{ port_id: string; source: PipelinePortReference }>;
  output_port_id: string;
  config: Record<string, unknown>;
};

export type PipelineOutputDefinition = {
  output_id: string;
  input: PipelinePortReference;
  materialization: "temporary" | "dataset";
  write_mode: "replace";
  dataset_name: string;
  business_case_role: "source" | "training" | "validation" | "test" | "scoring_input" | "scoring_output" | "monitoring_actuals" | "reference";
  data_contract?: DataContractDefinition;
};

export type DataContractDefinition = {
  columns: Array<{
    name: string;
    type: string;
    nullable: boolean;
    unique: boolean;
    minimum?: number;
    maximum?: number;
    allowed_values?: Array<string | number | boolean>;
    policy: "fail" | "warn" | "reject";
  }>;
  schema_drift_policy: "fail" | "warn";
  allow_unexpected_columns: boolean;
};

export type PipelineDefinition = {
  contract_version: "1.0";
  inputs: PipelineInputDefinition[];
  steps: PipelineStepDefinition[];
  outputs: PipelineOutputDefinition[];
  parameters: Record<string, unknown>;
};

export type PipelineStepType =
  | "select_columns"
  | "add_identifier"
  | "rename_columns"
  | "cast_columns"
  | "filter_rows"
  | "sort_rows"
  | "deduplicate"
  | "impute_missing"
  | "derive_column"
  | "aggregate"
  | "join"
  | "union"
  | "map_categories"
  | "custom_sql";

export function normalizePipelineDefinition(value: unknown): PipelineDefinition {
  if (!value || typeof value !== "object") return emptyPipelineDefinition();
  const raw = value as Record<string, unknown>;
  const steps = Array.isArray(raw.steps)
    ? (raw.steps as PipelineStepDefinition[]).map((step) => (
        step.type === "map_categories"
          ? { ...step, config: { ...step.config, mapping: sanitizeCategoryMapping(recordValue(step.config?.mapping)) } }
          : step
      ))
    : [];
  return rewireSequentialFlow({
    contract_version: "1.0",
    inputs: Array.isArray(raw.inputs)
      ? (raw.inputs as Array<Partial<PipelineInputDefinition>>).map((input) => ({
          input_id: String(input.input_id ?? "source"),
          dataset_id: String(input.dataset_id ?? ""),
          output_port_id: String(input.output_port_id ?? "out"),
          version_policy: input.version_policy === "select_at_run" ? "select_at_run" : "latest"
        }))
      : [],
    steps,
    outputs: Array.isArray(raw.outputs)
      ? (raw.outputs as Array<Partial<PipelineOutputDefinition>>).map((output) => ({
          output_id: String(output.output_id ?? "result"),
          input: output.input as PipelinePortReference,
          materialization: output.materialization === "temporary" ? "temporary" : "dataset",
          write_mode: "replace",
          dataset_name: String(output.dataset_name ?? output.output_id ?? "result"),
          business_case_role: output.business_case_role ?? "source",
          data_contract: output.data_contract
        }))
      : [],
    parameters: raw.parameters && typeof raw.parameters === "object"
      ? raw.parameters as Record<string, unknown>
      : {}
  });
}

export function emptyPipelineDefinition(): PipelineDefinition {
  return { contract_version: "1.0", inputs: [], steps: [], outputs: [], parameters: {} };
}

export function sanitizeCategoryMapping(mapping: Record<string, unknown>) {
  if (Object.keys(mapping).length === 1 && mapping["old_value"] === "new_value") {
    return {};
  }
  return mapping;
}

export function rewireSequentialFlow(definition: PipelineDefinition): PipelineDefinition {
  if (definition.inputs.length !== 1 || definition.steps.some((step) => step.inputs.length !== 1)) {
    return definition;
  }
  const source = {
    node_id: definition.inputs[0].input_id,
    port_id: definition.inputs[0].output_port_id
  };
  const steps = definition.steps.map((step, index) => ({
    ...step,
    inputs: [{
      ...step.inputs[0],
      source: index === 0
        ? source
        : {
            node_id: definition.steps[index - 1].step_id,
            port_id: definition.steps[index - 1].output_port_id
          }
    }]
  }));
  const last = steps.at(-1);
  return {
    ...definition,
    steps,
    outputs: last
      ? definition.outputs.map((output) => ({
          ...output,
          input: { node_id: last.step_id, port_id: last.output_port_id }
        }))
      : definition.outputs
  };
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}
