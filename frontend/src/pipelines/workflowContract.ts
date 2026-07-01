import {
  emptyPipelineDefinition,
  normalizePipelineDefinition
} from "./pipelineContract";
import type { PipelineDefinition } from "./pipelineContract";

export type WorkflowStepDefinition = {
  step_id: string;
  name: string;
  type: "data_engineering";
  inputs: Array<{
    port_id: string;
    source: { step_id: string; port_id: string };
  }>;
  output_port_id: string;
  config: {
    definition: PipelineDefinition;
  };
};

export type WorkflowDefinition = {
  contract_version: "2.0";
  steps: WorkflowStepDefinition[];
  outputs: Array<{
    output_id: string;
    source: { step_id: string; port_id: string };
  }>;
  parameters: Record<string, unknown>;
};

export function emptyWorkflowDefinition(): WorkflowDefinition {
  return {
    contract_version: "2.0",
    steps: [],
    outputs: [],
    parameters: {}
  };
}

export function normalizeWorkflowDefinition(value: unknown): WorkflowDefinition {
  if (!value || typeof value !== "object") return emptyWorkflowDefinition();
  const raw = value as Record<string, unknown>;
  if (raw.contract_version !== "2.0") {
    const legacy = normalizePipelineDefinition(raw);
    const empty = legacy.inputs.length === 0
      && legacy.steps.length === 0
      && legacy.outputs.length === 0;
    if (empty) return emptyWorkflowDefinition();
    return {
      contract_version: "2.0",
      steps: [{
        step_id: "de_1",
        name: "Data Engineering",
        type: "data_engineering",
        inputs: [],
        output_port_id: "dataset",
        config: { definition: legacy }
      }],
      outputs: [{ output_id: "result", source: { step_id: "de_1", port_id: "dataset" } }],
      parameters: {}
    };
  }
  const steps = Array.isArray(raw.steps)
    ? raw.steps.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const step = item as Record<string, unknown>;
        const config = step.config && typeof step.config === "object"
          ? step.config as Record<string, unknown>
          : {};
        return [{
          step_id: String(step.step_id ?? "de_1"),
          name: String(step.name ?? "Data Engineering"),
          type: "data_engineering" as const,
          inputs: Array.isArray(step.inputs)
            ? step.inputs as WorkflowStepDefinition["inputs"]
            : [],
          output_port_id: String(step.output_port_id ?? "dataset"),
          config: { definition: normalizePipelineDefinition(config.definition) }
        }];
      })
    : [];
  return {
    contract_version: "2.0",
    steps,
    outputs: Array.isArray(raw.outputs)
      ? raw.outputs as WorkflowDefinition["outputs"]
      : [],
    parameters: raw.parameters && typeof raw.parameters === "object"
      ? raw.parameters as Record<string, unknown>
      : {}
  };
}

export { emptyPipelineDefinition };
