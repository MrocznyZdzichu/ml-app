import { ListChecks, Search, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { useState } from "react";

import {
  classificationAlgorithms,
  defaultTrainingParameters,
  regressionAlgorithms
} from "./modelingContract";
import type {
  ModelingDefaults,
  ScoringDefinition,
  TrainingAlgorithm,
  TrainingDefinition
} from "./modelingContract";

export function TrainingBuilder({ definition, defaults, disabled, onChange }: {
  definition: TrainingDefinition;
  defaults: ModelingDefaults;
  disabled: boolean;
  onChange: (definition: TrainingDefinition) => void;
}) {
  const [openDialog, setOpenDialog] = useState<"features" | "parameters" | null>(null);
  const update = (patch: Partial<TrainingDefinition>) => onChange({ ...definition, ...patch });
  const algorithms = definition.problem_type === "regression"
    ? regressionAlgorithms
    : classificationAlgorithms;
  const updateAlgorithm = (algorithm: TrainingAlgorithm) => update({
    algorithm,
    parameters: defaultTrainingParameters(algorithm)
  });
  return <div className="inspector-form modeling-builder">
    <div className="scope-badge">Full-data, memory-bounded training without sampling.</div>
    <div className="fe-suggestion">
      <Sparkles size={17} />
      <span>Defaults combine the Business Case and the upstream Feature Engineering contract.</span>
    </div>
    <label>Problem type<select value={definition.problem_type} disabled={disabled} onChange={(event) => {
      const problem_type = event.target.value as TrainingDefinition["problem_type"];
      const algorithm = problem_type === "regression" ? regressionAlgorithms[0] : classificationAlgorithms[0];
      update({ problem_type, algorithm, parameters: defaultTrainingParameters(algorithm) });
    }}>
      <option value="binary_classification">Binary classification</option>
      <option value="multiclass_classification">Multiclass classification</option>
      <option value="regression">Regression</option>
    </select></label>
    <label>Algorithm<select value={definition.algorithm} disabled={disabled}
      onChange={(event) => updateAlgorithm(event.target.value as TrainingAlgorithm)}>
      {algorithms.map((algorithm) => <option value={algorithm} key={algorithm}>
        {algorithmLabel(algorithm)}
      </option>)}
    </select></label>
    <label>Model name<input value={definition.model_name} disabled={disabled}
      onChange={(event) => update({ model_name: event.target.value })} /></label>
    <ColumnSelect label="Target column" value={definition.target_column}
      columns={defaults.available_columns} disabled={disabled}
      onChange={(target_column) => update({
        target_column,
        feature_columns: definition.feature_columns.filter((item) => item !== target_column)
      })} />
    <div className="modeling-action-grid">
      <button className="modeling-config-button" type="button" disabled={disabled}
        onClick={() => setOpenDialog("features")}>
        <ListChecks size={18} />
        <span><strong>Add features</strong>
          <small>{definition.feature_columns.length} selected from {defaults.available_columns.length} available</small></span>
      </button>
      <button className="modeling-config-button" type="button" disabled={disabled}
        onClick={() => setOpenDialog("parameters")}>
        <SlidersHorizontal size={18} />
        <span><strong>Training parameters</strong>
          <small>{parameterSummary(definition)}</small></span>
      </button>
    </div>
    <small>Official runs create immutable model and metrics artifacts with lineage.</small>
    {openDialog === "features" && <ModelingDialog title="Model features"
      subtitle="Choose the exact columns consumed by the estimator."
      onClose={() => setOpenDialog(null)}>
      <ColumnPicker label="Model features"
        columns={defaults.available_columns.filter((item) =>
          item !== definition.target_column && item !== defaults.row_id_column
        )}
        selected={definition.feature_columns}
        disabled={disabled}
        onChange={(feature_columns) => update({ feature_columns })} />
    </ModelingDialog>}
    {openDialog === "parameters" && <ModelingDialog title="Training parameters"
      subtitle={`${algorithmLabel(definition.algorithm)} · full-data batch execution`}
      onClose={() => setOpenDialog(null)}>
      <TrainingParameters definition={definition} defaults={defaults} disabled={disabled} onChange={onChange} />
    </ModelingDialog>}
  </div>;
}

function TrainingParameters({ definition, defaults, disabled, onChange }: {
  definition: TrainingDefinition;
  defaults: ModelingDefaults;
  disabled: boolean;
  onChange: (definition: TrainingDefinition) => void;
}) {
  const update = (patch: Partial<TrainingDefinition>) => onChange({ ...definition, ...patch });
  const updateParameters = (patch: Record<string, unknown>) => update({
    parameters: { ...definition.parameters, ...patch }
  });
  return <div className="modeling-modal-content">
    <div className="step-grid">
      <label>Maximum epochs<input type="number" min={1} max={100} value={definition.epochs} disabled={disabled}
        onChange={(event) => update({ epochs: Number(event.target.value) })} /></label>
      <label>Batch size<input type="number" min={100} max={100000} value={definition.batch_size} disabled={disabled}
        onChange={(event) => update({ batch_size: Number(event.target.value) })} /></label>
      <label>Random seed<input type="number" value={definition.random_seed} disabled={disabled}
        onChange={(event) => update({ random_seed: Number(event.target.value) })} /></label>
    </div>
    <AlgorithmParameters definition={definition} disabled={disabled} onChange={updateParameters} />
    <label className="fe-toggle">
      <input type="checkbox" checked={definition.early_stopping}
        disabled={disabled || !defaults.has_validation}
        onChange={(event) => update({ early_stopping: event.target.checked })} />
      <span><strong>Early stopping</strong>
        <small>{defaults.has_validation
          ? "Keep the best validation model and stop after the patience budget."
          : "Add an explicit validation output in Feature Engineering to enable this."}</small>
      </span>
    </label>
    {definition.early_stopping && defaults.has_validation && <div className="step-grid">
      <label>Patience (epochs)<input type="number" min={1} max={50}
        value={definition.early_stopping_patience} disabled={disabled}
        onChange={(event) => update({ early_stopping_patience: Number(event.target.value) })} /></label>
      <label>Minimum improvement<input type="number" min={0} max={1} step={0.0001}
        value={definition.early_stopping_min_delta} disabled={disabled}
        onChange={(event) => update({ early_stopping_min_delta: Number(event.target.value) })} /></label>
    </div>}
  </div>;
}

function AlgorithmParameters({ definition, disabled, onChange }: {
  definition: TrainingDefinition;
  disabled: boolean;
  onChange: (patch: Record<string, unknown>) => void;
}) {
  const parameters = definition.parameters;
  const numberValue = (key: string, fallback: number) => Number(parameters[key] ?? fallback);
  const booleanValue = (key: string, fallback: boolean) =>
    typeof parameters[key] === "boolean" ? Boolean(parameters[key]) : fallback;
  if (definition.algorithm === "passive_aggressive_classifier") {
    return <div className="step-grid">
      <label>Aggressiveness C<input type="number" min={0.000001} step={0.1}
        value={numberValue("C", 1)} disabled={disabled}
        onChange={(event) => onChange({ C: Number(event.target.value) })} /></label>
      <label>Loss<select value={String(parameters.loss ?? "hinge")} disabled={disabled}
        onChange={(event) => onChange({ loss: event.target.value })}>
        <option value="hinge">Hinge</option><option value="squared_hinge">Squared hinge</option>
      </select></label>
      <BooleanSelect label="Average weights" value={booleanValue("average", false)}
        disabled={disabled} onChange={(average) => onChange({ average })} />
      <BooleanSelect label="Fit intercept" value={booleanValue("fit_intercept", true)}
        disabled={disabled} onChange={(fit_intercept) => onChange({ fit_intercept })} />
    </div>;
  }
  if (definition.algorithm === "passive_aggressive_regressor") {
    return <div className="step-grid">
      <label>Aggressiveness C<input type="number" min={0.000001} step={0.1}
        value={numberValue("C", 1)} disabled={disabled}
        onChange={(event) => onChange({ C: Number(event.target.value) })} /></label>
      <label>Epsilon<input type="number" min={0} step={0.01}
        value={numberValue("epsilon", 0.1)} disabled={disabled}
        onChange={(event) => onChange({ epsilon: Number(event.target.value) })} /></label>
      <label>Loss<select value={String(parameters.loss ?? "epsilon_insensitive")} disabled={disabled}
        onChange={(event) => onChange({ loss: event.target.value })}>
        <option value="epsilon_insensitive">Epsilon insensitive</option>
        <option value="squared_epsilon_insensitive">Squared epsilon insensitive</option>
      </select></label>
      <BooleanSelect label="Average weights" value={booleanValue("average", false)}
        disabled={disabled} onChange={(average) => onChange({ average })} />
      <BooleanSelect label="Fit intercept" value={booleanValue("fit_intercept", true)}
        disabled={disabled} onChange={(fit_intercept) => onChange({ fit_intercept })} />
    </div>;
  }
  if (definition.algorithm === "perceptron_classifier") {
    return <div className="step-grid">
      <label>Alpha<input type="number" min={0} step={0.0001}
        value={numberValue("alpha", 0.0001)} disabled={disabled}
        onChange={(event) => onChange({ alpha: Number(event.target.value) })} /></label>
      <PenaltySelect value={parameters.penalty} disabled={disabled}
        onChange={(penalty) => onChange({ penalty })} />
      <label>Learning rate<input type="number" min={0.000001} step={0.1}
        value={numberValue("eta0", 1)} disabled={disabled}
        onChange={(event) => onChange({ eta0: Number(event.target.value) })} /></label>
      <BooleanSelect label="Fit intercept" value={booleanValue("fit_intercept", true)}
        disabled={disabled} onChange={(fit_intercept) => onChange({ fit_intercept })} />
    </div>;
  }
  return <div className="step-grid">
    <label>Alpha<input type="number" min={0} step={0.0001}
      value={numberValue("alpha", 0.0001)} disabled={disabled}
      onChange={(event) => onChange({ alpha: Number(event.target.value) })} /></label>
    <PenaltySelect value={parameters.penalty} disabled={disabled}
      onChange={(penalty) => onChange({ penalty })} />
    <label>Learning-rate schedule<select value={String(parameters.learning_rate ?? "optimal")}
      disabled={disabled} onChange={(event) => onChange({ learning_rate: event.target.value })}>
      <option value="optimal">Optimal</option><option value="constant">Constant</option>
      <option value="invscaling">Inverse scaling</option><option value="adaptive">Adaptive</option>
    </select></label>
    <BooleanSelect label="Fit intercept" value={booleanValue("fit_intercept", true)}
      disabled={disabled} onChange={(fit_intercept) => onChange({ fit_intercept })} />
  </div>;
}

function PenaltySelect({ value, disabled, onChange }: {
  value: unknown;
  disabled: boolean;
  onChange: (value: string | null) => void;
}) {
  return <label>Penalty<select value={value == null ? "none" : String(value)} disabled={disabled}
    onChange={(event) => onChange(event.target.value === "none" ? null : event.target.value)}>
    <option value="none">None</option><option value="l2">L2</option>
    <option value="l1">L1</option><option value="elasticnet">Elastic net</option>
  </select></label>;
}

function BooleanSelect({ label, value, disabled, onChange }: {
  label: string;
  value: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  return <label>{label}<select value={value ? "true" : "false"} disabled={disabled}
    onChange={(event) => onChange(event.target.value === "true")}>
    <option value="true">Yes</option><option value="false">No</option>
  </select></label>;
}

function ModelingDialog({ title, subtitle, onClose, children }: {
  title: string;
  subtitle: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return <div className="modal-backdrop modeling-modal-backdrop" role="presentation" onMouseDown={onClose}>
    <section className="modal-dialog modeling-modal" role="dialog" aria-modal="true"
      aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
      <header className="modal-header">
        <div><h2>{title}</h2><p>{subtitle}</p></div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
          <X size={17} />
        </button>
      </header>
      {children}
      <footer className="modal-actions">
        <button className="primary-button" type="button" onClick={onClose}>Done</button>
      </footer>
    </section>
  </div>;
}

function algorithmLabel(algorithm: TrainingAlgorithm) {
  return {
    sgd_classifier: "Incremental logistic classifier (SGD)",
    passive_aggressive_classifier: "Passive-Aggressive classifier",
    perceptron_classifier: "Perceptron classifier",
    sgd_regressor: "Incremental linear regressor (SGD)",
    passive_aggressive_regressor: "Passive-Aggressive regressor"
  }[algorithm];
}

function parameterSummary(definition: TrainingDefinition) {
  const early = definition.early_stopping ? ` · early stopping, patience ${definition.early_stopping_patience}` : "";
  return `max ${definition.epochs} epochs · batch ${definition.batch_size}${early}`;
}

export function ScoringBuilder({ definition, defaults, disabled, onChange }: {
  definition: ScoringDefinition;
  defaults: ModelingDefaults;
  disabled: boolean;
  onChange: (definition: ScoringDefinition) => void;
}) {
  const update = (patch: Partial<ScoringDefinition>) => onChange({ ...definition, ...patch });
  return <div className="inspector-form modeling-builder">
    <div className="scope-badge">Uses the exact model port and scans every scoring row.</div>
    <ColumnSelect label="Row ID column" value={definition.row_id_column}
      columns={defaults.available_columns} disabled={disabled}
      onChange={(row_id_column) => update({ row_id_column })} />
    <ColumnSelect label="Target column for test metrics" value={definition.target_column}
      columns={defaults.available_columns} optional disabled={disabled}
      onChange={(target_column) => update({ target_column })} />
    <label>Prediction column<input value={definition.prediction_column} disabled={disabled}
      onChange={(event) => update({ prediction_column: event.target.value })} /></label>
    <label>Output dataset name<input value={definition.dataset_name} disabled={disabled}
      onChange={(event) => update({ dataset_name: event.target.value })} /></label>
    <label>Batch size<input type="number" min={100} max={100000} value={definition.batch_size} disabled={disabled}
      onChange={(event) => update({ batch_size: Number(event.target.value) })} /></label>
    <small>Output: Parquet prediction dataset with row ID, prediction and optional metrics.</small>
  </div>;
}

function ColumnSelect({ label, value, columns, optional = false, disabled, onChange }: {
  label: string;
  value: string;
  columns: string[];
  optional?: boolean;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return <label className="fe-field"><span>{label}</span>
    <select value={value} disabled={disabled || !columns.length}
      onChange={(event) => onChange(event.target.value)}>
      <option value="">{optional ? "Not assigned" : "Choose column…"}</option>
      {columns.map((column) => <option value={column} key={column}>{column}</option>)}
    </select>
    {!columns.length && <small>Configure the upstream Feature Engineering column roles first.</small>}
  </label>;
}

function ColumnPicker({ label, columns, selected, disabled, onChange }: {
  label: string;
  columns: string[];
  selected: string[];
  disabled: boolean;
  onChange: (selected: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const visible = columns.filter((column) => column.toLowerCase().includes(query.toLowerCase()));
  return <fieldset className="fe-column-picker">
    <legend>{label}<span>{selected.length} selected</span></legend>
    <div className="fe-column-toolbar">
      <label><Search size={14} /><input value={query} disabled={disabled}
        onChange={(event) => setQuery(event.target.value)} placeholder="Filter columns…" /></label>
      <button type="button" disabled={disabled} onClick={() => onChange(columns)}>All</button>
      <button type="button" disabled={disabled} onClick={() => onChange([])}>Clear</button>
    </div>
    <div className="fe-column-options">
      {visible.map((column) => <label key={column}>
        <input type="checkbox" checked={selected.includes(column)} disabled={disabled}
          onChange={(event) => onChange(event.target.checked
            ? [...selected, column]
            : selected.filter((item) => item !== column))} />
        <span>{column}<small>upstream column</small></span>
      </label>)}
      {!visible.length && <div className="fe-no-columns">No matching columns</div>}
    </div>
  </fieldset>;
}
