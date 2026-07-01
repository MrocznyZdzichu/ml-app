import { ArrowRight, Braces, DatabaseZap, Plus, Settings2, Trash2 } from "lucide-react";
import { useState } from "react";

import type { BusinessCaseDataAttachment, DataAsset } from "../api/client";
import {
  PipelineBuilder
} from "./PipelineBuilder";
import { emptyPipelineDefinition } from "./pipelineContract";
import type {
  WorkflowDefinition,
  WorkflowStepDefinition
} from "./workflowContract";

export type { WorkflowDefinition, WorkflowStepDefinition } from "./workflowContract";
export {
  emptyWorkflowDefinition,
  normalizeWorkflowDefinition
} from "./workflowContract";

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
      config: { definition: emptyPipelineDefinition() }
    };
    setExpandedStepId(step.step_id);
    onChange({
      ...definition,
      steps: [step],
      outputs: [{ output_id: "result", source: { step_id: step.step_id, port_id: step.output_port_id } }]
    });
  }

  function updateStep(index: number, step: WorkflowStepDefinition) {
    onChange({
      ...definition,
      steps: definition.steps.map((item, itemIndex) => itemIndex === index ? step : item)
    });
  }

  function removeStep(index: number) {
    const removed = definition.steps[index];
    setExpandedStepId("");
    onChange({
      ...definition,
      steps: definition.steps.filter((_, itemIndex) => itemIndex !== index),
      outputs: definition.outputs.filter((output) => output.source.step_id !== removed.step_id)
    });
  }

  return (
    <div className="workflow-editor">
      <div className="workflow-editor-heading">
        <div>
          <span className="builder-kicker">Pipeline workflow</span>
          <h3>High-level steps</h3>
          <p>
            The saved contract is a DAG. This prototype deliberately exposes one executable
            lifecycle step: Data Engineering.
          </p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={addDataEngineeringStep}
          disabled={disabled || definition.steps.length > 0}
        >
          <Plus size={15} /> Add Data Engineering step
        </button>
      </div>

      <div className="workflow-diagram" aria-label="Pipeline workflow diagram">
        <div className="workflow-terminal start"><span>START</span></div>
        <ArrowRight className="workflow-arrow" size={28} />
        {!definition.steps.length ? (
          <button className="workflow-add-node" type="button" onClick={addDataEngineeringStep} disabled={disabled}>
            <Plus size={20} /><strong>Add first step</strong><span>Data Engineering</span>
          </button>
        ) : definition.steps.map((step, index) => {
          const de = step.config.definition;
          const selected = expandedStepId === step.step_id;
          return (
            <button
              className={selected ? "workflow-node selected" : "workflow-node"}
              type="button"
              key={step.step_id}
              onClick={() => setExpandedStepId(step.step_id)}
            >
              <DatabaseZap size={22} />
              <span><small>STEP {index + 1}</small><strong>{step.name}</strong><em>{de.steps.length} transformations</em></span>
              <Settings2 size={16} />
            </button>
          );
        })}
        <ArrowRight className="workflow-arrow" size={28} />
        <div className="workflow-terminal output"><span>OUTPUT</span></div>
      </div>

      <div className="workflow-step-list">
        {definition.steps.map((step, index) => {
          const expanded = expandedStepId === step.step_id;
          const de = step.config.definition;
          return (
            expanded && (
              <article className="workflow-step selected" key={step.step_id}>
                <div className="workflow-step-summary">
                  <div className="workflow-step-icon"><DatabaseZap size={20} /></div>
                  <div className="workflow-step-copy">
                    <span>SELECTED STEP · {step.step_id}</span>
                    <input value={step.name} onChange={(event) => updateStep(index, { ...step, name: event.target.value })} disabled={disabled} />
                    <small>{de.inputs.length} sources · {de.steps.length} blocks · {de.outputs.length} outputs</small>
                  </div>
                  <button className="secondary-button" type="button" onClick={() => setExpandedStepId("")}>
                    <Braces size={15} /> Close configuration
                  </button>
                  <button className="icon-button" type="button" onClick={() => removeStep(index)} disabled={disabled} aria-label="Remove Data Engineering step">
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="workflow-step-configuration">
                  <PipelineBuilder
                    definition={de}
                    datasets={datasets}
                    dataAttachments={dataAttachments}
                    outputNameSuggestion={outputNameSuggestion}
                    disabled={disabled}
                    onChange={(nextDefinition) =>
                      updateStep(index, {
                        ...step,
                        config: { definition: nextDefinition }
                      })
                    }
                  />
                </div>
              </article>
            )
          );
        })}
      </div>
    </div>
  );
}
