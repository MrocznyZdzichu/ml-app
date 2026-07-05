import {
  Activity,
  ArrowRight,
  Brain,
  Calculator,
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
          : step.type === "feature_engineering"
            ? step.config.definition.transformations.length
            : step.type === "training"
              ? step.config.definition.feature_columns.length
              : 1;
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
              {step.type === "data_engineering" ? <DatabaseZap size={22} />
                : step.type === "feature_engineering" ? <Sparkles size={22} />
                  : step.type === "training" ? <Brain size={22} />
                    : step.type === "monitoring" ? <Activity size={22} />
                      : <Calculator size={22} />}
              <span>
                <small>STEP {index + 1}</small>
                <strong>{step.name}</strong>
                <em>{step.type === "training" ? `${count} features`
                  : step.type === "scoring"
                    ? step.config.definition.purpose === "batch"
                      ? "batch prediction"
                      : "holdout evaluation"
                    : step.type === "monitoring"
                      ? "target join + KPI"
                    : `${count} transformations`}</em>
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
