import {
  ArrowRight,
  DatabaseZap,
  Plus,
  Settings2,
  Sparkles
} from "lucide-react";
import { Fragment } from "react";

import type { WorkflowDefinition } from "./workflowContract";

export function WorkflowDiagram({
  definition,
  selectedStepId,
  disabled,
  onAddFirstStep,
  onSelectStep
}: {
  definition: WorkflowDefinition;
  selectedStepId: string;
  disabled: boolean;
  onAddFirstStep: () => void;
  onSelectStep: (stepId: string) => void;
}) {
  return (
    <div className="workflow-diagram" aria-label="Pipeline workflow diagram">
      <div className="workflow-terminal start"><span>START</span></div>
      <ArrowRight className="workflow-arrow" size={28} />
      {!definition.steps.length ? (
        <button
          className="workflow-add-node"
          type="button"
          onClick={onAddFirstStep}
          disabled={disabled}
        >
          <Plus size={20} /><strong>Add first step</strong><span>Data Engineering</span>
        </button>
      ) : definition.steps.map((step, index) => {
        const count = step.type === "data_engineering"
          ? step.config.definition.steps.length
          : step.config.definition.transformations.length;
        return (
          <Fragment key={step.step_id}>
            {index > 0 && <ArrowRight className="workflow-arrow" size={28} />}
            <button
              className={selectedStepId === step.step_id
                ? "workflow-node selected"
                : "workflow-node"}
              type="button"
              onClick={() => onSelectStep(step.step_id)}
            >
              {step.type === "data_engineering"
                ? <DatabaseZap size={22} />
                : <Sparkles size={22} />}
              <span>
                <small>STEP {index + 1}</small>
                <strong>{step.name}</strong>
                <em>{count} transformations</em>
              </span>
              <Settings2 size={16} />
            </button>
          </Fragment>
        );
      })}
      <ArrowRight className="workflow-arrow" size={28} />
      <div className="workflow-output-stack">
        {definition.outputs.length ? definition.outputs.map((output) => (
          <div
            className={`workflow-output-port ${output.source.port_id}`}
            key={output.output_id}
          >
            <span>{output.source.port_id.replace("_", " ")}</span>
            <small>{output.output_id.replaceAll("_", " ")}</small>
          </div>
        )) : <div className="workflow-terminal output"><span>OUTPUT</span></div>}
      </div>
    </div>
  );
}
