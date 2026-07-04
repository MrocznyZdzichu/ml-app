import { Braces, Brain, Calculator, DatabaseZap, Plus, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCase,
  BusinessCaseDataAttachment,
  DataAsset,
  DatasetColumn,
  ModelArtifact
} from "../api/client";
import { FeatureEngineeringBuilder, inferFeatureRecipeColumns } from "./FeatureEngineeringBuilder";
import {
  emptyFeatureEngineeringDefinition,
  normalizeFeatureEngineeringDefinition
} from "./featureEngineeringContract";
import { PipelineBuilder } from "./PipelineBuilder";
import {
  emptyPipelineDefinition,
  normalizePipelineDefinition
} from "./pipelineContract";
import type { PipelineDefinition } from "./pipelineContract";
import { datasetColumns, inferPipelineOutputColumns, inputDatasetIds } from "./pipelineSchema";
import type { WorkflowDefinition, WorkflowStepDefinition } from "./workflowContract";
import { WorkflowDiagram } from "./WorkflowDiagram";
import { ScoringBuilder, TrainingBuilder } from "./ModelingBuilders";
import {
  deriveModelingDefaults,
  emptyScoringDefinition,
  emptyTrainingDefinition,
  scoringWithDefaults,
  trainingWithDefaults
} from "./modelingContract";
import {
  featureEngineeringOutputPorts,
  workflowOutputsForStep
} from "./workflowContract";

export type { WorkflowDefinition, WorkflowStepDefinition } from "./workflowContract";
export { emptyWorkflowDefinition, normalizeWorkflowDefinition } from "./workflowContract";

