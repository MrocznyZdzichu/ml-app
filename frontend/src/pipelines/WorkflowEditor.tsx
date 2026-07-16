import { Activity, Braces, Brain, Calculator, DatabaseZap, Plus, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCase,
  BusinessCaseDataAttachment,
  DataAsset,
  DatasetColumn,
  ModelArtifact,
  Pipeline,
  PipelineRun,
  PipelineVersion
} from "../api/client";
import { FeatureEngineeringBuilder, inferFeatureRecipeColumns } from "./FeatureEngineeringBuilder";
import {
  emptyFeatureEngineeringDefinition,
  normalizeFeatureEngineeringDefinition
} from "./featureEngineeringContract";
import { PipelineBuilder } from "./PipelineBuilder";
import {
  emptyPipelineDefinition,
  normalizePipelineDefinition,
  rewireSequentialFlow
} from "./pipelineContract";
import type { PipelineDefinition } from "./pipelineContract";
import { datasetColumns, inferPipelineOutputColumns, inputDatasetIds } from "./pipelineSchema";
import type { WorkflowDefinition, WorkflowStepDefinition } from "./workflowContract";
import { WorkflowDiagram } from "./WorkflowDiagram";
import { ScoringBuilder, TrainingBuilder } from "./ModelingBuilders";
import { MonitoringBuilder } from "./MonitoringBuilder";
import { emptyMonitoringDefinition } from "./monitoringContract";
import {
  deriveModelingDefaults,
  emptyScoringDefinition,
  emptyTrainingDefinition,
  scoringWithDefaults,
  trainingWithDefaults
} from "./modelingContract";
import {
  featureEngineeringOutputPorts,
  normalizeWorkflowDefinition,
  workflowTemplateDefinition,
  workflowOutputsForStep
} from "./workflowContract";

export type { WorkflowDefinition, WorkflowStepDefinition } from "./workflowContract";
export { emptyWorkflowDefinition, normalizeWorkflowDefinition } from "./workflowContract";

