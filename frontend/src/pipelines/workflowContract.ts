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
  emptyScoringDefinition,
  emptyTrainingDefinition,
  normalizeScoringDefinition,
  normalizeTrainingDefinition,
  validateTrainingConfiguration
} from "./modelingContract";
import type { ScoringDefinition, TrainingDefinition } from "./modelingContract";
import {
  emptyMonitoringDefinition,
  normalizeMonitoringDefinition
} from "./monitoringContract";
import type { MonitoringDefinition } from "./monitoringContract";

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
      type: "automl";
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
    }
  | {
      step_id: string;
      name: string;
      type: "monitoring";
      inputs: Array<{ port_id: "data"; source: { step_id: string; port_id: string } }>;
      output_port_id: "performance_report";
      additional_output_port_ids: string[];
      config: { definition: MonitoringDefinition };
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

export type PipelineTemplate = "training" | "automl" | "batch_scoring" | "custom" | "monitoring";

export function workflowTemplateDefinition(
  template: PipelineTemplate,
  targetColumn = "target"
): WorkflowDefinition {
  if (template === "custom") {
    return {
      ...emptyWorkflowDefinition(),
      parameters: { template }
    };
  }
  if (template === "monitoring") {
    const processStep: DataEngineeringWorkflowStep = {
      step_id: "process_join_1",
      name: "Process & Join",
      type: "data_engineering",
      inputs: [],
      output_port_id: "dataset",
      additional_output_port_ids: [],
      config: {
        definition: {
          contract_version: "1.0",
          inputs: [
            {
              input_id: "predictions",
              dataset_id: "",
              output_port_id: "out",
              version_policy: "select_at_run_any"
            },
            {
              input_id: "actuals",
              dataset_id: "",
              output_port_id: "out",
              version_policy: "select_at_run_any"
            }
          ],
          steps: [{
            step_id: "join_predictions_actuals",
            type: "join",
            inputs: [
              { port_id: "left", source: { node_id: "predictions", port_id: "out" } },
              { port_id: "right", source: { node_id: "actuals", port_id: "out" } }
            ],
            output_port_id: "out",
            config: {
              join_type: "left",
              keys: [{ left: "row_id", right: "row_id" }],
              right_suffix: "_actuals"
            }
          }],
          outputs: [{
            output_id: "joined_monitoring_data",
            input: { node_id: "join_predictions_actuals", port_id: "out" },
            materialization: "dataset",
            write_mode: "replace",
            dataset_name: "Predictions with actuals",
            business_case_role: "monitoring_input"
          }],
          parameters: { purpose: "monitoring_process_join" }
        }
      }
    };
    const monitoringStep: Extract<WorkflowStepDefinition, { type: "monitoring" }> = {
      step_id: "monitoring_1",
      name: "Performance Report",
      type: "monitoring",
      inputs: [{
        port_id: "data",
        source: { step_id: processStep.step_id, port_id: processStep.output_port_id }
      }],
      output_port_id: "performance_report",
      additional_output_port_ids: [],
      config: { definition: emptyMonitoringDefinition() }
    };
    return {
      contract_version: "2.0",
      steps: [processStep, monitoringStep],
      outputs: workflowOutputsForStep(monitoringStep),
      parameters: { template }
    };
  }
  const deStep: DataEngineeringWorkflowStep = {
    step_id: "de_1",
    name: template === "training" || template === "automl" ? "Data Engineering" : "Scoring Data Engineering",
    type: "data_engineering",
    inputs: [],
    output_port_id: "dataset",
    additional_output_port_ids: [],
    config: { definition: emptyPipelineDefinition() }
  };
  if (template === "automl") {
    const featureBase = emptyFeatureEngineeringDefinition();
    const featureDefinition: FeatureEngineeringDefinition = {
      ...featureBase,
      evaluation: {
        ...featureBase.evaluation,
        split_strategy: "stratified",
        // Keep the initial draft structurally valid. The user can still choose a
        // different target/strategy once the upstream schema is configured.
        stratify_column: targetColumn.trim() || "target",
        validation_size: 0.1,
        test_size: 0.2
      },
      outputs: [
        { output_id: "training_features", input_id: "training", dataset_name: "AutoML training", business_case_role: "training" },
        { output_id: "validation_features", input_id: "validation", dataset_name: "AutoML validation", business_case_role: "validation" },
        { output_id: "test_features", input_id: "test", dataset_name: "AutoML holdout test", business_case_role: "test" }
      ]
    };
    const featureStep: FeatureEngineeringWorkflowStep = {
      step_id: "fe_1",
      name: "Evaluation Split",
      type: "feature_engineering",
      inputs: [{ port_id: "training", source: { step_id: deStep.step_id, port_id: deStep.output_port_id } }],
      output_port_id: "training",
      additional_output_port_ids: ["validation", "test", "fitted_transform"],
      config: { definition: featureDefinition }
    };
    const automlDefinition: TrainingDefinition = {
      ...emptyTrainingDefinition(),
      model_name: "AutoML champion",
      optimization: {
        ...emptyTrainingDefinition().optimization,
        mode: "automl",
        max_trials: 50,
        timeout_seconds: 3600
      }
    };
    const automlStep: Extract<WorkflowStepDefinition, { type: "automl" }> = {
      step_id: "automl_1",
      name: "AutoML",
      type: "automl",
      inputs: [
        { port_id: "training", source: { step_id: featureStep.step_id, port_id: "training" } },
        { port_id: "validation", source: { step_id: featureStep.step_id, port_id: "validation" } },
        { port_id: "test", source: { step_id: featureStep.step_id, port_id: "test" } },
        { port_id: "fitted_transform", source: { step_id: featureStep.step_id, port_id: "fitted_transform" } }
      ],
      output_port_id: "model",
      additional_output_port_ids: ["metrics", "test"],
      config: { definition: automlDefinition }
    };
    const scoringStep: Extract<WorkflowStepDefinition, { type: "scoring" }> = {
      step_id: "scoring_1",
      name: "Holdout Test Scoring",
      type: "scoring",
      inputs: [
        { port_id: "data", source: { step_id: automlStep.step_id, port_id: "test" } },
        { port_id: "model", source: { step_id: automlStep.step_id, port_id: "model" } }
      ],
      output_port_id: "predictions",
      additional_output_port_ids: [],
      config: { definition: { ...emptyScoringDefinition(), report_name: "AutoML holdout report" } }
    };
    return {
      contract_version: "2.0",
      steps: [deStep, featureStep, automlStep, scoringStep],
      outputs: workflowOutputsForStep(scoringStep),
      parameters: { template }
    };
  }
  if (template === "batch_scoring") {
    const featureDefinition: FeatureEngineeringDefinition = {
      ...emptyFeatureEngineeringDefinition(),
      mode: "transform",
      inputs: [{
        input_id: "scoring_input",
        role: "scoring_input",
        dataset_id: "",
        version_policy: "select_at_run_any"
      }],
      outputs: [{
        output_id: "scoring_features",
        input_id: "scoring_input",
        dataset_name: "Scoring features",
        business_case_role: "scoring_input"
      }]
    };
    const featureStep: FeatureEngineeringWorkflowStep = {
      step_id: "fe_1",
      name: "Feature Engineering Transform",
      type: "feature_engineering",
      inputs: [{
        port_id: "scoring_input",
        source: { step_id: deStep.step_id, port_id: deStep.output_port_id }
      }],
      output_port_id: "scoring_input",
      additional_output_port_ids: [],
      config: { definition: featureDefinition }
    };
    const scoringStep: Extract<WorkflowStepDefinition, { type: "scoring" }> = {
      step_id: "scoring_1",
      name: "Batch Scoring",
      type: "scoring",
      inputs: [{
        port_id: "data",
        source: { step_id: featureStep.step_id, port_id: featureStep.output_port_id }
      }],
      output_port_id: "predictions",
      additional_output_port_ids: [],
      config: {
        definition: {
          ...emptyScoringDefinition(),
          purpose: "batch",
          dataset_name: "Batch predictions",
          report_name: "Batch scoring"
        }
      }
    };
    return {
      contract_version: "2.0",
      steps: [deStep, featureStep, scoringStep],
      outputs: workflowOutputsForStep(scoringStep),
      parameters: { template }
    };
  }

  const featureDefinition: FeatureEngineeringDefinition = {
    ...emptyFeatureEngineeringDefinition(),
    inputs: [
      { input_id: "training", role: "training", dataset_id: "", version_policy: "latest" },
      { input_id: "validation", role: "validation", dataset_id: "", version_policy: "latest" },
      { input_id: "test", role: "test", dataset_id: "", version_policy: "latest" }
    ],
    outputs: [
      {
        output_id: "training_features",
        input_id: "training",
        dataset_name: "Training features",
        business_case_role: "training"
      },
      {
        output_id: "validation_features",
        input_id: "validation",
        dataset_name: "Validation features",
        business_case_role: "validation"
      },
      {
        output_id: "test_features",
        input_id: "test",
        dataset_name: "Test features",
        business_case_role: "test"
      }
    ]
  };
  const featureStep: FeatureEngineeringWorkflowStep = {
    step_id: "fe_1",
    name: "Feature Engineering",
    type: "feature_engineering",
    inputs: [{
      port_id: "training",
      source: { step_id: deStep.step_id, port_id: deStep.output_port_id }
    }],
    output_port_id: "training",
    additional_output_port_ids: ["validation", "test", "fitted_transform"],
    config: { definition: featureDefinition }
  };
  const trainingStep: Extract<WorkflowStepDefinition, { type: "training" }> = {
    step_id: "training_1",
    name: "Model Training",
    type: "training",
    inputs: [
      { port_id: "training", source: { step_id: featureStep.step_id, port_id: "training" } },
      { port_id: "validation", source: { step_id: featureStep.step_id, port_id: "validation" } },
      { port_id: "fitted_transform", source: { step_id: featureStep.step_id, port_id: "fitted_transform" } }
    ],
    output_port_id: "model",
    additional_output_port_ids: ["metrics"],
    config: { definition: emptyTrainingDefinition() }
  };
  const scoringStep: Extract<WorkflowStepDefinition, { type: "scoring" }> = {
    step_id: "scoring_1",
    name: "Test Scoring",
    type: "scoring",
    inputs: [
      { port_id: "data", source: { step_id: featureStep.step_id, port_id: "test" } },
      { port_id: "model", source: { step_id: trainingStep.step_id, port_id: "model" } }
    ],
    output_port_id: "predictions",
    additional_output_port_ids: [],
    config: { definition: emptyScoringDefinition() }
  };
  return {
    contract_version: "2.0",
    steps: [deStep, featureStep, trainingStep, scoringStep],
    outputs: workflowOutputsForStep(scoringStep),
    parameters: { template }
  };
}

export function canonicalizeWorkflowDatasetIds(
  definition: WorkflowDefinition,
  datasets: DataAsset[]
): WorkflowDefinition {
  return normalizeWorkflowDefinition({
    ...definition,
    steps: definition.steps.map((step) => {
      if (step.type === "training" || step.type === "automl" || step.type === "scoring") return step;
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
              if (input.version_policy === "pinned") return input;
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
        if (step.type === "training" || step.type === "automl") {
          return [{
            step_id: String(step.step_id ?? (step.type === "automl" ? "automl_1" : "training_1")),
            name: String(step.name ?? (step.type === "automl" ? "AutoML" : "Model Training")),
            type: step.type,
            inputs: Array.isArray(step.inputs)
              ? step.inputs as Extract<WorkflowStepDefinition, { type: "training" | "automl" }>["inputs"]
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
        if (step.type === "monitoring") {
          return [{
            step_id: String(step.step_id ?? "monitoring_1"),
            name: String(step.name ?? "Performance Report"),
            type: "monitoring",
            inputs: Array.isArray(step.inputs)
              ? step.inputs as Extract<WorkflowStepDefinition, { type: "monitoring" }>["inputs"]
              : [],
            output_port_id: "performance_report",
            additional_output_port_ids: [],
            config: { definition: normalizeMonitoringDefinition(config.definition) }
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
  const migratedSteps = migrateAutoMLTestScoring(steps);
  const rawOutputs = Array.isArray(raw.outputs)
    ? raw.outputs as WorkflowDefinition["outputs"]
    : [];
  const lastStep = migratedSteps.at(-1);
  return {
    contract_version: "2.0",
    steps: migratedSteps,
    outputs: lastStep?.type === "feature_engineering"
      ? workflowOutputsForStep(lastStep)
      : rawOutputs,
    parameters: raw.parameters && typeof raw.parameters === "object"
      ? raw.parameters as Record<string, unknown>
      : {}
  };
}

function migrateAutoMLTestScoring(steps: WorkflowStepDefinition[]): WorkflowStepDefinition[] {
  const automl = steps.find((step) => step.type === "automl");
  const scoring = steps.find((step) => step.type === "scoring" && step.config.definition.purpose === "test");
  if (!automl || !scoring || !automl.config.definition.auto_feature_engineering.enabled) return steps;
  const rawTest = scoring.inputs.find((input) => input.port_id === "data" && input.source.port_id === "test");
  if (!rawTest) return steps;
  const automlInputs = automl.inputs.some((input) => input.port_id === "test")
    ? automl.inputs
    : [...automl.inputs, { port_id: "test", source: rawTest.source }];
  const migratedAutoML = {
    ...automl,
    inputs: automlInputs,
    additional_output_port_ids: Array.from(new Set([...automl.additional_output_port_ids, "test"]))
  } as WorkflowStepDefinition;
  const migratedScoring = {
    ...scoring,
    inputs: scoring.inputs.map((input) => input.port_id === "data"
      ? { ...input, source: { step_id: automl.step_id, port_id: "test" } }
      : input)
  } as WorkflowStepDefinition;
  return steps.map((step) => step.step_id === automl.step_id
    ? migratedAutoML
    : step.step_id === scoring.step_id ? migratedScoring : step);
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

export function validateWorkflowConfiguration(definition: WorkflowDefinition): string[] {
  const issues: string[] = [];
  const stepIds = definition.steps.map((step) => step.step_id);
  const uniqueStepIds = new Set(stepIds);
  if (uniqueStepIds.size !== stepIds.length) issues.push("Workflow step IDs must be unique.");
  const outputIds = definition.outputs.map((output) => output.output_id);
  if (new Set(outputIds).size !== outputIds.length) issues.push("Workflow output IDs must be unique.");
  const ports = new Map(definition.steps.map((step) => [
    step.step_id,
    new Set([step.output_port_id, ...step.additional_output_port_ids])
  ]));
  for (const step of definition.steps) {
    if (!step.name.trim()) issues.push(`Workflow step '${step.step_id}' requires a name.`);
    const inputPorts = step.inputs.map((input) => input.port_id);
    if (new Set(inputPorts).size !== inputPorts.length) {
      issues.push(`Workflow step '${step.step_id}' has duplicate input ports.`);
    }
    for (const input of step.inputs) {
      if (!ports.get(input.source.step_id)?.has(input.source.port_id)) {
        issues.push(
          `Workflow step '${step.step_id}' references missing output '${input.source.step_id}.${input.source.port_id}'.`
        );
      }
    }
    if (step.type === "training" || step.type === "automl") {
      issues.push(...validateTrainingConfiguration(step.config.definition));
      const ports = new Set(step.inputs.map((input) => input.port_id));
      if (!ports.has("training")) issues.push(`${step.type === "automl" ? "AutoML" : "Training"} requires an explicit training input port.`);
      if (step.type === "automl" && step.config.definition.optimization.mode !== "automl") {
        issues.push("AutoML step requires AutoML optimization mode.");
      }
      if (step.config.definition.early_stopping && !ports.has("validation")) {
        issues.push("Training early stopping requires an explicit validation input port.");
      }
    }
    if (step.type === "scoring") {
      const scoring = step.config.definition;
      if (!scoring.row_id_column.trim()) issues.push("Scoring requires a row ID column before publish or dry-run.");
      if (scoring.purpose === "batch" && !scoring.model_artifact_id.trim()) {
        issues.push("Batch scoring requires a pinned model artifact.");
      }
      if (scoring.purpose === "batch" && scoring.target_column.trim()) {
        issues.push("Batch scoring cannot consume a target column; actuals belong to monitoring.");
      }
    }
  }
  for (const output of definition.outputs) {
    if (!ports.get(output.source.step_id)?.has(output.source.port_id)) {
      issues.push(`Workflow output '${output.output_id}' references missing output '${output.source.step_id}.${output.source.port_id}'.`);
    }
  }
  return Array.from(new Set(issues));
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export { emptyPipelineDefinition };
export { emptyFeatureEngineeringDefinition };
