import type { DataAsset } from "../api/client";
import {
  emptyPipelineDefinition,
  normalizePipelineDefinition
} from "./pipelineContract";
import type { PipelineDefinition } from "./pipelineContract";
import {
  emptyFeatureEngineeringDefinition,
  normalizeFeatureEngineeringDefinition
} from "./featureEngineeringContract";
import type { FeatureEngineeringDefinition } from "./featureEngineeringContract";
import {
  normalizeScoringDefinition,
  normalizeTrainingDefinition
} from "./modelingContract";
import type { ScoringDefinition, TrainingDefinition } from "./modelingContract";

export type DataEngineeringWorkflowStep = {
  step_id: string;
  name: string;
  type: "data_engineering";
  inputs: Array<{
    port_id: string;
    source: { step_id: string; port_id: string };
  }>;
  output_port_id: string;
  additional_output_port_ids: string[];
  config: {
    definition: PipelineDefinition;
  };
};

export type FeatureEngineeringWorkflowStep = {
  step_id: string;
  name: string;
  type: "feature_engineering";
  inputs: Array<{
    port_id: string;
    source: { step_id: string; port_id: string };
  }>;
  output_port_id: string;
  additional_output_port_ids: string[];
  config: {
    definition: FeatureEngineeringDefinition;
  };
};

export type WorkflowStepDefinition =
  | DataEngineeringWorkflowStep
  | FeatureEngineeringWorkflowStep
  | {
      step_id: string;
      name: string;
      type: "training";
      inputs: Array<{ port_id: string; source: { step_id: string; port_id: string } }>;
      output_port_id: "model";
      additional_output_port_ids: string[];
      config: { definition: TrainingDefinition };
    }
  | {
      step_id: string;
      name: string;
      type: "scoring";
      inputs: Array<{ port_id: string; source: { step_id: string; port_id: string } }>;
      output_port_id: "predictions";
      additional_output_port_ids: string[];
      config: { definition: ScoringDefinition };
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

export function canonicalizeWorkflowDatasetIds(
  definition: WorkflowDefinition,
  datasets: DataAsset[]
): WorkflowDefinition {
  return normalizeWorkflowDefinition({
    ...definition,
    steps: definition.steps.map((step) => {
      if (step.type === "training" || step.type === "scoring") return step;
      const nested = recordValue(step.config.definition);
      const inputs = Array.isArray(nested.inputs) ? nested.inputs : [];
      return {
        ...step,
        config: {
          ...step.config,
          definition: {
            ...nested,
            inputs: inputs.map((value) => {
              const input = recordValue(value);
              const referenced = datasets.find((dataset) => dataset.id === input.dataset_id);
              return referenced ? { ...input, dataset_id: referenced.logical_id } : input;
            })
          }
        }
      };
    })
  });
}

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
        additional_output_port_ids: [],
        config: { definition: legacy }
      }],
      outputs: [{ output_id: "result", source: { step_id: "de_1", port_id: "dataset" } }],
      parameters: {}
    };
  }
  const steps: WorkflowStepDefinition[] = Array.isArray(raw.steps)
    ? raw.steps.flatMap<WorkflowStepDefinition>((item): WorkflowStepDefinition[] => {
        if (!item || typeof item !== "object") return [];
        const step = item as Record<string, unknown>;
        const config = step.config && typeof step.config === "object"
          ? step.config as Record<string, unknown>
          : {};
        if (step.type === "feature_engineering") {
          const featureDefinition = normalizeFeatureEngineeringDefinition(config.definition);
          const ports = featureEngineeringOutputPorts(featureDefinition);
          return [{
            step_id: String(step.step_id ?? "fe_1"),
            name: String(step.name ?? "Feature Engineering"),
            type: "feature_engineering" as const,
            inputs: Array.isArray(step.inputs)
              ? step.inputs as WorkflowStepDefinition["inputs"]
              : [],
            output_port_id: ports.primary,
            additional_output_port_ids: ports.additional,
            config: { definition: featureDefinition }
          }];
        }
        if (step.type === "training") {
          return [{
            step_id: String(step.step_id ?? "training_1"),
            name: String(step.name ?? "Model Training"),
            type: "training",
            inputs: Array.isArray(step.inputs)
              ? step.inputs as Extract<WorkflowStepDefinition, { type: "training" }>["inputs"]
              : [],
            output_port_id: "model",
            additional_output_port_ids: ["metrics"],
            config: { definition: normalizeTrainingDefinition(config.definition) }
          }];
        }
        if (step.type === "scoring") {
          return [{
            step_id: String(step.step_id ?? "scoring_1"),
            name: String(step.name ?? "Test Scoring"),
            type: "scoring",
            inputs: Array.isArray(step.inputs)
              ? step.inputs as Extract<WorkflowStepDefinition, { type: "scoring" }>["inputs"]
              : [],
            output_port_id: "predictions",
            additional_output_port_ids: [],
            config: { definition: normalizeScoringDefinition(config.definition) }
          }];
        }
        return [{
          step_id: String(step.step_id ?? "de_1"),
          name: String(step.name ?? "Data Engineering"),
          type: "data_engineering" as const,
          inputs: Array.isArray(step.inputs)
            ? step.inputs as WorkflowStepDefinition["inputs"]
            : [],
          output_port_id: String(step.output_port_id ?? "dataset"),
          additional_output_port_ids: Array.isArray(step.additional_output_port_ids)
            ? step.additional_output_port_ids.map(String)
            : [],
          config: { definition: normalizePipelineDefinition(config.definition) }
        }];
      })
    : [];
  const rawOutputs = Array.isArray(raw.outputs)
    ? raw.outputs as WorkflowDefinition["outputs"]
    : [];
  const lastStep = steps.at(-1);
  return {
    contract_version: "2.0",
    steps,
    outputs: lastStep?.type === "feature_engineering"
      ? workflowOutputsForStep(lastStep)
      : rawOutputs,
    parameters: raw.parameters && typeof raw.parameters === "object"
      ? raw.parameters as Record<string, unknown>
      : {}
  };
}

export function featureEngineeringOutputPorts(definition: FeatureEngineeringDefinition) {
  const roles = [...new Set(definition.outputs.map((output) => output.business_case_role))];
  const primary = roles.includes("training") ? "training" : roles[0] ?? "training";
  return {
    primary,
    additional: [
      ...roles.filter((role) => role !== primary),
      ...(definition.mode === "fit_transform" ? ["fitted_transform"] : [])
    ]
  };
}

export function workflowOutputsForStep(
  step: WorkflowStepDefinition
): WorkflowDefinition["outputs"] {
  if (step.type !== "feature_engineering") {
    return [{
      output_id: "result",
      source: { step_id: step.step_id, port_id: step.output_port_id }
    }];
  }
  return step.config.definition.outputs.map((output) => ({
    output_id: output.output_id,
    source: {
      step_id: step.step_id,
      port_id: output.business_case_role
    }
  }));
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export { emptyPipelineDefinition };
export { emptyFeatureEngineeringDefinition };