export function WorkflowEditor({
  definition,
  businessCase,
  datasets,
  models,
  pipelines,
  dataAttachments,
  pipelineId,
  pipelineType,
  outputNameSuggestion,
  disabled,
  onChange
}: {
  definition: WorkflowDefinition;
  businessCase?: BusinessCase;
  datasets: DataAsset[];
  models: ModelArtifact[];
  pipelines: Pipeline[];
  dataAttachments: BusinessCaseDataAttachment[];
  pipelineId?: string;
  pipelineType: string;
  outputNameSuggestion?: string;
  disabled: boolean;
  onChange: (definition: WorkflowDefinition) => void;
}) {
  const [expandedStepId, setExpandedStepId] = useState(definition.steps[0]?.step_id ?? "");
  const [schemaCache, setSchemaCache] = useState<Record<string, DatasetColumn[]>>({});
  const [isInferenceDialogOpen, setIsInferenceDialogOpen] = useState(false);
  const [sourcePipelineId, setSourcePipelineId] = useState("");
  const [sourceVersions, setSourceVersions] = useState<PipelineVersion[]>([]);
  const [sourceVersionId, setSourceVersionId] = useState("");
  const [sourceModelId, setSourceModelId] = useState("");
  const [isMonitoringInferenceOpen, setIsMonitoringInferenceOpen] = useState(false);
  const [monitoringPipelineId, setMonitoringPipelineId] = useState("");
  const [monitoringVersions, setMonitoringVersions] = useState<PipelineVersion[]>([]);
  const [monitoringVersionId, setMonitoringVersionId] = useState("");
  const [monitoringRuns, setMonitoringRuns] = useState<PipelineRun[]>([]);
  const [monitoringRunId, setMonitoringRunId] = useState("");
  const [monitoringDatasetId, setMonitoringDatasetId] = useState("");
  const [isDataEngineeringInferenceOpen, setIsDataEngineeringInferenceOpen] = useState(false);
  const [dataEngineeringSourcePipelineId, setDataEngineeringSourcePipelineId] = useState("");
  const [dataEngineeringSourceVersions, setDataEngineeringSourceVersions] = useState<PipelineVersion[]>([]);
  const [dataEngineeringSourceVersionId, setDataEngineeringSourceVersionId] = useState("");
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
  const isAutoMLTemplate = definition.parameters.template === "automl" || pipelineType === "automl";
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
  );
  const sourcePipelines = pipelines.filter(
    (pipeline) =>
      pipeline.business_case_id === businessCase?.id
      && scoringModels.some((model) => model.pipeline_id === pipeline.id)
  );
  const dataEngineeringSourcePipelines = pipelines.filter(
    (pipeline) =>
      pipeline.business_case_id === businessCase?.id
      && pipeline.type === "training"
      && pipeline.id !== pipelineId
  );
  const availableDataEngineeringSourceVersions = dataEngineeringSourceVersions.filter(
    (version) =>
      version.business_case_id === businessCase?.id
      && Boolean(dataEngineeringStepFromVersion(version))
  );
  const availableSourceVersions = sourceVersions.filter(
    (version) =>
      version.status === "published"
      && scoringModels.some(
        (model) =>
          model.pipeline_id === sourcePipelineId
          && model.pipeline_version_id === version.id
      )
  );
  const versionModels = scoringModels.filter(
    (model) =>
      model.pipeline_id === sourcePipelineId
      && model.pipeline_version_id === sourceVersionId
  );
  const monitoringSourcePipelines = pipelines.filter(
    (pipeline) =>
      pipeline.business_case_id === businessCase?.id
      && pipeline.type === "batch_scoring"
  );
  const availableMonitoringVersions = monitoringVersions.filter(
    (version) => version.status === "published"
  );
  const availableMonitoringRuns = monitoringRuns.filter(
    (run) =>
      run.status === "succeeded"
      && !run.is_dry_run
      && run.pipeline_version_id === monitoringVersionId
      && run.output_manifest.some(
        (output) => output.artifact_type === "prediction_dataset" && output.dataset_id
      )
  );
  const selectedMonitoringRun = availableMonitoringRuns.find(
    (run) => run.id === monitoringRunId
  );
  const monitoringPredictionOutputs = selectedMonitoringRun?.output_manifest.filter(
    (output) => output.artifact_type === "prediction_dataset" && output.dataset_id
  ) ?? [];

  useEffect(() => {
    let changed = false;
    const steps = definition.steps.map((step) => {
      if (step.type === "training" || step.type === "automl") {
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
    if (!upstream || upstream.type !== "data_engineering") return;
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
    addModelingStep("training");
  }

  function addAutoMLStep() {
    addModelingStep("automl");
  }

  function addModelingStep(type: "training" | "automl") {
    if (definition.steps.some((step) => step.type === "training" || step.type === "automl")) return;
    const feature = [...definition.steps].reverse().find((step) => step.type === "feature_engineering");
    if (!feature || definition.steps.at(-1)?.step_id !== feature.step_id) return;
    const trainingDefinition = trainingWithDefaults(modelingDefaults, emptyTrainingDefinition());
    const step: WorkflowStepDefinition = {
      step_id: type === "automl" ? "automl_1" : "training_1",
      name: type === "automl" ? "AutoML" : "Model Training",
      type,
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
      config: { definition: type === "automl"
        ? {
            ...trainingDefinition,
            early_stopping: false,
            optimization: { ...trainingDefinition.optimization, mode: "automl" }
          }
        : trainingDefinition }
    } as WorkflowStepDefinition;
    setExpandedStepId(step.step_id);
    onChange({ ...definition, steps: [...definition.steps, step], outputs: workflowOutputsForStep(step) });
  }

  function addScoringStep() {
    if (definition.steps.some((step) => step.type === "scoring")) return;
    const feature = definition.steps.find((step) => step.type === "feature_engineering");
    const training = definition.steps.find(
      (step) => step.type === "training" || step.type === "automl"
    );
    if (!feature || !training || definition.steps.at(-1)?.step_id !== training.step_id) return;
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

  function addMonitoringStep() {
    if (definition.steps.some((step) => step.type === "monitoring")) return;
    const scoring = definition.steps.find((step) => step.type === "scoring");
    if (!scoring || definition.steps.at(-1)?.step_id !== scoring.step_id) return;
    const scoringDefinition = scoring.config.definition;
    const step: WorkflowStepDefinition = {
      step_id: "monitoring_1",
      name: "Model Monitoring",
      type: "monitoring",
      inputs: [{
        port_id: "data",
        source: { step_id: scoring.step_id, port_id: scoring.output_port_id }
      }],
      output_port_id: "performance_report",
      additional_output_port_ids: [],
      config: {
        definition: {
          ...emptyMonitoringDefinition(),
          row_id_column: scoringDefinition.row_id_column || modelingDefaults.row_id_column || "row_id",
          target_column: scoringDefinition.target_column || modelingDefaults.target_column || "target",
          prediction_column: scoringDefinition.prediction_column,
          problem_type: modelingDefaults.problem_type,
          report_name: `${scoringDefinition.report_name || "Model"} monitoring`
        }
      }
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
    const reusableSteps = sourceDe.steps
      .filter((step) => isReusableInferenceStep(step.type, step.config, targetColumn))
      .map((step) => ({
        ...step,
        config: sanitizeInferenceConfig(step.type, step.config, targetColumn)
      }));
    const sourceOutput = sourceDe.outputs[0];
    const outputContract = sourceOutput?.data_contract
      ? {
          ...sourceOutput.data_contract,
          columns: sourceOutput.data_contract.columns.filter(
            (column) => column.name !== targetColumn
          )
        }
      : undefined;
    const deDefinition = rewireSequentialFlow({
      ...sourceDe,
      inputs: [{
        ...sourceDe.inputs[0],
        input_id: "scoring_input",
        dataset_id: "",
        version_policy: "select_at_run_any"
      }],
      steps: reusableSteps,
      outputs: [{
        ...(sourceOutput ?? {
          output_id: "scoring_prepared",
          input: { node_id: "scoring_input", port_id: "out" },
          write_mode: "replace"
        }),
        output_id: "scoring_prepared",
        materialization: "temporary",
        dataset_name: `${model.name} scoring-ready data`,
        business_case_role: "scoring_input",
        data_contract: outputContract?.columns.length ? outputContract : undefined
      }]
    } as PipelineDefinition);
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
      parameters: {
        template: "batch_scoring",
        inferred_from: {
          pipeline_id: model.pipeline_id,
          pipeline_version_id: model.pipeline_version_id,
          pipeline_run_id: model.pipeline_run_id,
          model_artifact_id: model.id,
          fitted_transform_artifact_id: model.fitted_transform_artifact_id
        }
      }
    });
    setIsInferenceDialogOpen(false);
    setSourceModelId("");
  }

  async function selectSourcePipeline(pipelineId: string) {
    setSourcePipelineId(pipelineId);
    setSourceVersionId("");
    setSourceModelId("");
    try {
      setSourceVersions(
        pipelineId
          ? await api.listPipelineVersions(pipelineId)
          : []
      );
    } catch {
      setSourceVersions([]);
    }
  }

  async function selectDataEngineeringSourcePipeline(pipelineId: string) {
    setDataEngineeringSourcePipelineId(pipelineId);
    setDataEngineeringSourceVersionId("");
    try {
      setDataEngineeringSourceVersions(
        pipelineId
          ? await api.listPipelineVersions(pipelineId)
          : []
      );
    } catch {
      setDataEngineeringSourceVersions([]);
    }
  }

  function inferDataEngineering() {
    const sourcePipeline = dataEngineeringSourcePipelines.find(
      (pipeline) => pipeline.id === dataEngineeringSourcePipelineId
    );
    const sourceVersion = availableDataEngineeringSourceVersions.find(
      (version) => version.id === dataEngineeringSourceVersionId
    );
    const sourceStep = sourceVersion ? dataEngineeringStepFromVersion(sourceVersion) : undefined;
    const targetIndex = definition.steps.findIndex((step) => step.type === "data_engineering");
    if (!sourcePipeline || !sourceVersion || !sourceStep || targetIndex < 0) return;
    const targetStep = definition.steps[targetIndex];
    if (targetStep.type !== "data_engineering") return;
    const nextStep: WorkflowStepDefinition = {
      ...targetStep,
      config: {
        definition: normalizePipelineDefinition(sourceStep.config.definition)
      }
    };
    const steps = definition.steps.map((step, index) => index === targetIndex ? nextStep : step);
    setExpandedStepId(targetStep.step_id);
    onChange({
      ...definition,
      steps,
      parameters: {
        ...definition.parameters,
        data_engineering_inferred_from: {
          pipeline_id: sourcePipeline.id,
          pipeline_name: sourcePipeline.name,
          pipeline_version_id: sourceVersion.id,
          pipeline_version_number: sourceVersion.version_number,
          pipeline_version_status: sourceVersion.status,
          definition_hash: sourceVersion.definition_hash,
          source_step_id: sourceStep.step_id
        }
      }
    });
    setIsDataEngineeringInferenceOpen(false);
  }

  async function selectMonitoringPipeline(pipelineId: string) {
    setMonitoringPipelineId(pipelineId);
    setMonitoringVersionId("");
    setMonitoringRunId("");
    setMonitoringDatasetId("");
    try {
      const [versionItems, runItems] = pipelineId
        ? await Promise.all([
            api.listPipelineVersions(pipelineId),
            api.listPipelineRuns(pipelineId)
          ])
        : [[], []];
      setMonitoringVersions(versionItems);
      setMonitoringRuns(runItems);
    } catch {
      setMonitoringVersions([]);
      setMonitoringRuns([]);
    }
  }

  function configureMonitoringFromRun() {
    const run = monitoringRuns.find((item) => item.id === monitoringRunId);
    const prediction = run?.output_manifest.find(
      (output) =>
        output.artifact_type === "prediction_dataset"
        && output.dataset_id === monitoringDatasetId
    );
    if (!run || !prediction?.dataset_id) return;
    const template = workflowTemplateDefinition("monitoring");
    const process = template.steps.find(
      (step): step is Extract<WorkflowStepDefinition, { type: "data_engineering" }> =>
        step.type === "data_engineering"
    );
    const report = template.steps.find(
      (step): step is Extract<WorkflowStepDefinition, { type: "monitoring" }> =>
        step.type === "monitoring"
    );
    if (!process || !report) return;
    const scoreContract = prediction.score_contract ?? {};
    const problemType = scoreContract.problem_type === "regression"
      ? "regression"
      : Array.isArray(scoreContract.classes) && scoreContract.classes.length > 2
        ? "multiclass_classification"
        : "binary_classification";
    const rowIdColumn = prediction.row_id_column
      ?? prediction.schema?.find(
        (column) => ![
          prediction.prediction_column ?? "prediction",
          "prediction_score",
          "positive_class_probability"
        ].includes(column.name)
      )?.name
      ?? "row_id";
    const predictionColumn = prediction.prediction_column ?? "prediction";
    const processDefinition = process.config.definition;
    process.config.definition = {
      ...processDefinition,
      inputs: processDefinition.inputs.map((input) =>
        input.input_id === "predictions"
          ? {
              ...input,
              dataset_id: prediction.dataset_id!,
              version_policy: "pinned" as const
            }
          : input
      ),
      steps: processDefinition.steps.map((step) =>
        step.type === "join"
          ? {
              ...step,
              config: {
                ...step.config,
                keys: [{ left: rowIdColumn, right: rowIdColumn }]
              }
            }
          : step
      )
    };
    report.config.definition = {
      ...report.config.definition,
      row_id_column: rowIdColumn,
      prediction_column: predictionColumn,
      problem_type: problemType
    };
    setExpandedStepId(process.step_id);
    onChange({
      ...template,
      steps: [process, report],
      parameters: {
        ...template.parameters,
        inferred_from: {
          pipeline_id: monitoringPipelineId,
          pipeline_version_id: monitoringVersionId,
          pipeline_run_id: run.id,
          prediction_dataset_id: prediction.dataset_id,
          prediction_artifact_id: prediction.artifact_id ?? ""
        }
      }
    });
    setIsMonitoringInferenceOpen(false);
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

  const lastStep = definition.steps.at(-1);
  const hasDataEngineering = definition.steps.some((step) => step.type === "data_engineering");
  const hasFeatureEngineering = definition.steps.some((step) => step.type === "feature_engineering");
  const hasModeling = definition.steps.some(
    (step) => step.type === "training" || step.type === "automl"
  );
  const hasScoring = definition.steps.some((step) => step.type === "scoring");
  const hasMonitoring = definition.steps.some((step) => step.type === "monitoring");
  const canAddDataEngineering = definition.steps.length === 0;
  const canAddFeatureEngineering = lastStep?.type === "data_engineering" && !hasFeatureEngineering;
  const canAddModeling = lastStep?.type === "feature_engineering" && !hasModeling;
  const canAddScoring = (lastStep?.type === "training" || lastStep?.type === "automl") && !hasScoring;
  const canAddMonitoring = lastStep?.type === "scoring" && !hasMonitoring;
  const recommendedStep: WorkflowStepDefinition["type"] | null = !hasDataEngineering
    ? "data_engineering"
    : !hasFeatureEngineering
      ? "feature_engineering"
      : !hasModeling
        ? (isAutoMLTemplate ? "automl" : "training")
        : !hasScoring
          ? "scoring"
          : !hasMonitoring
            ? "monitoring"
            : null;
  const buttonClass = (type: WorkflowStepDefinition["type"]) =>
    recommendedStep === type ? "primary-button" : "secondary-button";

  return (
    <div className="workflow-editor">
      <div className="workflow-editor-heading">
        <div>
          <span className="builder-kicker">Pipeline workflow</span>
          <h3>High-level steps</h3>
          <p>
            {pipelineType === "batch_scoring"
              ? "Infer an editable DE → fitted FE → Batch Scoring workflow from one immutable training result."
              : pipelineType === "monitoring"
                ? "Join immutable predictions with actuals and calculate full-scope model performance."
                : pipelineType === "custom"
                  ? "Compose the standard MLOps lifecycle: DE → FE → Training or AutoML → Scoring → Monitoring."
                  : "Build the training lifecycle from Data Engineering through holdout Test Scoring."}
          </p>
        </div>
        <div className="inline-actions">
          {isAutoMLTemplate && (
            <button className="primary-button" type="button" disabled={disabled}
              onClick={() => setIsDataEngineeringInferenceOpen(true)}>
              <DatabaseZap size={15} /> Infer Data Engineering
            </button>
          )}
          {pipelineType === "batch_scoring" && (
            <button className="primary-button" type="button" disabled={disabled}
              onClick={() => setIsInferenceDialogOpen(true)}>
              <Sparkles size={15} /> Infer from training pipeline
            </button>
          )}
          {pipelineType === "monitoring" && (
            <button className="primary-button" type="button" disabled={disabled}
              onClick={() => setIsMonitoringInferenceOpen(true)}>
              <Sparkles size={15} /> Infer from scoring run
            </button>
          )}
          {pipelineType !== "batch_scoring" && pipelineType !== "monitoring" && (
            <>
              <button className={buttonClass("data_engineering")} type="button" onClick={addDataEngineeringStep}
                disabled={disabled || !canAddDataEngineering}>
                <Plus size={15} /> Add Data Engineering
              </button>
              <button className={buttonClass("feature_engineering")} type="button" onClick={addFeatureEngineeringStep}
                disabled={disabled || !canAddFeatureEngineering}>
                <Plus size={15} /> Add Feature Engineering
              </button>
              <button className={buttonClass("training")} type="button" onClick={addTrainingStep}
                disabled={disabled || !canAddModeling}>
                <Plus size={15} /> Add Training
              </button>
              <button className={buttonClass("automl")} type="button" onClick={addAutoMLStep}
                disabled={disabled || !canAddModeling}>
                <Plus size={15} /> Add AutoML
              </button>
              <button className={buttonClass("scoring")} type="button" onClick={addScoringStep}
                disabled={disabled || !canAddScoring}>
                <Plus size={15} /> Add Test Scoring
              </button>
              <button className={buttonClass("monitoring")} type="button" onClick={addMonitoringStep}
                disabled={disabled || !canAddMonitoring}>
                <Plus size={15} /> Add Monitoring
              </button>
            </>
          )}
        </div>
      </div>

      {pipelineType === "batch_scoring"
        && definition.steps.some((step) => step.type === "training") && (
          <div className="form-warning">
            This Batch Scoring pipeline still contains training lifecycle steps.
            Use “Infer from training pipeline” to replace it with DE, fitted FE and Batch Scoring.
          </div>
        )}

      {isAutoMLTemplate && Boolean(definition.parameters.data_engineering_inferred_from) && (
        <div className="form-note">
          Data Engineering was copied from {String(
            recordValue(definition.parameters.data_engineering_inferred_from).pipeline_name ?? "a training pipeline"
          )}, v{String(
            recordValue(definition.parameters.data_engineering_inferred_from).pipeline_version_number ?? "?"
          )}. The copied step is independent and remains fully editable.
        </div>
      )}

      <WorkflowDiagram
        definition={definition}
        selectedStepId={expandedStepId}
        disabled={disabled}
        onAddFirstStep={() => pipelineType === "batch_scoring"
          ? setIsInferenceDialogOpen(true)
          : pipelineType === "monitoring"
            ? undefined
            : addDataEngineeringStep()}
        onSelectStep={setExpandedStepId}
      />

      <div className="workflow-step-list">
        {definition.steps.map((step, index) => expandedStepId === step.step_id && (
          <article className="workflow-step selected" key={step.step_id}>
            <div className="workflow-step-summary">
              <div className="workflow-step-icon">
                {step.type === "data_engineering" ? <DatabaseZap size={20} />
                  : step.type === "feature_engineering" ? <Sparkles size={20} />
                    : step.type === "training" || step.type === "automl" ? <Brain size={20} />
                      : step.type === "monitoring" ? <Activity size={20} />
                        : <Calculator size={20} />}
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
                    : step.type === "training" || step.type === "automl"
                      ? step.type === "automl"
                        ? `${step.config.definition.optimization.candidate_algorithms.length || "curated"} candidate families · max ${step.config.definition.optimization.max_trials} trials`
                        : `${step.config.definition.feature_columns.length} features · max ${step.config.definition.epochs} epochs${step.config.definition.early_stopping ? " · early stopping" : ""}`
                      : step.type === "monitoring"
                        ? `predictions + actuals · ${step.config.definition.report_name}`
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
                  fittedStateLocked={pipelineType === "batch_scoring"}
                  disabled={disabled}
                  onChange={(nextDefinition) => updateFeatureStep(index, step, nextDefinition)}
                />
              ) : step.type === "training" || step.type === "automl" ? (
                <TrainingBuilder
                  definition={step.config.definition}
                  defaults={modelingDefaults}
                  disabled={disabled}
                  onChange={(nextDefinition) => updateStep(index, {
                    ...step, config: { definition: step.type === "automl"
                      ? { ...nextDefinition, optimization: { ...nextDefinition.optimization, mode: "automl" } }
                      : nextDefinition }
                  })}
                />
              ) : step.type === "monitoring" ? (
                <MonitoringBuilder
                  definition={step.config.definition}
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
      {isInferenceDialogOpen && (
        <BatchInferenceDialog
          pipelines={sourcePipelines}
          versions={availableSourceVersions}
          models={versionModels}
          sourcePipelineId={sourcePipelineId}
          sourceVersionId={sourceVersionId}
          sourceModelId={sourceModelId}
          onPipelineChange={(pipelineId) => void selectSourcePipeline(pipelineId)}
          onVersionChange={(versionId) => {
            setSourceVersionId(versionId);
            setSourceModelId("");
          }}
          onModelChange={setSourceModelId}
          onClose={() => setIsInferenceDialogOpen(false)}
          onApply={() => configureBatchScoring(sourceModelId)}
        />
      )}
      {isMonitoringInferenceOpen && (
        <MonitoringInferenceDialog
          pipelines={monitoringSourcePipelines}
          versions={availableMonitoringVersions}
          runs={availableMonitoringRuns}
          outputs={monitoringPredictionOutputs}
          pipelineId={monitoringPipelineId}
          versionId={monitoringVersionId}
          runId={monitoringRunId}
          datasetId={monitoringDatasetId}
          onPipelineChange={(pipelineId) => void selectMonitoringPipeline(pipelineId)}
          onVersionChange={(versionId) => {
            setMonitoringVersionId(versionId);
            setMonitoringRunId("");
            setMonitoringDatasetId("");
          }}
          onRunChange={(runId) => {
            setMonitoringRunId(runId);
            const run = monitoringRuns.find((item) => item.id === runId);
            const output = run?.output_manifest.find(
              (item) => item.artifact_type === "prediction_dataset" && item.dataset_id
            );
            setMonitoringDatasetId(output?.dataset_id ?? "");
          }}
          onDatasetChange={setMonitoringDatasetId}
          onClose={() => setIsMonitoringInferenceOpen(false)}
          onApply={configureMonitoringFromRun}
        />
      )}
      {isDataEngineeringInferenceOpen && (
        <DataEngineeringInferenceDialog
          pipelines={dataEngineeringSourcePipelines}
          versions={availableDataEngineeringSourceVersions}
          pipelineId={dataEngineeringSourcePipelineId}
          versionId={dataEngineeringSourceVersionId}
          onPipelineChange={(pipelineId) => void selectDataEngineeringSourcePipeline(pipelineId)}
          onVersionChange={setDataEngineeringSourceVersionId}
          onClose={() => setIsDataEngineeringInferenceOpen(false)}
          onApply={inferDataEngineering}
        />
      )}
    </div>
  );
}

function dataEngineeringStepFromVersion(version: PipelineVersion) {
  return normalizeWorkflowDefinition(version.definition).steps.find(
    (step): step is Extract<WorkflowStepDefinition, { type: "data_engineering" }> =>
      step.type === "data_engineering"
  );
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function DataEngineeringInferenceDialog({
  pipelines,
  versions,
  pipelineId,
  versionId,
  onPipelineChange,
  onVersionChange,
  onClose,
  onApply
}: {
  pipelines: Pipeline[];
  versions: PipelineVersion[];
  pipelineId: string;
  versionId: string;
  onPipelineChange: (pipelineId: string) => void;
  onVersionChange: (versionId: string) => void;
  onClose: () => void;
  onApply: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-dialog form-panel inference-source-dialog" role="dialog"
        aria-modal="true" aria-label="Infer Data Engineering"
        onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="builder-kicker">AutoML template</span>
            <h2>Infer Data Engineering</h2>
            <p>Copy the DE definition from one explicit version of another training pipeline in this Business Case.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose}
            aria-label="Close Data Engineering inference"><X size={17} /></button>
        </div>
        <label>Training pipeline
          <select value={pipelineId} onChange={(event) => onPipelineChange(event.target.value)}>
            <option value="">Choose pipeline…</option>
            {pipelines.map((pipeline) => (
              <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>
            ))}
          </select>
          {!pipelines.length && (
            <small>No pipeline with purpose “training” exists in this Business Case.</small>
          )}
        </label>
        <label>Pipeline version
          <select value={versionId} disabled={!pipelineId}
            onChange={(event) => onVersionChange(event.target.value)}>
            <option value="">Choose version…</option>
            {versions.map((version) => (
              <option key={version.id} value={version.id}>
                v{version.version_number} · {version.status} · {version.definition_hash.slice(0, 10)}
              </option>
            ))}
          </select>
          {pipelineId && !versions.length && (
            <small>No version of this pipeline contains a Data Engineering step.</small>
          )}
        </label>
        <div className="form-warning">
          The current AutoML Data Engineering configuration will be replaced. Downstream step IDs and connections
          stay unchanged, and the copied definition can be edited immediately afterward.
        </div>
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>Cancel</button>
          <button className="primary-button" type="button" onClick={onApply}
            disabled={!pipelineId || !versionId}>
            <DatabaseZap size={15} /> Copy Data Engineering
          </button>
        </div>
      </section>
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

function MonitoringInferenceDialog({
  pipelines,
  versions,
  runs,
  outputs,
  pipelineId,
  versionId,
  runId,
  datasetId,
  onPipelineChange,
  onVersionChange,
  onRunChange,
  onDatasetChange,
  onClose,
  onApply
}: {
  pipelines: Pipeline[];
  versions: PipelineVersion[];
  runs: PipelineRun[];
  outputs: PipelineRun["output_manifest"];
  pipelineId: string;
  versionId: string;
  runId: string;
  datasetId: string;
  onPipelineChange: (pipelineId: string) => void;
  onVersionChange: (versionId: string) => void;
  onRunChange: (runId: string) => void;
  onDatasetChange: (datasetId: string) => void;
  onClose: () => void;
  onApply: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-dialog form-panel inference-source-dialog" role="dialog"
        aria-modal="true" aria-label="Infer Monitoring pipeline"
        onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Monitoring template</span>
            <h2>Infer from scoring run</h2>
            <p>Pin one immutable prediction artifact. No “latest” result is selected implicitly.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose}
            aria-label="Close monitoring inference"><X size={17} /></button>
        </div>
        <label>Batch scoring pipeline
          <select value={pipelineId} onChange={(event) => onPipelineChange(event.target.value)}>
            <option value="">Choose pipeline…</option>
            {pipelines.map((pipeline) => (
              <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>
            ))}
          </select>
          {!pipelines.length && (
            <small>No Batch Scoring pipeline exists in this Business Case.</small>
          )}
        </label>
        <label>Published pipeline version
          <select value={versionId} disabled={!pipelineId}
            onChange={(event) => onVersionChange(event.target.value)}>
            <option value="">Choose version…</option>
            {versions.map((version) => (
              <option key={version.id} value={version.id}>
                v{version.version_number} · {version.definition_hash.slice(0, 10)}
              </option>
            ))}
          </select>
        </label>
        <label>Successful scoring run
          <select value={runId} disabled={!versionId}
            onChange={(event) => onRunChange(event.target.value)}>
            <option value="">Choose run…</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.id.slice(0, 8)} · {run.output_row_count ?? "?"} rows · {run.finished_at ?? run.created_at}
              </option>
            ))}
          </select>
        </label>
        <label>Prediction artifact
          <select value={datasetId} disabled={!runId}
            onChange={(event) => onDatasetChange(event.target.value)}>
            <option value="">Choose prediction dataset…</option>
            {outputs.map((output) => (
              <option key={output.artifact_id ?? output.dataset_id} value={output.dataset_id}>
                {output.dataset_name ?? output.output_id} · {output.row_count ?? "?"} rows
              </option>
            ))}
          </select>
          <small>
            The exact dataset version, scoring pipeline version and run are saved for audit.
          </small>
        </label>
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>Cancel</button>
          <button className="primary-button" type="button" onClick={onApply}
            disabled={!pipelineId || !versionId || !runId || !datasetId}>
            <Sparkles size={15} /> Create monitoring draft
          </button>
        </div>
      </section>
    </div>
  );
}

function BatchInferenceDialog({
  pipelines,
  versions,
  models,
  sourcePipelineId,
  sourceVersionId,
  sourceModelId,
  onPipelineChange,
  onVersionChange,
  onModelChange,
  onClose,
  onApply
}: {
  pipelines: Pipeline[];
  versions: PipelineVersion[];
  models: ModelArtifact[];
  sourcePipelineId: string;
  sourceVersionId: string;
  sourceModelId: string;
  onPipelineChange: (pipelineId: string) => void;
  onVersionChange: (versionId: string) => void;
  onModelChange: (modelId: string) => void;
  onClose: () => void;
  onApply: () => void;
}) {
  const selectedModel = models.find((model) => model.id === sourceModelId);
  const readiness = selectedModel
    ? batchInferenceReadiness(selectedModel)
    : null;
  return (
    <div className="modal-backdrop" role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-dialog form-panel inference-source-dialog" role="dialog"
        aria-modal="true" aria-label="Infer Batch Scoring pipeline"
        onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Batch scoring template</span>
            <h2>Infer from training pipeline</h2>
            <p>Choose one immutable training result. The generated draft remains editable.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose}
            aria-label="Close inference source"><X size={17} /></button>
        </div>
        <label>Training pipeline
          <select value={sourcePipelineId}
            onChange={(event) => onPipelineChange(event.target.value)}>
            <option value="">Choose pipeline…</option>
            {pipelines.map((pipeline) => (
              <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>
            ))}
          </select>
          {!pipelines.length && (
            <small>No training pipeline in this Business Case has a persisted model and fitted FE state.</small>
          )}
        </label>
        <label>Published pipeline version
          <select value={sourceVersionId} disabled={!sourcePipelineId}
            onChange={(event) => onVersionChange(event.target.value)}>
            <option value="">Choose version…</option>
            {versions.map((version) => (
              <option key={version.id} value={version.id}>
                v{version.version_number} · {version.definition_hash.slice(0, 10)}
              </option>
            ))}
          </select>
          {sourcePipelineId && !versions.length && (
            <small>No published version of this pipeline has a scoring-ready model result.</small>
          )}
        </label>
        <label>Concrete model result
          <select value={sourceModelId} disabled={!sourceVersionId}
            onChange={(event) => onModelChange(event.target.value)}>
            <option value="">Choose model/run…</option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name} · {model.version} · run {model.pipeline_run_id.slice(0, 8)}
              </option>
            ))}
          </select>
          <small>
            Pipeline version alone is not enough: this pins the exact model and fitted transform produced by one run.
          </small>
        </label>
        {readiness && (
          <div className={readiness.compatible ? "inference-summary" : "form-warning"}>
            <strong>{readiness.compatible ? "Ready to infer" : "Cannot infer safely"}</strong>
            <span>{readiness.message}</span>
          </div>
        )}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>Cancel</button>
          <button className="primary-button" type="button" onClick={onApply}
            disabled={!selectedModel || !readiness?.compatible}>
            <Sparkles size={15} /> Create scoring draft
          </button>
        </div>
      </section>
    </div>
  );
}