export function WorkflowEditor({
  definition,
  businessCase,
  datasets,
  models,
  dataAttachments,
  pipelineType,
  outputNameSuggestion,
  disabled,
  onChange
}: {
  definition: WorkflowDefinition;
  businessCase?: BusinessCase;
  datasets: DataAsset[];
  models: ModelArtifact[];
  dataAttachments: BusinessCaseDataAttachment[];
  pipelineType: string;
  outputNameSuggestion?: string;
  disabled: boolean;
  onChange: (definition: WorkflowDefinition) => void;
}) {
  const [expandedStepId, setExpandedStepId] = useState(definition.steps[0]?.step_id ?? "");
  const [schemaCache, setSchemaCache] = useState<Record<string, DatasetColumn[]>>({});
  const initializedModelingSteps = useRef(new Set<string>());
  const featureStep = definition.steps.find(
    (step) => step.type === "feature_engineering"
  );
  const featureDefinition = featureStep?.config.definition;
  const hasValidation = Boolean(
    featureStep
    && (
      featureStep.output_port_id === "validation"
      || featureStep.additional_output_port_ids.includes("validation")
    )
  );
  const dataEngineeringDefinition = previousDataEngineeringDefinition(
    definition.steps,
    definition.steps.length
  );
  const schemaDatasetIds = useMemo(() => Array.from(new Set([
    ...inputDatasetIds(dataEngineeringDefinition),
    ...(featureDefinition?.inputs.map((input) => input.dataset_id).filter(Boolean) ?? [])
  ])), [dataEngineeringDefinition, featureDefinition]);
  useEffect(() => {
    for (const datasetId of schemaDatasetIds) {
      const dataset = datasets.find((item) => item.id === datasetId);
      if (
        !dataset
        || schemaCache[datasetId]
        || (Array.isArray(dataset.metadata.source_schema) && dataset.metadata.source_schema.length > 0)
      ) continue;
      void api.previewDataset(datasetId, 1)
        .then((preview) => setSchemaCache((current) => ({
          ...current,
          [datasetId]: preview.columns
        })))
        .catch(() => setSchemaCache((current) => ({ ...current, [datasetId]: [] })));
    }
  }, [datasets, schemaCache, schemaDatasetIds]);
  const dagColumns = useMemo(() => {
    const upstream = inferPipelineOutputColumns(dataEngineeringDefinition, datasets, schemaCache);
    const direct = (featureDefinition?.inputs ?? []).flatMap((input) =>
      datasetColumns(datasets.find((dataset) => dataset.id === input.dataset_id), schemaCache)
    );
    const source = [...new Map([...upstream, ...direct].map((column) => [column.name, column])).values()];
    return inferFeatureRecipeColumns(source, featureDefinition?.transformations ?? []);
  }, [dataEngineeringDefinition, datasets, featureDefinition, schemaCache]);
  const modelingDefaults = useMemo(() => deriveModelingDefaults({
    businessCase,
    attachments: dataAttachments,
    featureDefinition,
    dagColumns,
    hasValidation,
    pipelineName: outputNameSuggestion ?? "Trained model"
  }), [businessCase, dagColumns, dataAttachments, featureDefinition, hasValidation, outputNameSuggestion]);
  const scoringModels = models.filter(
    (model) =>
      model.business_case_id === businessCase?.id
      && model.fitted_transform_artifact_id
      && Object.keys(model.data_engineering_definition).length > 0
      && Object.keys(model.feature_engineering_definition).length > 0
      && isInferenceSafeModelPreparation(model)
  );

  useEffect(() => {
    let changed = false;
    const steps = definition.steps.map((step) => {
      if (step.type === "training") {
        const initialize = !initializedModelingSteps.current.has(step.step_id);
        initializedModelingSteps.current.add(step.step_id);
        const defaulted = initialize
          ? trainingWithDefaults(modelingDefaults, step.config.definition)
          : step.config.definition;
        const next = hasValidation || !defaulted.early_stopping
          ? defaulted
          : { ...defaulted, early_stopping: false };
        const inputsWithoutValidation = step.inputs.filter((item) => item.port_id !== "validation");
        const inputs = hasValidation && featureStep
          ? [
              ...inputsWithoutValidation,
              {
                port_id: "validation",
                source: { step_id: featureStep.step_id, port_id: "validation" }
              }
            ]
          : inputsWithoutValidation;
        changed = changed
          || JSON.stringify(next) !== JSON.stringify(step.config.definition)
          || JSON.stringify(inputs) !== JSON.stringify(step.inputs);
        return { ...step, inputs, config: { definition: next } };
      }
      if (step.type === "scoring") {
        if (initializedModelingSteps.current.has(step.step_id)) return step;
        initializedModelingSteps.current.add(step.step_id);
        const next = scoringWithDefaults(modelingDefaults, step.config.definition);
        changed = changed || JSON.stringify(next) !== JSON.stringify(step.config.definition);
        return { ...step, config: { definition: next } };
      }
      return step;
    });
    if (changed) onChange({ ...definition, steps });
  }, [definition, modelingDefaults, onChange]);

  function addDataEngineeringStep() {
    if (definition.steps.length) return;
    const step: WorkflowStepDefinition = {
      step_id: "de_1",
      name: "Data Engineering",
      type: "data_engineering",
      inputs: [],
      output_port_id: "dataset",
      additional_output_port_ids: [],
      config: { definition: emptyPipelineDefinition() }
    };
    setExpandedStepId(step.step_id);
    onChange({
      ...definition,
      steps: [step],
      outputs: [{ output_id: "result", source: { step_id: step.step_id, port_id: step.output_port_id } }]
    });
  }

  function addFeatureEngineeringStep() {
    if (definition.steps.some((step) => step.type === "feature_engineering")) return;
    const upstream = definition.steps.at(-1);
    const step: WorkflowStepDefinition = {
      step_id: "fe_1",
      name: "Feature Engineering",
      type: "feature_engineering",
      inputs: upstream ? [{
        port_id: "training",
        source: { step_id: upstream.step_id, port_id: upstream.output_port_id }
      }] : [],
      output_port_id: "training",
      additional_output_port_ids: ["fitted_transform"],
      config: { definition: emptyFeatureEngineeringDefinition() }
    };
    setExpandedStepId(step.step_id);
    onChange({
      ...definition,
      steps: [...definition.steps, step],
      outputs: workflowOutputsForStep(step)
    });
  }

  function addTrainingStep() {
    if (definition.steps.some((step) => step.type === "training")) return;
    const feature = [...definition.steps].reverse().find((step) => step.type === "feature_engineering");
    if (!feature) return;
    const step: WorkflowStepDefinition = {
      step_id: "training_1",
      name: "Model Training",
      type: "training",
      inputs: [
        { port_id: "training", source: { step_id: feature.step_id, port_id: "training" } },
        ...(feature.additional_output_port_ids.includes("fitted_transform")
          ? [{
              port_id: "fitted_transform",
              source: { step_id: feature.step_id, port_id: "fitted_transform" }
            }]
          : []),
        ...(feature.additional_output_port_ids.includes("validation")
          ? [{
              port_id: "validation",
              source: { step_id: feature.step_id, port_id: "validation" }
            }]
          : [])
      ],
      output_port_id: "model",
      additional_output_port_ids: ["metrics"],
      config: { definition: trainingWithDefaults(modelingDefaults, emptyTrainingDefinition()) }
    };
    setExpandedStepId(step.step_id);
    onChange({ ...definition, steps: [...definition.steps, step], outputs: workflowOutputsForStep(step) });
  }

  function addScoringStep() {
    if (definition.steps.some((step) => step.type === "scoring")) return;
    const feature = definition.steps.find((step) => step.type === "feature_engineering");
    const training = definition.steps.find((step) => step.type === "training");
    if (!feature || !training) return;
    const dataPort = feature.additional_output_port_ids.includes("test") ? "test" : feature.output_port_id;
    const step: WorkflowStepDefinition = {
      step_id: "scoring_1",
      name: "Test Scoring",
      type: "scoring",
      inputs: [
        { port_id: "data", source: { step_id: feature.step_id, port_id: dataPort } },
        { port_id: "model", source: { step_id: training.step_id, port_id: "model" } }
      ],
      output_port_id: "predictions",
      additional_output_port_ids: [],
      config: { definition: scoringWithDefaults(modelingDefaults, emptyScoringDefinition()) }
    };
    setExpandedStepId(step.step_id);
    onChange({ ...definition, steps: [...definition.steps, step], outputs: workflowOutputsForStep(step) });
  }

  function configureBatchScoring(modelId: string) {
    const model = scoringModels.find((item) => item.id === modelId);
    if (!model) return;
    const sourceDe = normalizePipelineDefinition(model.data_engineering_definition);
    const sourceFe = normalizeFeatureEngineeringDefinition(
      model.feature_engineering_definition
    );
    const targetColumn = sourceFe.target_column;
    const deDefinition: PipelineDefinition = {
      ...sourceDe,
      inputs: sourceDe.inputs.map((input) => ({
        ...input,
        dataset_id: "",
        version_policy: "select_at_run_any"
      })),
      steps: sourceDe.steps.map((step) => ({
        ...step,
        config: sanitizeInferenceConfig(step.type, step.config, targetColumn)
      })),
      outputs: sourceDe.outputs.map((output) => ({
        ...output,
        materialization: "temporary",
        dataset_name: `${model.name} scoring-ready data`,
        business_case_role: "scoring_input",
        data_contract: output.data_contract
          ? {
              ...output.data_contract,
              columns: output.data_contract.columns.filter(
                (column) => column.name !== targetColumn
              )
            }
          : undefined
      }))
    };
    const deStep: WorkflowStepDefinition = {
      step_id: "de_1",
      name: "Scoring Data Engineering",
      type: "data_engineering",
      inputs: [],
      output_port_id: "dataset",
      additional_output_port_ids: [],
      config: { definition: deDefinition }
    };
    const feDefinition = {
      ...sourceFe,
      mode: "transform" as const,
      inputs: [{
        input_id: "scoring_input",
        role: "scoring_input" as const,
        dataset_id: "",
        version_policy: "latest" as const
      }],
      outputs: [{
        output_id: "scoring_features",
        input_id: "scoring_input",
        dataset_name: `${model.name} scoring features`,
        business_case_role: "scoring_input" as const
      }],
      fitted_state_artifact_id: model.fitted_transform_artifact_id,
      evaluation: {
        ...sourceFe.evaluation,
        split_strategy: "predefined" as const,
        cross_validation: {
          ...sourceFe.evaluation.cross_validation,
          enabled: false
        }
      }
    };
    const feStep: WorkflowStepDefinition = {
      step_id: "fe_1",
      name: "Feature Engineering Transform",
      type: "feature_engineering",
      inputs: [{
        port_id: "scoring_input",
        source: { step_id: deStep.step_id, port_id: deStep.output_port_id }
      }],
      output_port_id: "scoring_input",
      additional_output_port_ids: [],
      config: { definition: feDefinition }
    };
    const scoringStep: WorkflowStepDefinition = {
      step_id: "scoring_1",
      name: "Batch Scoring",
      type: "scoring",
      inputs: [{
        port_id: "data",
        source: { step_id: feStep.step_id, port_id: feStep.output_port_id }
      }],
      output_port_id: "predictions",
      additional_output_port_ids: [],
      config: {
        definition: {
          ...emptyScoringDefinition(),
          purpose: "batch",
          model_artifact_id: model.id,
          row_id_column: sourceFe.row_id_column,
          target_column: "",
          dataset_name: `${model.name} batch predictions`,
          report_name: "Batch scoring"
        }
      }
    };
    setExpandedStepId(deStep.step_id);
    onChange({
      contract_version: "2.0",
      steps: [deStep, feStep, scoringStep],
      outputs: workflowOutputsForStep(scoringStep),
      parameters: {}
    });
  }

  function updateStep(index: number, step: WorkflowStepDefinition) {
    const steps = definition.steps.map((item, itemIndex) => itemIndex === index ? step : item);
    onChange({
      ...definition,
      steps,
      outputs: index === steps.length - 1
        ? workflowOutputsForStep(step)
        : definition.outputs
    });
  }

  function updateFeatureStep(
    index: number,
    step: Extract<WorkflowStepDefinition, { type: "feature_engineering" }>,
    nextDefinition: Extract<WorkflowStepDefinition, { type: "feature_engineering" }>["config"]["definition"]
  ) {
    const ports = featureEngineeringOutputPorts(nextDefinition);
    updateStep(index, {
      ...step,
      output_port_id: ports.primary,
      additional_output_port_ids: ports.additional,
      config: { definition: nextDefinition }
    });
  }

  function removeStep(index: number) {
    const removed = definition.steps[index];
    const remaining = definition.steps.filter((_, itemIndex) => itemIndex !== index);
    const last = remaining.at(-1);
    setExpandedStepId(last?.step_id ?? "");
    onChange({
      ...definition,
      steps: remaining,
      outputs: last
        ? workflowOutputsForStep(last)
        : [],
    });
  }

  return (
    <div className="workflow-editor">
      <div className="workflow-editor-heading">
        <div>
          <span className="builder-kicker">Pipeline workflow</span>
          <h3>High-level steps</h3>
          <p>
            Data Engineering can feed a fitted, reusable Feature Engineering step.
            Full datasets stay in the columnar execution layer.
          </p>
        </div>
        <div className="inline-actions">
          {pipelineType === "batch_scoring" && (
            <label className="compact-select">
              <span>Configure from model</span>
              <select value="" disabled={disabled}
                onChange={(event) => configureBatchScoring(event.target.value)}>
                <option value="">Choose scoring-ready model…</option>
                {scoringModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name} · {model.version}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button className="secondary-button" type="button" onClick={addDataEngineeringStep}
            disabled={disabled || definition.steps.length > 0}>
            <Plus size={15} /> Add Data Engineering
          </button>
          <button className="primary-button" type="button" onClick={addFeatureEngineeringStep}
            disabled={disabled || definition.steps.some((step) => step.type === "feature_engineering")}>
            <Plus size={15} /> Add Feature Engineering
          </button>
          <button className="secondary-button" type="button" onClick={addTrainingStep}
            disabled={disabled || !definition.steps.some((step) => step.type === "feature_engineering")
              || definition.steps.some((step) => step.type === "training")}>
            <Plus size={15} /> Add Training
          </button>
          <button className="secondary-button" type="button" onClick={addScoringStep}
            disabled={disabled || !definition.steps.some((step) => step.type === "training")
              || definition.steps.some((step) => step.type === "scoring")}>
            <Plus size={15} /> Add Test Scoring
          </button>
        </div>
      </div>

      <WorkflowDiagram
        definition={definition}
        selectedStepId={expandedStepId}
        disabled={disabled}
        onAddFirstStep={addDataEngineeringStep}
        onSelectStep={setExpandedStepId}
      />

      <div className="workflow-step-list">
        {definition.steps.map((step, index) => expandedStepId === step.step_id && (
          <article className="workflow-step selected" key={step.step_id}>
            <div className="workflow-step-summary">
              <div className="workflow-step-icon">
                {step.type === "data_engineering" ? <DatabaseZap size={20} />
                  : step.type === "feature_engineering" ? <Sparkles size={20} />
                    : step.type === "training" ? <Brain size={20} /> : <Calculator size={20} />}
              </div>
              <div className="workflow-step-copy">
                <span>SELECTED STEP · {step.step_id}</span>
                <input value={step.name} onChange={(event) => updateStep(index, {
                  ...step, name: event.target.value
                })} disabled={disabled} />
                <small>{step.type === "data_engineering"
                  ? `${step.config.definition.inputs.length} sources · ${step.config.definition.steps.length} blocks · ${step.config.definition.outputs.length} outputs`
                  : step.type === "feature_engineering"
                    ? `${step.config.definition.inputs.length} splits · ${step.config.definition.transformations.length} transforms · ${step.config.definition.outputs.length} outputs`
                    : step.type === "training"
                      ? `${step.config.definition.feature_columns.length} features · max ${step.config.definition.epochs} epochs${step.config.definition.early_stopping ? " · early stopping" : ""}`
                      : `model + data · ${step.config.definition.dataset_name}`}
                </small>
              </div>
              <button className="secondary-button" type="button" onClick={() => setExpandedStepId("")}>
                <Braces size={15} /> Close configuration
              </button>
              <button className="icon-button" type="button" onClick={() => removeStep(index)}
                disabled={disabled || index < definition.steps.length - 1}
                aria-label={`Remove ${step.name} step`}>
                <Trash2 size={16} />
              </button>
            </div>
            <div className="workflow-step-configuration">
              {step.type === "data_engineering" ? (
                <PipelineBuilder
                  definition={step.config.definition}
                  datasets={datasets}
                  dataAttachments={dataAttachments}
                  outputNameSuggestion={outputNameSuggestion}
                  disabled={disabled}
                  onChange={(nextDefinition) => updateStep(index, {
                    ...step, config: { definition: nextDefinition }
                  })}
                />
              ) : step.type === "feature_engineering" ? (
                <FeatureEngineeringBuilder
                  definition={step.config.definition}
                  datasets={datasets}
                  dataAttachments={dataAttachments}
                  upstreamDefinition={previousDataEngineeringDefinition(definition.steps, index)}
                  hasUpstream={step.inputs.length > 0}
                  disabled={disabled}
                  onChange={(nextDefinition) => updateFeatureStep(index, step, nextDefinition)}
                />
              ) : step.type === "training" ? (
                <TrainingBuilder
                  definition={step.config.definition}
                  defaults={modelingDefaults}
                  disabled={disabled}
                  onChange={(nextDefinition) => updateStep(index, {
                    ...step, config: { definition: nextDefinition }
                  })}
                />
              ) : (
                <ScoringBuilder
                  definition={step.config.definition}
                  defaults={modelingDefaults}
                  models={models}
                  disabled={disabled}
                  onChange={(nextDefinition) => updateStep(index, {
                    ...step, config: { definition: nextDefinition }
                  })}
                />
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function previousDataEngineeringDefinition(
  steps: WorkflowStepDefinition[],
  beforeIndex: number
): PipelineDefinition | undefined {
  for (let index = beforeIndex - 1; index >= 0; index -= 1) {
    const step = steps[index];
    if (step.type === "data_engineering") return step.config.definition;
  }
  return undefined;
}

const inferenceSafeDeTypes = new Set([
  "select_columns",
  "add_identifier",
  "rename_columns",
  "cast_columns",
  "derive_column",
  "map_categories"
]);

function isInferenceSafeModelPreparation(model: ModelArtifact) {
  const de = normalizePipelineDefinition(model.data_engineering_definition);
  const fe = normalizeFeatureEngineeringDefinition(model.feature_engineering_definition);
  return de.inputs.length > 0
    && de.outputs.length > 0
    && Boolean(fe.row_id_column)
    && de.steps.every((step) => (
      inferenceSafeDeTypes.has(step.type)
      && !(step.type === "add_identifier" && step.config.mode === "sequence")
      && (
        ["select_columns", "rename_columns", "cast_columns"].includes(step.type)
        || !containsValue(step.config, fe.target_column)
      )
    ));
}

function sanitizeInferenceConfig(
  type: string,
  config: Record<string, unknown>,
  targetColumn: string
) {
  if (!targetColumn) return config;
  if (type === "select_columns") {
    return {
      ...config,
      columns: Array.isArray(config.columns)
        ? config.columns.filter((column) => column !== targetColumn)
        : config.columns
    };
  }
  if (type === "rename_columns" || type === "cast_columns") {
    const field = type === "rename_columns" ? "renames" : "casts";
    const mapping = config[field] && typeof config[field] === "object"
      ? config[field] as Record<string, unknown>
      : {};
    return {
      ...config,
      [field]: Object.fromEntries(
        Object.entries(mapping).filter(
          ([source, target]) => source !== targetColumn && target !== targetColumn
        )
      )
    };
  }
  return config;
}

function containsValue(value: unknown, expected: string): boolean {
  if (!expected) return false;
  if (Array.isArray(value)) return value.some((item) => containsValue(item, expected));
  if (value && typeof value === "object") {
    return Object.entries(value).some(
      ([key, item]) => key === expected || containsValue(item, expected)
    );
  }
  return value === expected;
}
