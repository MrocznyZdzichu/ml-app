import { Braces, DatabaseZap, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";

import type { BusinessCaseDataAttachment, DataAsset } from "../api/client";
import { FeatureEngineeringBuilder } from "./FeatureEngineeringBuilder";
import { emptyFeatureEngineeringDefinition } from "./featureEngineeringContract";
import { PipelineBuilder } from "./PipelineBuilder";
import { emptyPipelineDefinition } from "./pipelineContract";
import type { PipelineDefinition } from "./pipelineContract";
import type { WorkflowDefinition, WorkflowStepDefinition } from "./workflowContract";
import { WorkflowDiagram } from "./WorkflowDiagram";
import {
  featureEngineeringOutputPorts,
  workflowOutputsForStep
} from "./workflowContract";

export type { WorkflowDefinition, WorkflowStepDefinition } from "./workflowContract";
export { emptyWorkflowDefinition, normalizeWorkflowDefinition } from "./workflowContract";

export function WorkflowEditor({
  definition,
  datasets,
  dataAttachments,
  outputNameSuggestion,
  disabled,
  onChange
}: {
  definition: WorkflowDefinition;
  datasets: DataAsset[];
  dataAttachments: BusinessCaseDataAttachment[];
  outputNameSuggestion?: string;
  disabled: boolean;
  onChange: (definition: WorkflowDefinition) => void;
}) {
  const [expandedStepId, setExpandedStepId] = useState(definition.steps[0]?.step_id ?? "");

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
          <button className="secondary-button" type="button" onClick={addDataEngineeringStep}
            disabled={disabled || definition.steps.length > 0}>
            <Plus size={15} /> Add Data Engineering
          </button>
          <button className="primary-button" type="button" onClick={addFeatureEngineeringStep}
            disabled={disabled || definition.steps.some((step) => step.type === "feature_engineering")}>
            <Plus size={15} /> Add Feature Engineering
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
                {step.type === "data_engineering" ? <DatabaseZap size={20} /> : <Sparkles size={20} />}
              </div>
              <div className="workflow-step-copy">
                <span>SELECTED STEP · {step.step_id}</span>
                <input value={step.name} onChange={(event) => updateStep(index, {
                  ...step, name: event.target.value
                })} disabled={disabled} />
                <small>{step.type === "data_engineering"
                  ? `${step.config.definition.inputs.length} sources · ${step.config.definition.steps.length} blocks · ${step.config.definition.outputs.length} outputs`
                  : `${step.config.definition.inputs.length} splits · ${step.config.definition.transformations.length} transforms · ${step.config.definition.outputs.length} outputs`}
                </small>
              </div>
              <button className="secondary-button" type="button" onClick={() => setExpandedStepId("")}>
                <Braces size={15} /> Close configuration
              </button>
              <button className="icon-button" type="button" onClick={() => removeStep(index)}
                disabled={disabled || (step.type === "data_engineering" && definition.steps.length > 1)}
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
              ) : (
                <FeatureEngineeringBuilder
                  definition={step.config.definition}
                  datasets={datasets}
                  dataAttachments={dataAttachments}
                  upstreamDefinition={previousDataEngineeringDefinition(definition.steps, index)}
                  hasUpstream={step.inputs.length > 0}
                  disabled={disabled}
                  onChange={(nextDefinition) => updateFeatureStep(index, step, nextDefinition)}
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