const inferenceSafeDeTypes = new Set([
  "select_columns",
  "add_identifier",
  "rename_columns",
  "cast_columns",
  "derive_column",
  "map_categories"
]);

function batchInferenceReadiness(model: ModelArtifact) {
  const de = normalizePipelineDefinition(model.data_engineering_definition);
  const fe = normalizeFeatureEngineeringDefinition(model.feature_engineering_definition);
  if (!model.fitted_transform_artifact_id) {
    return { compatible: false, message: "The selected run has no fitted FE artifact." };
  }
  if (de.inputs.length !== 1 || !de.outputs.length) {
    return {
      compatible: false,
      message: "Automatic inference currently requires a single-source training DE. Configure joins manually."
    };
  }
  if (!fe.row_id_column) {
    return { compatible: false, message: "The source FE contract has no stable row ID." };
  }
  const reusable = de.steps.filter(
    (step) => isReusableInferenceStep(step.type, step.config, fe.target_column)
  ).length;
  const omitted = de.steps.length - reusable;
  return {
    compatible: true,
    message: (
      `${reusable} inference-safe DE block${reusable === 1 ? "" : "s"} will be copied; `
      + `${omitted} training-only block${omitted === 1 ? "" : "s"} will be omitted. `
      + "The exact FE recipe, fitted state and model artifact will be pinned."
    )
  };
}

function isReusableInferenceStep(
  type: string,
  config: Record<string, unknown>,
  targetColumn: string
) {
  if (!inferenceSafeDeTypes.has(type)) return false;
  if (type === "add_identifier" && config.mode === "sequence") return false;
  if (!["select_columns", "rename_columns", "cast_columns"].includes(type)
    && containsValue(config, targetColumn)) return false;
  const sanitized = sanitizeInferenceConfig(type, config, targetColumn);
  if (type === "select_columns") {
    return Array.isArray(sanitized.columns) && sanitized.columns.length > 0;
  }
  if (type === "rename_columns" || type === "cast_columns") {
    const field = type === "rename_columns" ? "renames" : "casts";
    return Boolean(
      sanitized[field]
      && typeof sanitized[field] === "object"
      && Object.keys(sanitized[field] as Record<string, unknown>).length
    );
  }
  return true;
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
