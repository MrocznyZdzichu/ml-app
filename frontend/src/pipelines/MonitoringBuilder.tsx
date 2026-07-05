import type { MonitoringDefinition } from "./monitoringContract";

export function MonitoringBuilder({
  definition,
  disabled,
  onChange
}: {
  definition: MonitoringDefinition;
  disabled: boolean;
  onChange: (definition: MonitoringDefinition) => void;
}) {
  const update = (patch: Partial<MonitoringDefinition>) =>
    onChange({ ...definition, ...patch });
  return (
    <div className="form-grid">
      <label>Stable row ID column
        <input value={definition.row_id_column} disabled={disabled}
          onChange={(event) => update({ row_id_column: event.target.value })} />
      </label>
      <label>Prediction column
        <input value={definition.prediction_column} disabled={disabled}
          onChange={(event) => update({ prediction_column: event.target.value })} />
      </label>
      <label>Target column
        <input value={definition.target_column} disabled={disabled}
          onChange={(event) => update({ target_column: event.target.value })} />
      </label>
      <label>Problem type
        <select value={definition.problem_type} disabled={disabled}
          onChange={(event) => update({
            problem_type: event.target.value as MonitoringDefinition["problem_type"]
          })}>
          <option value="binary_classification">Binary classification</option>
          <option value="multiclass_classification">Multiclass classification</option>
          <option value="regression">Regression</option>
        </select>
      </label>
      <label>Performance report name
        <input value={definition.report_name} disabled={disabled}
          onChange={(event) => update({ report_name: event.target.value })} />
      </label>
      <div className="form-note">
        Metrics use the complete upstream Process & Join output. Rows without a usable
        target are counted and excluded from metric denominators.
      </div>
    </div>
  );
}
