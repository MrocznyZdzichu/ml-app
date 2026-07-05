import { ArrowRight, ChevronDown, ChevronUp, Code2, Database, Plus, SlidersHorizontal, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { BusinessCaseDataAttachment, DataAsset, DatasetColumn } from "../api/client";
import type {
  PipelineDefinition,
  DataContractDefinition,
  PipelineInputDefinition,
  PipelineOutputDefinition,
  PipelinePortReference,
  PipelineStepDefinition,
  PipelineStepType
} from "./pipelineContract";
import {
  emptyPipelineDefinition,
  normalizePipelineDefinition,
  rewireSequentialFlow,
  sanitizeCategoryMapping
} from "./pipelineContract";
import {
  inferPipelineNodeColumns,
  inferPipelineOutputColumns,
  inferPipelineStepInputColumns
} from "./pipelineSchema";
import {
  businessCaseDataRoleOptions,
  datasetVersionPolicyOptions
} from "./dataContractOptions";

export type {
  PipelineDefinition,
  PipelineInputDefinition,
  PipelineOutputDefinition,
  PipelinePortReference,
  PipelineStepDefinition,
  PipelineStepType
} from "./pipelineContract";
export { emptyPipelineDefinition, normalizePipelineDefinition } from "./pipelineContract";

type PipelineColumn = DatasetColumn & {
  role?: string;
};

const stepOptions: Array<{ type: PipelineStepType; label: string; description: string }> = [
  { type: "select_columns", label: "Select columns", description: "Keep an explicit column projection." },
  { type: "add_identifier", label: "Add identifier", description: "Create a stable row identifier from a hash or ordered sequence." },
  { type: "filter_rows", label: "Filter rows", description: "Keep rows matching a structured predicate." },
  { type: "rename_columns", label: "Rename columns", description: "Rename one or more columns." },
  { type: "cast_columns", label: "Cast columns", description: "Convert columns to validated DuckDB types." },
  { type: "impute_missing", label: "Fill missing values", description: "Replace nulls with fixed values." },
  { type: "derive_column", label: "Derive column", description: "Create a column from a safe expression." },
  { type: "sort_rows", label: "Sort rows", description: "Order rows by a selected column." },
  { type: "deduplicate", label: "Deduplicate", description: "Remove duplicate rows or duplicate keys." },
  { type: "aggregate", label: "Aggregate", description: "Group rows and calculate a metric." },
  { type: "map_categories", label: "Map categories", description: "Replace categorical values from a mapping." },
  { type: "join", label: "Join", description: "Join two upstream nodes by matching keys." },
  { type: "union", label: "Union", description: "Append two upstream nodes by column name." },
  { type: "custom_sql", label: "User Written SQL", description: "One controlled SELECT/WITH query over declared inputs." }
];

export function PipelineBuilder({
  definition,
  datasets,
  dataAttachments,
  outputNameSuggestion = "result",
  onChange,
  disabled = false
}: {
  definition: PipelineDefinition;
  datasets: DataAsset[];
  dataAttachments: BusinessCaseDataAttachment[];
  outputNameSuggestion?: string;
  onChange: (definition: PipelineDefinition) => void;
  disabled?: boolean;
}) {
  const [selectedNodeId, setSelectedNodeId] = useState<string>("");
  const [schemaCache, setSchemaCache] = useState<Record<string, DatasetColumn[]>>({});
  const attachmentByDataset = useMemo(
    () => new Map(dataAttachments.map((attachment) => [attachment.data_asset_id, attachment])),
    [dataAttachments]
  );
  const activeDatasets = useMemo(
    () =>
      datasets
        .filter((dataset) => dataset.status !== "deleted" && ["csv", "parquet"].includes(dataset.format))
        .sort((left, right) => {
          const roleRank = (datasetId: string) => {
            const role = attachmentByDataset.get(datasetId)?.role;
            return [
              "source",
              "training",
              "scoring_input",
              "scoring_output",
              "monitoring_actuals",
              "monitoring_input",
              "validation",
              "test",
              "reference"
            ].indexOf(role ?? "") + 1 || 99;
          };
          return roleRank(left.id) - roleRank(right.id) || left.name.localeCompare(right.name);
        }),
    [attachmentByDataset, datasets]
  );
  useEffect(() => {
    const missing = definition.inputs
      .map((input) => datasets.find((dataset) => dataset.id === input.dataset_id))
      .filter((dataset): dataset is DataAsset =>
        Boolean(dataset)
        && !schemaCache[dataset!.id]
        && (!Array.isArray(dataset!.metadata.source_schema) || dataset!.metadata.source_schema.length === 0)
      );
    for (const dataset of missing) {
      void api.previewDataset(dataset.id, 1)
        .then((preview) => setSchemaCache((current) => ({ ...current, [dataset.id]: preview.columns })))
        .catch(() => setSchemaCache((current) => ({ ...current, [dataset.id]: [] })));
    }
  }, [datasets, definition.inputs, schemaCache]);
  useEffect(() => {
    let changed = false;
    const steps = definition.steps.map((step) => {
      const columns = inferPipelineStepInputColumns(definition, datasets, schemaCache, step)
        .map((column) => column.name);
      const serialized = JSON.stringify(step.config);
      if (
        columns.length
        && (serialized.includes('"column_name"') || serialized.includes('"key"'))
        && !columns.includes("column_name")
        && !columns.includes("key")
      ) {
        changed = true;
        return { ...step, config: defaultConfig(step.type, columns) };
      }
      return step;
    });
    if (changed) onChange({ ...definition, steps });
  }, [datasets, definition, onChange, schemaCache]);
  const allColumns = useMemo(
    () =>
      Array.from(
        new Set(
          definition.inputs.flatMap((input) => {
            const dataset = datasets.find((item) => item.id === input.dataset_id);
            return columnsForDataset(dataset, schemaCache).map((column) => column.name);
          })
        )
      ),
    [datasets, definition.inputs, schemaCache]
  );

  function update(next: Partial<PipelineDefinition>) {
    onChange({ ...definition, ...next });
  }

  function addInput() {
    const used = new Set(definition.inputs.map((input) => input.input_id));
    const inputId = nextStableId("source", used);
    const nextInput: PipelineInputDefinition = {
      input_id: inputId,
      dataset_id: activeDatasets[0]?.id ?? "",
      output_port_id: "out",
      version_policy: "latest"
    };
    const inputs = [...definition.inputs, nextInput];
    const outputs = definition.outputs.length
      ? definition.outputs
      : [datasetOutput({ node_id: inputId, port_id: "out" }, "result", undefined, outputNameSuggestion)];
    update({ inputs, outputs });
    setSelectedNodeId(inputId);
  }

  function updateInput(index: number, patch: Partial<PipelineInputDefinition>) {
    update({ inputs: definition.inputs.map((input, itemIndex) => itemIndex === index ? { ...input, ...patch } : input) });
  }

  function removeInput(index: number) {
    const target = definition.inputs[index];
    if (isNodeReferenced(definition, target.input_id)) return;
    update({ inputs: definition.inputs.filter((_, itemIndex) => itemIndex !== index) });
  }

  function addStep(type: PipelineStepType) {
    const available = availableSources(definition);
    if (!available.length) return;
    const stepId = nextStableId("step", new Set(definition.steps.map((step) => step.step_id)));
    const source = available[available.length - 1].reference;
    const secondSource = available.length > 1 ? available[available.length - 2].reference : source;
    const upstreamColumns = inferPipelineNodeColumns(definition, datasets, schemaCache, source.node_id)
      .map((column) => column.name);
    const step: PipelineStepDefinition = {
      step_id: stepId,
      type,
      inputs: defaultInputs(type, source, secondSource),
      output_port_id: "out",
      config: defaultConfig(type, upstreamColumns)
    };
    update({
      steps: [...definition.steps, step],
      outputs: [datasetOutput({ node_id: stepId, port_id: "out" }, "result", undefined, outputNameSuggestion)]
    });
    setSelectedNodeId(stepId);
  }

  function updateStep(index: number, nextStep: PipelineStepDefinition) {
    update({ steps: definition.steps.map((step, itemIndex) => itemIndex === index ? nextStep : step) });
  }

  function changeStepType(index: number, type: PipelineStepType) {
    const step = definition.steps[index];
    const sources = availableSources(definition, index);
    const first = step.inputs[0]?.source ?? sources.at(-1)?.reference;
    if (!first) return;
    const second = step.inputs[1]?.source ?? sources.at(-2)?.reference ?? first;
    const upstreamColumns = inferPipelineNodeColumns(definition, datasets, schemaCache, first.node_id)
      .map((column) => column.name);
    updateStep(index, {
      ...step,
      type,
      inputs: defaultInputs(type, first, second),
      config: defaultConfig(type, upstreamColumns)
    });
  }

  function removeStep(index: number) {
    const removed = definition.steps[index];
    const fallback = removed.inputs[0]?.source;
    const steps = definition.steps
      .filter((_, itemIndex) => itemIndex !== index)
      .map((step) => ({
        ...step,
        inputs: step.inputs.map((input) =>
          input.source.node_id === removed.step_id && fallback
            ? { ...input, source: fallback }
            : input
        )
      }));
    const outputs = definition.outputs.map((output) =>
      output.input.node_id === removed.step_id && fallback
        ? { ...output, input: fallback }
        : output
    );
    update({ steps, outputs });
  }

  function moveStep(index: number, direction: -1 | 1) {
    const destination = index + direction;
    if (destination < 0 || destination >= definition.steps.length) return;
    const steps = [...definition.steps];
    [steps[index], steps[destination]] = [steps[destination], steps[index]];
    update(rewireSequentialFlow({ ...definition, steps }));
  }

  const outputSources = availableSources(definition);
  const selectedOutput = definition.outputs[0]?.input;
  const outputColumns = useMemo(
    () => inferPipelineOutputColumns(definition, datasets, schemaCache),
    [datasets, definition, schemaCache]
  );
  useEffect(() => {
    const output = definition.outputs[0];
    if (!output || !outputColumns.length) return;
    const dataContract = synchronizeDataContract(output.data_contract, outputColumns);
    if (JSON.stringify(output.data_contract) === JSON.stringify(dataContract)) return;
    onChange({
      ...definition,
      outputs: [{ ...output, data_contract: dataContract }, ...definition.outputs.slice(1)]
    });
  }, [definition, onChange, outputColumns]);
  const isExecutable = definition.inputs.length > 0 && definition.outputs.length > 0;
  const selectedInputIndex = definition.inputs.findIndex((input) => input.input_id === selectedNodeId);
  const selectedStepIndex = definition.steps.findIndex((step) => step.step_id === selectedNodeId);

  return (
    <div className="de-designer">
      <datalist id="pipeline-column-names">
        {allColumns.map((column) => <option key={column} value={column} />)}
      </datalist>
      <aside className="de-palette">
        <div><span className="builder-kicker">Toolbox</span><h3>DE blocks</h3><p>Select a block to append it to the flow.</p></div>
        <button className="palette-source" onClick={addInput} type="button" disabled={disabled || !activeDatasets.length}>
          <Database size={17} /><span><strong>Dataset source</strong><small>CSV or Parquet</small></span><Plus size={14} />
        </button>
        <div className="palette-divider">Transformations</div>
        {stepOptions.map((option) => (
          <button key={option.type} type="button" onClick={() => addStep(option.type)} disabled={disabled || !definition.inputs.length}>
            <SlidersHorizontal size={16} /><span><strong>{option.label}</strong><small>{option.description}</small></span><Plus size={14} />
          </button>
        ))}
      </aside>

      <div className="de-canvas">
        <div className="canvas-toolbar"><span>Data flow</span><small>Click a node to configure it</small></div>
        <div className="de-flow">
          <div className="de-source-stack">
            {definition.inputs.map((input) => {
              const dataset = datasets.find((item) => item.id === input.dataset_id);
              return (
                <button className={selectedNodeId === input.input_id ? "de-node source selected" : "de-node source"} type="button" key={input.input_id} onClick={() => setSelectedNodeId(input.input_id)}>
                  <Database size={19} /><span><small>SOURCE {attachmentByDataset.get(input.dataset_id)?.role ? `· ${attachmentByDataset.get(input.dataset_id)?.role}` : ""}</small><strong>{dataset?.name ?? input.input_id}</strong><em>{dataset?.row_count ?? "?"} rows</em></span>
                </button>
              );
            })}
            {!definition.inputs.length && (
              <button className="canvas-empty-node suggested" type="button" onClick={addInput} disabled={disabled || !activeDatasets.length}>
                <strong>{activeDatasets[0] ? `Use suggested: ${activeDatasets[0].name}` : "Add a dataset source"}</strong>
                <span>
                  {activeDatasets[0] && attachmentByDataset.get(activeDatasets[0].id)?.role
                    ? `BC role: ${attachmentByDataset.get(activeDatasets[0].id)?.role}`
                    : "Choose from uploaded CSV or Parquet datasets"}
                </span>
              </button>
            )}
          </div>
          <ArrowRight className="de-edge-arrow" size={27} />
          <div className="de-transform-chain">
            {definition.steps.map((step, index) => (
              <div className="de-chain-item" key={step.step_id}>
                {index > 0 && <ArrowRight className="de-edge-arrow inline" size={24} />}
                <button className={selectedNodeId === step.step_id ? "de-node transform selected" : "de-node transform"} type="button" onClick={() => setSelectedNodeId(step.step_id)}>
                  <SlidersHorizontal size={19} /><span><small>TRANSFORM</small><strong>{stepOptions.find((item) => item.type === step.type)?.label}</strong><em>from {step.inputs.map((item) => item.source.node_id).join(", ")}</em></span>
                </button>
              </div>
            ))}
            {!definition.steps.length && <div className="canvas-empty-node compact">Optional transformations</div>}
          </div>
          <ArrowRight className="de-edge-arrow" size={27} />
          <button className={selectedNodeId === "__output__" ? "de-node output selected" : "de-node output"} type="button" onClick={() => setSelectedNodeId("__output__")} disabled={!definition.outputs.length}>
            <span><small>OUTPUT</small><strong>{definition.outputs[0]?.dataset_name ?? "Result dataset"}</strong><em>Parquet</em></span>
          </button>
        </div>
      </div>

      <aside className="de-inspector">
        <div><span className="builder-kicker">Inspector</span><h3>Node settings</h3></div>
        {selectedInputIndex >= 0 && (() => {
          const input = definition.inputs[selectedInputIndex];
          const dataset = datasets.find((item) => item.id === input.dataset_id);
          const referenced = isNodeReferenced(definition, input.input_id);
          return (
            <div className="inspector-form">
              <label>Dataset<select value={input.dataset_id} onChange={(event) => updateInput(selectedInputIndex, { dataset_id: event.target.value })} disabled={disabled}>
                <option value="">Choose dataset</option>
                {activeDatasets.map((item) => {
                  const role = attachmentByDataset.get(item.id)?.role;
                  return <option key={item.id} value={item.id}>{role ? `★ ${role} · ` : ""}{item.name} · {item.row_count ?? "?"} rows</option>;
                })}
              </select></label>
              <label>Version policy<select
                value={input.version_policy ?? "latest"}
                onChange={(event) => updateInput(selectedInputIndex, {
                  version_policy: event.target.value as PipelineInputDefinition["version_policy"]
                })}
                disabled={disabled}
              >
                {datasetVersionPolicyOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select></label>
              <label>Stable source ID<input value={input.input_id} disabled /></label>
              {attachmentByDataset.get(input.dataset_id)?.role && (
                <div className="source-recommendation">Suggested by BC role: <strong>{attachmentByDataset.get(input.dataset_id)?.role}</strong></div>
              )}
              {dataset && <SchemaSummary dataset={dataset} columns={columnsForDataset(dataset, schemaCache)} />}
              <button className="secondary-button danger-action" type="button" disabled={disabled || referenced} onClick={() => removeInput(selectedInputIndex)}><Trash2 size={15} /> Remove source</button>
            </div>
          );
        })()}
        {selectedStepIndex >= 0 && (
          <StepCard
            step={definition.steps[selectedStepIndex]}
            index={selectedStepIndex}
            sourceOptions={availableSources(definition, selectedStepIndex)}
            availableColumns={inferPipelineStepInputColumns(definition, datasets, schemaCache, definition.steps[selectedStepIndex], columnRoles)}
            inputColumns={definition.steps[selectedStepIndex].inputs.map((input) =>
              inferPipelineNodeColumns(definition, datasets, schemaCache, input.source.node_id, new Set<string>(), columnRoles)
            )}
            sourceDatasetIds={datasetIdsForStepInputs(
              definition,
              definition.steps[selectedStepIndex]
            ).map((datasetId) => physicalDatasetId(datasets, datasetId))}
            disabled={disabled}
            onChange={(nextStep) => updateStep(selectedStepIndex, nextStep)}
            onTypeChange={(type) => changeStepType(selectedStepIndex, type)}
            onMove={(direction) => moveStep(selectedStepIndex, direction)}
            onRemove={() => {
              removeStep(selectedStepIndex);
              setSelectedNodeId("");
            }}
          />
        )}
        {selectedNodeId === "__output__" && (
          <div className="inspector-form">
            <label>Dataset name<input value={definition.outputs[0]?.dataset_name ?? outputNameSuggestion} onChange={(event) => update({ outputs: [{ ...datasetOutput(selectedOutput ?? outputSources[0]?.reference, definition.outputs[0]?.output_id, definition.outputs[0], outputNameSuggestion), dataset_name: event.target.value }] })} disabled={disabled || !isExecutable} /></label>
            <label>Output of<select value={referenceKey(selectedOutput)} onChange={(event) => update({ outputs: [datasetOutput(referenceFromKey(event.target.value), definition.outputs[0]?.output_id, definition.outputs[0], outputNameSuggestion)] })} disabled={disabled || !outputSources.length}>
              {outputSources.map((source) => <option key={referenceKey(source.reference)} value={referenceKey(source.reference)}>{source.label}</option>)}
            </select></label>
            <label>Business Case role<select value={definition.outputs[0]?.business_case_role ?? "source"} onChange={(event) => update({ outputs: [{ ...datasetOutput(selectedOutput, definition.outputs[0]?.output_id, definition.outputs[0], outputNameSuggestion), business_case_role: event.target.value as PipelineOutputDefinition["business_case_role"] }] })} disabled={disabled || !isExecutable}>
              {businessCaseDataRoleOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select></label>
            <DataContractEditor
              contract={definition.outputs[0]?.data_contract}
              columns={outputColumns}
              disabled={disabled || !isExecutable}
              onChange={(data_contract) => update({
                outputs: [{
                  ...datasetOutput(selectedOutput, definition.outputs[0]?.output_id, definition.outputs[0], outputNameSuggestion),
                  data_contract
                }]
              })}
            />
            <div className="scope-badge">Run: persistent Parquet · Dry-run: temporary preview</div>
          </div>
        )}
        {!selectedNodeId && <div className="inspector-empty">Select a source, transformation or output node on the canvas.</div>}
      </aside>
    </div>
  );
}

function StepCard({
  step,
  index,
  sourceOptions,
  availableColumns,
  inputColumns,
  sourceDatasetIds,
  disabled,
  onChange,
  onTypeChange,
  onMove,
  onRemove
}: {
  step: PipelineStepDefinition;
  index: number;
  sourceOptions: SourceOption[];
  availableColumns: PipelineColumn[];
  inputColumns: PipelineColumn[][];
  sourceDatasetIds: string[];
  disabled: boolean;
  onChange: (step: PipelineStepDefinition) => void;
  onTypeChange: (type: PipelineStepType) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}) {
  const option = stepOptions.find((item) => item.type === step.type);

  function updateInput(inputIndex: number, source: PipelinePortReference) {
    onChange({
      ...step,
      inputs: step.inputs.map((input, indexValue) => indexValue === inputIndex ? { ...input, source } : input)
    });
  }

  return (
    <article className={`pipeline-step-card ${step.type === "custom_sql" ? "code-step" : ""}`}>
      <div className="step-index">{index + 1}</div>
      <div className="step-content">
        <div className="step-header">
          <div>
            <strong>{option?.label ?? step.type}</strong>
            <span>{step.step_id} · output port {step.output_port_id}</span>
          </div>
          <div className="button-row">
            <button className="icon-button" type="button" onClick={() => onMove(-1)} disabled={disabled || index === 0} aria-label="Move block up">
              <ChevronUp size={15} />
            </button>
            <button className="icon-button" type="button" onClick={() => onMove(1)} disabled={disabled} aria-label="Move block down">
              <ChevronDown size={15} />
            </button>
            <button className="icon-button" type="button" onClick={onRemove} disabled={disabled} aria-label="Remove block">
              <Trash2 size={15} />
            </button>
          </div>
        </div>
        <div className="step-grid">
          <label>
            Block type
            <select value={step.type} onChange={(event) => onTypeChange(event.target.value as PipelineStepType)} disabled={disabled}>
              {stepOptions.map((item) => <option value={item.type} key={item.type}>{item.label}</option>)}
            </select>
          </label>
          {step.inputs.map((input, inputIndex) => (
            <label key={input.port_id}>
              {step.inputs.length > 1 ? `${titleCase(input.port_id)} input` : "Upstream node"}
              <select
                value={referenceKey(input.source)}
                onChange={(event) => updateInput(inputIndex, referenceFromKey(event.target.value))}
                disabled={disabled}
              >
                {sourceOptions.map((source) => (
                  <option value={referenceKey(source.reference)} key={referenceKey(source.reference)}>{source.label}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <StepConfigEditor
          type={step.type}
          config={step.config}
          availableColumns={availableColumns}
          inputColumns={inputColumns}
          sourceDatasetIds={sourceDatasetIds}
          disabled={disabled}
          onChange={(config) => onChange({ ...step, config })}
        />
      </div>
    </article>
  );
}

function StepConfigEditor({ type, config, availableColumns, inputColumns, sourceDatasetIds, disabled, onChange }: {
  type: PipelineStepType;
  config: Record<string, unknown>;
  availableColumns: PipelineColumn[];
  inputColumns: PipelineColumn[][];
  sourceDatasetIds: string[];
  disabled: boolean;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const columnNames = availableColumns.map((column) => column.name);
  if (type === "custom_sql") {
    return <SqlExpressionEditor
      title="User Written SQL"
      hint="Use input as the upstream relation."
      value={String(config.sql ?? "")}
      columns={availableColumns}
      disabled={disabled}
      onChange={(sql) => onChange({ sql })}
      fullQuery
    />;
  }
  if (type === "select_columns" || type === "deduplicate") {
    return <ColumnMultiSelect label={type === "select_columns" ? "Columns to keep" : "Duplicate key columns"} hint={type === "deduplicate" ? "No selection compares complete rows." : undefined} columns={columnNames} selected={stringList(config.columns)} onChange={(columns) => onChange({ columns })} disabled={disabled} />;
  }
  if (type === "add_identifier") {
    return <IdentifierEditor
      config={config}
      columns={columnNames}
      disabled={disabled}
      onChange={onChange}
    />;
  }
  if (type === "rename_columns") {
    const renames = recordValue(config.renames);
    const complete = Object.fromEntries(columnNames.map((column) => [column, renames[column] ?? column]));
    return <div className="config-table">
      <div className="config-table-head"><span>Source name</span><span>New name</span></div>
      {columnNames.map((column) => <div className="config-table-row" key={column}><code>{column}</code><input value={String(complete[column])} onChange={(event) => onChange({ renames: { ...complete, [column]: event.target.value } })} disabled={disabled} /></div>)}
      {!columnNames.length && <div className="config-empty">Upstream schema is not available.</div>}
    </div>;
  }
  if (type === "filter_rows") {
    return <FilterEditor config={config} columns={availableColumns} sourceDatasetIds={sourceDatasetIds} disabled={disabled} onChange={onChange} />;
  }
  if (type === "cast_columns") {
    return <CastEditor casts={recordValue(config.casts)} columns={availableColumns} disabled={disabled} onChange={(casts) => onChange({ casts })} />;
  }
  if (type === "impute_missing") {
    return <ImputeRulesEditor config={config} columns={availableColumns} disabled={disabled} onChange={onChange} />;
  }
  if (type === "sort_rows") {
    return <SortEditor rules={recordList(config.columns)} columns={columnNames} disabled={disabled} onChange={(columns) => onChange({ columns })} />;
  }
  if (type === "derive_column") {
    const expression = recordValue(config.expression);
    const left = recordValue(expression.left);
    const right = recordValue(expression.right);
    const rightIsColumn = "column" in right;
    return <div className="inspector-form">
      <TextField label="New column name" value={String(config.name ?? "")} onChange={(name) => onChange({ ...config, name })} disabled={disabled} />
      <ColumnSelect label="Left column" value={String(left.column ?? "")} columns={columnNames} onChange={(column) => onChange({ ...config, expression: { ...expression, left: { column } } })} disabled={disabled} />
      <label>Operation<select value={String(expression.operator ?? "multiply")} onChange={(event) => onChange({ ...config, expression: { ...expression, operator: event.target.value } })} disabled={disabled}>{deriveOperators(availableColumns.find((column) => column.name === left.column)).map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>Right operand type<select value={rightIsColumn ? "column" : "literal"} onChange={(event) => onChange({ ...config, expression: { ...expression, right: event.target.value === "column" ? { column: columnNames[0] ?? "" } : { literal: 1 } } })} disabled={disabled}><option value="literal">Fixed value</option><option value="column">Another column</option></select></label>
      {rightIsColumn
        ? <ColumnSelect label="Right column" value={String(right.column ?? "")} columns={columnNames} onChange={(column) => onChange({ ...config, expression: { ...expression, right: { column } } })} disabled={disabled} />
        : <TextField label="Fixed value" value={String(right.literal ?? "")} onChange={(value) => onChange({ ...config, expression: { ...expression, right: { literal: parseScalar(value) } } })} disabled={disabled} />}
    </div>;
  }
  if (type === "aggregate") {
    return <AggregateEditor config={config} columns={availableColumns} disabled={disabled} onChange={onChange} />;
  }
  if (type === "join") {
    return <JoinEditor config={config} leftColumns={inputColumns[0] ?? []} rightColumns={inputColumns[1] ?? []} disabled={disabled} onChange={onChange} />;
  }
  if (type === "map_categories") {
    const categoryColumnNames = categoricalColumns(availableColumns).map((column) => column.name);
    const selectedCategoryColumn = categoryColumnNames.includes(String(config.column ?? "")) ? String(config.column) : "";
    return <div className="inspector-form">
      <ColumnSelect label="Category column" value={selectedCategoryColumn} columns={categoryColumnNames} onChange={(column) => onChange({ ...config, column })} disabled={disabled} />
      {!selectedCategoryColumn && <small className="metadata-hint">Choose a category column first. Then source-value mapping will show searchable values from that column.</small>}
      <TextField label="Optional output column" value={String(config.output_column ?? "")} onChange={(value) => onChange(value ? { ...config, output_column: value } : withoutKey(config, "output_column"))} disabled={disabled} />
      <CategoryMappingEditor datasetIds={sourceDatasetIds} column={selectedCategoryColumn} values={sanitizeCategoryMapping(recordValue(config.mapping))} disabled={disabled || !selectedCategoryColumn} onChange={(mapping) => onChange({ ...config, mapping })} />
    </div>;
  }
  if (type === "union") {
    return <label className="toggle-control"><input type="checkbox" checked={config.by_name !== false} onChange={(event) => onChange({ by_name: event.target.checked })} disabled={disabled} /><span><strong>Align columns by name</strong><small>Recommended when input column order can differ.</small></span></label>;
  }
  return null;
}

function ColumnMultiSelect({ label, hint, columns, selected, onChange, disabled }: {
  label: string; hint?: string; columns: string[]; selected: string[]; onChange: (columns: string[]) => void; disabled: boolean;
}) {
  const [search, setSearch] = useState("");
  const visible = columns.filter((column) => column.toLowerCase().includes(search.toLowerCase()));
  return <div className="column-picker"><label>{label}</label>{hint && <small>{hint}</small>}
    <details><summary>{selected.length ? `${selected.length} of ${columns.length} selected` : "Choose columns"}</summary>
      <div className="column-picker-popover">
        <input placeholder="Search columns…" value={search} onChange={(event) => setSearch(event.target.value)} disabled={disabled} />
        <div className="column-picker-actions"><button type="button" onClick={() => onChange([...columns])} disabled={disabled}>Select all</button><button type="button" onClick={() => onChange([])} disabled={disabled}>Unselect all</button></div>
        <div className="column-checkbox-list">{visible.map((column) => <label key={column}><input type="checkbox" checked={selected.includes(column)} onChange={(event) => onChange(event.target.checked ? [...selected, column] : selected.filter((item) => item !== column))} disabled={disabled} /><span>{column}</span></label>)}</div>
      </div>
    </details>
  </div>;
}

function FilterEditor({ config, columns, sourceDatasetIds, disabled, onChange }: {
  config: Record<string, unknown>; columns: PipelineColumn[]; sourceDatasetIds: string[]; disabled: boolean; onChange: (config: Record<string, unknown>) => void;
}) {
  const columnNames = columns.map((column) => column.name);
  const mode = String(config.mode ?? "visual");
  const conditions = recordList(config.conditions);
  const setConditions = (next: Array<Record<string, unknown>>) => onChange({ mode: "visual", combine: config.combine ?? "and", conditions: next });
  return <div className="filter-editor">
    <div className="segmented-control"><button type="button" className={mode === "visual" ? "active" : ""} onClick={() => onChange({ mode: "visual", combine: "and", conditions: conditions.length ? conditions : [{ column: columnNames[0] ?? "", operator: defaultOperator(columns[0]), value: "" }] })}>Condition builder</button><button type="button" className={mode === "sql" ? "active" : ""} onClick={() => onChange({ mode: "sql", sql: String(config.sql ?? "") })}>SQL WHERE</button></div>
    {mode === "sql" ? <SqlExpressionEditor title="WHERE condition" hint="Click a column or operator to insert it at the cursor." value={String(config.sql ?? "")} columns={columns} disabled={disabled} onChange={(sql) => onChange({ mode: "sql", sql })} /> : <>
      <label>Match<select value={String(config.combine ?? "and")} onChange={(event) => onChange({ ...config, combine: event.target.value })} disabled={disabled}><option value="and">All conditions (AND)</option><option value="or">Any condition (OR)</option></select></label>
      <div className="condition-list">{conditions.map((condition, index) => {
        const column = columns.find((item) => item.name === condition.column) ?? columns[0];
        const operators = operatorsForColumn(column);
        const operator = operators.some(([value]) => value === condition.operator) ? String(condition.operator) : defaultOperator(column);
        const updateCondition = (patch: Record<string, unknown>) => setConditions(conditions.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
        return <div className="condition-card" key={index}>
          <div className="condition-row">
            <ColumnSelect value={String(condition.column ?? "")} columns={columnNames} onChange={(name) => {
              const nextColumn = columns.find((item) => item.name === name);
              updateCondition({ column: name, operator: defaultOperator(nextColumn), value: "", values: [] });
            }} disabled={disabled} />
            <select value={operator} onChange={(event) => updateCondition({ operator: event.target.value, value: "", values: [] })} disabled={disabled}>{operators.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select>
            {!["is_null", "not_null"].includes(operator) && <FilterValueInput datasetId={sourceDatasetIds[0]} column={column} operator={operator} condition={condition} disabled={disabled} onChange={updateCondition} />}
            <button className="icon-button" type="button" onClick={() => setConditions(conditions.filter((_, itemIndex) => itemIndex !== index))} disabled={disabled || conditions.length === 1}><Trash2 size={14} /></button>
          </div>
          {column && <small className="metadata-hint">{column.type}{column.role ? ` · ${column.role.replaceAll("_", " ")}` : ""}</small>}
        </div>;
      })}</div>
      <button className="secondary-button compact-button" type="button" onClick={() => setConditions([...conditions, { column: columnNames[0] ?? "", operator: defaultOperator(columns[0]), value: "" }])} disabled={disabled}><Plus size={14} /> Add condition</button>
    </>}
  </div>;
}

function SqlExpressionEditor({ title, hint, value, columns, disabled, onChange, fullQuery = false }: {
  title: string; hint: string; value: string; columns: PipelineColumn[]; disabled: boolean; onChange: (value: string) => void; fullQuery?: boolean;
}) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const insert = (token: string) => {
    const element = textarea.current;
    const start = element?.selectionStart ?? value.length;
    const end = element?.selectionEnd ?? value.length;
    const before = start > 0 && !/\s/.test(value[start - 1] ?? "") ? " " : "";
    const after = end < value.length && !/\s/.test(value[end] ?? "") ? " " : "";
    onChange(`${value.slice(0, start)}${before}${token}${after}${value.slice(end)}`);
    requestAnimationFrame(() => {
      const cursor = start + before.length + token.length + after.length;
      textarea.current?.focus();
      textarea.current?.setSelectionRange(cursor, cursor);
    });
  };
  return <div className={fullQuery ? "sql-editor metadata-sql-editor" : "sql-where-editor metadata-sql-editor"}>
    <div className="sql-editor-heading"><Code2 size={17} /><div><strong>{title}</strong><span>{hint}</span></div></div>
    <div className="sql-helper"><span>Columns</span><div className="sql-token-list">{columns.map((column) => <button className="sql-token" type="button" key={column.name} onClick={() => insert(quoteSqlIdentifier(column.name))} disabled={disabled} title={`${column.type}${column.role ? ` · ${column.role}` : ""}`}>{column.name}<small>{column.type}</small></button>)}</div>
      {!fullQuery && <><span>Operators</span><div className="sql-token-list">{["=", "<>", ">", ">=", "<", "<=", "AND", "OR", "IN ()", "IS NULL", "IS NOT NULL", "LIKE"].map((token) => <button className="sql-token operator" type="button" key={token} onClick={() => insert(token)} disabled={disabled}>{token}</button>)}</div></>}
    </div>
    <textarea ref={textarea} value={value} onChange={(event) => onChange(event.target.value)} placeholder={fullQuery ? "SELECT *\nFROM input" : "\"species\" = 'setosa' AND \"sepal_length\" > 5"} disabled={disabled} spellCheck={false} />
    <p className="security-note">{fullQuery ? "One controlled SELECT/WITH query. No files, URLs, DDL, DML or Python." : "Enter only the predicate after WHERE. Subqueries and additional SQL clauses are blocked."}</p>
  </div>;
}

function FilterValueInput({ datasetId, column, operator, condition, disabled, onChange }: {
  datasetId?: string; column?: PipelineColumn; operator: string; condition: Record<string, unknown>; disabled: boolean; onChange: (patch: Record<string, unknown>) => void;
}) {
  const categorical = isCategorical(column);
  const { options, truncated, loading } = useColumnValues(datasetId, column?.name, categorical);
  if (categorical && ["in", "not_in"].includes(operator)) {
    const selected = stringList(condition.values);
    return <details className="value-picker"><summary>{selected.length ? `${selected.length} selected` : loading ? "Loading values..." : "Choose values"}</summary><div className="value-picker-popover">
      <div className="value-picker-actions"><button type="button" onClick={() => onChange({ values: [...options] })} disabled={disabled || !options.length}>Select all</button><button type="button" onClick={() => onChange({ values: [] })} disabled={disabled || !selected.length}>Clear</button></div>
      <div className="value-checkbox-list">{options.map((option) => <label key={option}><input type="checkbox" checked={selected.includes(option)} onChange={(event) => onChange({ values: event.target.checked ? [...selected, option] : selected.filter((item) => item !== option) })} disabled={disabled} /><span>{option}</span></label>)}</div>
      {!options.length && !loading && <small>No bounded value list available.</small>}
      {truncated && <small>Showing 100 most frequent values from the full dataset.</small>}
    </div></details>;
  }
  if (categorical) {
    const listId = `filter-values-${safeDomId(datasetId)}-${safeDomId(column?.name)}`;
    return <div className="value-combobox"><input value={String(condition.value ?? "")} onChange={(event) => onChange({ value: parseScalar(event.target.value) })} list={listId} placeholder={loading ? "Loading values…" : "Choose or type"} disabled={disabled} /><datalist id={listId}>{options.map((option) => <option key={option} value={option} />)}</datalist>{truncated && <small>Top 100</small>}</div>;
  }
  const inputType = column?.type === "number" ? "number" : column?.type === "date" ? "datetime-local" : "text";
  return <input type={inputType} value={String(condition.value ?? "")} onChange={(event) => onChange({ value: parseScalar(event.target.value) })} placeholder="value" disabled={disabled} />;
}

function LegacyFilterEditor({ config, columns, disabled, onChange }: {
  config: Record<string, unknown>; columns: string[]; disabled: boolean; onChange: (config: Record<string, unknown>) => void;
}) {
  const mode = String(config.mode ?? "visual");
  const conditions = recordList(config.conditions);
  const setConditions = (next: Array<Record<string, unknown>>) => onChange({ mode: "visual", combine: config.combine ?? "and", conditions: next });
  return <div className="filter-editor">
    <div className="segmented-control"><button type="button" className={mode === "visual" ? "active" : ""} onClick={() => onChange({ mode: "visual", combine: "and", conditions: conditions.length ? conditions : [{ column: columns[0] ?? "", operator: "eq", value: "" }] })}>Condition builder</button><button type="button" className={mode === "sql" ? "active" : ""} onClick={() => onChange({ mode: "sql", sql: String(config.sql ?? "") })}>SQL WHERE</button></div>
    {mode === "sql" ? <div className="sql-where-editor"><label>WHERE condition<textarea value={String(config.sql ?? "")} onChange={(event) => onChange({ mode: "sql", sql: event.target.value })} placeholder="species = 'setosa' AND sepal_length > 5" disabled={disabled} /></label><small>Enter only the predicate after WHERE. Subqueries and additional SQL clauses are blocked.</small></div> : <>
      <label>Match<select value={String(config.combine ?? "and")} onChange={(event) => onChange({ ...config, combine: event.target.value })} disabled={disabled}><option value="and">All conditions (AND)</option><option value="or">Any condition (OR)</option></select></label>
      <div className="condition-list">{conditions.map((condition, index) => {
        const operator = String(condition.operator ?? "eq");
        return <div className="condition-row" key={index}><ColumnSelect value={String(condition.column ?? "")} columns={columns} onChange={(column) => setConditions(conditions.map((item, itemIndex) => itemIndex === index ? { ...item, column } : item))} disabled={disabled} /><select value={operator} onChange={(event) => setConditions(conditions.map((item, itemIndex) => itemIndex === index ? { ...item, operator: event.target.value } : item))} disabled={disabled}>{[["eq", "="], ["ne", "≠"], ["gt", ">"], ["gte", "≥"], ["lt", "<"], ["lte", "≤"], ["in", "in list"], ["is_null", "is empty"], ["not_null", "is not empty"]].map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select>{!["is_null", "not_null"].includes(operator) && <input value={operator === "in" ? stringList(condition.values).join(", ") : String(condition.value ?? "")} onChange={(event) => setConditions(conditions.map((item, itemIndex) => itemIndex === index ? (operator === "in" ? { column: item.column, operator, values: splitComma(event.target.value).map(parseScalar) } : { column: item.column, operator, value: parseScalar(event.target.value) }) : item))} placeholder={operator === "in" ? "a, b, c" : "value"} disabled={disabled} />}<button className="icon-button" type="button" onClick={() => setConditions(conditions.filter((_, itemIndex) => itemIndex !== index))} disabled={disabled || conditions.length === 1}><Trash2 size={14} /></button></div>;
      })}</div>
      <button className="secondary-button compact-button" type="button" onClick={() => setConditions([...conditions, { column: columns[0] ?? "", operator: "eq", value: "" }])} disabled={disabled}><Plus size={14} /> Add condition</button>
    </>}
  </div>;
}

function ColumnSelect({ label, value, columns, onChange, disabled }: {
  label?: string; value: string; columns: string[]; onChange: (value: string) => void; disabled: boolean;
}) {
  const select = <select value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled}><option value="">Choose column</option>{columns.map((column) => <option key={column} value={column}>{column}</option>)}</select>;
  return label ? <label>{label}{select}</label> : select;
}

function CastEditor({ casts, columns, disabled, onChange }: { casts: Record<string, unknown>; columns: PipelineColumn[]; disabled: boolean; onChange: (casts: Record<string, unknown>) => void; }) {
  const types = ["BOOLEAN", "INTEGER", "BIGINT", "DOUBLE", "DECIMAL", "VARCHAR", "DATE", "TIMESTAMP", "TIMESTAMPTZ"];
  return <div className="config-table"><div className="config-table-head three"><span>Cast</span><span>Column / source type</span><span>Target type</span></div>{columns.map((column) => <div className="config-table-row three" key={column.name}><input type="checkbox" checked={column.name in casts} onChange={(event) => { const next = { ...casts }; if (event.target.checked) next[column.name] = suggestedDuckDbType(column.type); else delete next[column.name]; onChange(next); }} disabled={disabled || (column.name in casts && Object.keys(casts).length === 1)} /><code>{column.name}<small>{column.type}</small></code><select value={String(casts[column.name] ?? suggestedDuckDbType(column.type))} onChange={(event) => onChange({ ...casts, [column.name]: event.target.value })} disabled={disabled || !(column.name in casts)}>{types.map((type) => <option key={type}>{type}</option>)}</select></div>)}</div>;
}

function ImputeRulesEditor({ config, columns, disabled, onChange }: { config: Record<string, unknown>; columns: PipelineColumn[]; disabled: boolean; onChange: (config: Record<string, unknown>) => void; }) {
  const rules = normalizeImputeRules(config, columns);
  const byColumn = new Map(rules.map((rule) => [String(rule["column"]), rule]));
  const setRule = (column: PipelineColumn, patch: Record<string, unknown>) => {
    const existing = byColumn.get(column.name) ?? { column: column.name, method: defaultImputeMethod(column), value: defaultValueForType(column.type), add_indicator: false };
    onChange({ rules: [...rules.filter((rule) => rule["column"] !== column.name), { ...existing, ...patch }] });
  };
  const removeRule = (column: string) => onChange({ rules: rules.filter((rule) => rule["column"] !== column) });
  return <div className="config-table impute-table">
    <div className="config-table-head impute-row"><span>Apply</span><span>Column / type</span><span>Method</span><span>Value</span><span>Indicator</span></div>
    {columns.map((column) => {
      const rule = byColumn.get(column.name);
      const enabled = Boolean(rule);
      const method = String(rule?.method ?? defaultImputeMethod(column));
      const needsValue = ["fixed", "constant"].includes(method);
      return <div className="config-table-row impute-row" key={column.name}>
        <input type="checkbox" checked={enabled} onChange={(event) => event.target.checked ? setRule(column, {}) : removeRule(column.name)} disabled={disabled || (enabled && rules.length === 1)} />
        <code>{column.name}<small>{column.type}</small></code>
        <select value={method} onChange={(event) => {
          const nextMethod = event.target.value;
          const patch: Record<string, unknown> = { method: nextMethod };
          if (["fixed", "constant"].includes(nextMethod)) patch.value = rule?.value ?? defaultValueForType(column.type);
          else patch.value = undefined;
          setRule(column, patch);
        }} disabled={disabled || !enabled}>
          {imputeMethodOptions(column).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        {needsValue ? (
          column.type === "boolean"
            ? <select value={String(rule?.value ?? "false")} onChange={(event) => setRule(column, { value: event.target.value === "true" })} disabled={disabled || !enabled}><option value="false">false</option><option value="true">true</option></select>
            : <input type={column.type === "number" ? "number" : column.type === "date" ? "datetime-local" : "text"} value={String(rule?.value ?? "")} onChange={(event) => setRule(column, { value: parseScalar(event.target.value) })} disabled={disabled || !enabled} />
        ) : <span className="metadata-hint">{method === "drop_rows" ? "filters rows" : "computed"}</span>}
        <input type="checkbox" checked={Boolean(rule?.add_indicator)} onChange={(event) => setRule(column, { add_indicator: event.target.checked })} disabled={disabled || !enabled} title={`Add ${column.name}__was_missing`} />
      </div>;
    })}
    {!columns.length && <div className="config-empty">Upstream schema is not available.</div>}
  </div>;
}

function SortEditor({ rules, columns, disabled, onChange }: { rules: Array<Record<string, unknown>>; columns: string[]; disabled: boolean; onChange: (rules: Array<Record<string, unknown>>) => void; }) {
  return <div className="row-editor"><div className="config-table-head"><span>Column</span><span>Direction</span></div>{rules.map((rule, index) => <div className="condition-row compact" key={index}><ColumnSelect value={String(rule.column ?? "")} columns={columns} onChange={(column) => onChange(rules.map((item, itemIndex) => itemIndex === index ? { ...item, column } : item))} disabled={disabled} /><select value={String(rule.direction ?? "asc")} onChange={(event) => onChange(rules.map((item, itemIndex) => itemIndex === index ? { ...item, direction: event.target.value } : item))} disabled={disabled}><option value="asc">Ascending</option><option value="desc">Descending</option></select><button className="icon-button" type="button" onClick={() => onChange(rules.filter((_, itemIndex) => itemIndex !== index))} disabled={disabled || rules.length === 1}><Trash2 size={14} /></button></div>)}<button className="secondary-button compact-button" type="button" onClick={() => onChange([...rules, { column: columns[0] ?? "", direction: "asc" }])} disabled={disabled}><Plus size={14} /> Add sort level</button></div>;
}

function IdentifierEditor({ config, columns, disabled, onChange }: {
  config: Record<string, unknown>;
  columns: string[];
  disabled: boolean;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const mode = String(config.mode ?? "record_hash");
  const modes = [
    {
      id: "record_hash",
      label: "Hash entire record",
      description: "SHA-256 over every upstream column. Identical records receive the same identifier."
    },
    {
      id: "columns_hash",
      label: "Hash selected columns",
      description: "SHA-256 over a chosen business key or a stable combination of columns."
    },
    {
      id: "sequence",
      label: "Ordered sequence",
      description: "Consecutive BIGINT values assigned using an explicit, reproducible sort order."
    }
  ];
  const setMode = (nextMode: string) => {
    const common = { mode: nextMode, output_column: String(config.output_column ?? "row_id") };
    if (nextMode === "columns_hash") {
      onChange({ ...common, columns: stringList(config.columns).length ? stringList(config.columns) : columns.slice(0, 1) });
    } else if (nextMode === "sequence") {
      onChange({
        ...common,
        order_by: recordList(config.order_by).length
          ? recordList(config.order_by)
          : [{ column: columns[0] ?? "", direction: "asc" }],
        start: Number.isInteger(config.start) ? config.start : 1
      });
    } else {
      onChange(common);
    }
  };

  return <div className="identifier-editor">
    <div className="identifier-mode-grid">
      {modes.map((item) => <label className={`identifier-mode-card ${mode === item.id ? "selected" : ""}`} key={item.id}>
        <input
          type="radio"
          name="identifier-mode"
          value={item.id}
          checked={mode === item.id}
          onChange={() => setMode(item.id)}
          disabled={disabled}
        />
        <span><strong>{item.label}</strong><small>{item.description}</small></span>
      </label>)}
    </div>
    <TextField
      label="Identifier column name"
      value={String(config.output_column ?? "row_id")}
      onChange={(output_column) => onChange({ ...config, output_column })}
      disabled={disabled}
    />
    {mode === "columns_hash" && <ColumnMultiSelect
      label="Columns forming the identifier"
      hint="Column order is part of the definition. NULL values and field boundaries are encoded unambiguously."
      columns={columns}
      selected={stringList(config.columns)}
      onChange={(selected) => onChange({ ...config, columns: selected })}
      disabled={disabled}
    />}
    {mode === "sequence" && <div className="identifier-sequence">
      <label>
        First number
        <input
          type="number"
          min={0}
          step={1}
          value={Number(config.start ?? 1)}
          onChange={(event) => onChange({ ...config, start: Math.max(0, Math.trunc(Number(event.target.value) || 0)) })}
          disabled={disabled}
        />
      </label>
      <SortEditor
        rules={recordList(config.order_by)}
        columns={columns}
        onChange={(order_by) => onChange({ ...config, order_by })}
        disabled={disabled}
      />
      <small className="identifier-warning">
        The sort columns must uniquely order rows. Ties can make sequence identifiers unstable between runs.
      </small>
    </div>}
    {mode === "record_hash" && <small className="identifier-warning">
      Exact duplicate records intentionally receive the same identifier.
    </small>}
  </div>;
}

function AggregateEditor({ config, columns, disabled, onChange }: { config: Record<string, unknown>; columns: PipelineColumn[]; disabled: boolean; onChange: (config: Record<string, unknown>) => void; }) {
  const aggregations = recordList(config.aggregations);
  const names = columns.map((column) => column.name);
  return <div className="row-editor"><ColumnMultiSelect label="Group by columns" columns={names} selected={stringList(config.group_by)} onChange={(group_by) => onChange({ ...config, group_by })} disabled={disabled} /><div className="config-table-head three"><span>Column</span><span>Function</span><span>Output name</span></div>{aggregations.map((aggregation, index) => {
    const selected = columns.find((column) => column.name === aggregation.column);
    const functions = aggregateFunctions(selected);
    return <div className="aggregation-row" key={index}><select value={String(aggregation.column ?? "*")} onChange={(event) => onChange({ ...config, aggregations: aggregations.map((item, itemIndex) => itemIndex === index ? { ...item, column: event.target.value, function: event.target.value === "*" ? "count" : aggregateFunctions(columns.find((column) => column.name === event.target.value))[0] } : item) })} disabled={disabled}><option value="*">* rows</option>{columns.map((column) => <option key={column.name} value={column.name}>{column.name} · {column.type}</option>)}</select><select value={functions.includes(String(aggregation.function)) ? String(aggregation.function) : functions[0]} onChange={(event) => onChange({ ...config, aggregations: aggregations.map((item, itemIndex) => itemIndex === index ? { ...item, function: event.target.value } : item) })} disabled={disabled}>{functions.map((item) => <option key={item}>{item}</option>)}</select><input value={String(aggregation.alias ?? "metric")} onChange={(event) => onChange({ ...config, aggregations: aggregations.map((item, itemIndex) => itemIndex === index ? { ...item, alias: event.target.value } : item) })} disabled={disabled} /><button className="icon-button" type="button" onClick={() => onChange({ ...config, aggregations: aggregations.filter((_, itemIndex) => itemIndex !== index) })}><Trash2 size={14} /></button></div>;
  })}<button className="secondary-button compact-button" type="button" onClick={() => onChange({ ...config, aggregations: [...aggregations, { column: "*", function: "count", alias: `metric_${aggregations.length + 1}` }] })}><Plus size={14} /> Add metric</button></div>;
}

function DataContractEditor({
  contract,
  columns,
  disabled,
  onChange
}: {
  contract?: DataContractDefinition;
  columns: PipelineColumn[];
  disabled: boolean;
  onChange: (contract: DataContractDefinition | undefined) => void;
}) {
  if (!contract) {
    return (
      <div className="data-contract-editor">
        <div><strong>Data contract</strong><small>{columns.length ? "Synchronizing the contract with the DAG output schema…" : "Output schema is not available yet. Configure the DAG source and operations first."}</small></div>
      </div>
    );
  }

  const updateColumn = (index: number, patch: Partial<DataContractDefinition["columns"][number]>) => {
    onChange({
      ...contract,
      columns: contract.columns.map((column, itemIndex) =>
        itemIndex === index ? { ...column, ...patch } : column
      )
    });
  };
  return (
    <div className="data-contract-editor">
      <div className="data-contract-heading">
        <div><strong>Data contract</strong><small>{contract.columns.length} columns inferred from the DAG. Names and types follow the output automatically.</small></div>
        <span className="scope-badge">DAG synchronized</span>
      </div>
      <div className="data-contract-options">
        <label>Schema drift<select value={contract.schema_drift_policy} disabled={disabled} onChange={(event) => onChange({ ...contract, schema_drift_policy: event.target.value as "fail" | "warn" })}><option value="fail">Fail run</option><option value="warn">Warn</option></select></label>
        <label className="checkbox-label"><input type="checkbox" checked={contract.allow_unexpected_columns} disabled={disabled} onChange={(event) => onChange({ ...contract, allow_unexpected_columns: event.target.checked })} /> Allow extra columns</label>
      </div>
      <div className="contract-rule-list">
        {contract.columns.map((column, index) => (
          <div className="contract-rule" key={`${column.name}-${index}`}>
            <div className="contract-rule-primary">
              <div className="contract-inferred-field"><span>Column from DAG</span><strong>{column.name}</strong></div>
              <div className="contract-inferred-field"><span>Inferred type</span><code>{column.type}</code></div>
              <label><span>On violation</span><select value={column.policy} disabled={disabled} onChange={(event) => updateColumn(index, { policy: event.target.value as "fail" | "warn" | "reject" })}><option value="fail">Fail run</option><option value="warn">Warn</option><option value="reject">Reject row</option></select></label>
            </div>
            <div className="contract-rule-constraints">
              <label className="checkbox-label"><input type="checkbox" checked={column.nullable} disabled={disabled} onChange={(event) => updateColumn(index, { nullable: event.target.checked })} /> Nullable</label>
              <label className="checkbox-label"><input type="checkbox" checked={column.unique} disabled={disabled} onChange={(event) => updateColumn(index, { unique: event.target.checked })} /> Unique</label>
              <label><span>Minimum</span><input type="number" placeholder={contractTypeSupportsRange(column.type) ? "No minimum" : "Numeric only"} value={column.minimum ?? ""} disabled={disabled || !contractTypeSupportsRange(column.type)} onChange={(event) => updateColumn(index, { minimum: event.target.value === "" ? undefined : Number(event.target.value) })} /></label>
              <label><span>Maximum</span><input type="number" placeholder={contractTypeSupportsRange(column.type) ? "No maximum" : "Numeric only"} value={column.maximum ?? ""} disabled={disabled || !contractTypeSupportsRange(column.type)} onChange={(event) => updateColumn(index, { maximum: event.target.value === "" ? undefined : Number(event.target.value) })} /></label>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function synchronizeDataContract(
  current: DataContractDefinition | undefined,
  columns: DatasetColumn[]
): DataContractDefinition {
  const existing = new Map(current?.columns.map((column) => [column.name, column]) ?? []);
  return {
    schema_drift_policy: current?.schema_drift_policy ?? "fail",
    allow_unexpected_columns: current?.allow_unexpected_columns ?? false,
    columns: columns.map((column) => {
      const previous = existing.get(column.name);
      const type = column.storage_type || contractColumnType(column.type);
      const supportsRange = column.type === "number";
      return {
        name: column.name,
        type,
        nullable: previous?.nullable ?? true,
        unique: previous?.unique ?? false,
        policy: previous?.policy ?? "fail",
        ...(supportsRange && previous?.minimum !== undefined ? { minimum: previous.minimum } : {}),
        ...(supportsRange && previous?.maximum !== undefined ? { maximum: previous.maximum } : {}),
        ...(previous?.allowed_values ? { allowed_values: previous.allowed_values } : {})
      };
    })
  };
}

function contractColumnType(type: DatasetColumn["type"]) {
  if (type === "number") return "DOUBLE";
  if (type === "date") return "TIMESTAMP";
  if (type === "boolean") return "BOOLEAN";
  return "VARCHAR";
}

function contractTypeSupportsRange(type: string) {
  return ["TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL"]
    .some((token) => type.toUpperCase().includes(token));
}

function JoinEditor({ config, leftColumns, rightColumns, disabled, onChange }: { config: Record<string, unknown>; leftColumns: PipelineColumn[]; rightColumns: PipelineColumn[]; disabled: boolean; onChange: (config: Record<string, unknown>) => void; }) {
  const keys = recordList(config.keys);
  const leftNames = leftColumns.map((column) => column.name);
  const rightNames = rightColumns.map((column) => column.name);
  return <div className="row-editor"><label>Join type<select value={String(config.join_type ?? "inner")} onChange={(event) => onChange({ ...config, join_type: event.target.value })} disabled={disabled}>{["inner", "left", "right", "full"].map((item) => <option key={item}>{item}</option>)}</select></label><div className="config-table-head"><span>Left key</span><span>Right key</span></div>{keys.map((key, index) => {
    const left = leftColumns.find((column) => column.name === key.left);
    const compatibleRight = rightColumns.filter((column) => !left || compatibleTypes(left.type, column.type)).map((column) => column.name);
    return <div className="condition-card" key={index}><div className="condition-row compact"><ColumnSelect value={String(key.left ?? "")} columns={leftNames} onChange={(leftKey) => onChange({ ...config, keys: keys.map((item, itemIndex) => itemIndex === index ? { ...item, left: leftKey, right: suggestJoinKey(leftKey, rightColumns) } : item) })} disabled={disabled} /><ColumnSelect value={String(key.right ?? "")} columns={compatibleRight.length ? compatibleRight : rightNames} onChange={(right) => onChange({ ...config, keys: keys.map((item, itemIndex) => itemIndex === index ? { ...item, right } : item) })} disabled={disabled} /><button className="icon-button" type="button" onClick={() => onChange({ ...config, keys: keys.filter((_, itemIndex) => itemIndex !== index) })}><Trash2 size={14} /></button></div>{left && <small className="metadata-hint">Matching {left.type} keys; incompatible right-side types are hidden.</small>}</div>;
  })}<button className="secondary-button compact-button" type="button" onClick={() => onChange({ ...config, keys: [...keys, { left: leftNames[0] ?? "", right: suggestJoinKey(leftNames[0] ?? "", rightColumns) }] })}><Plus size={14} /> Add key pair</button></div>;
}

function CategoryMappingEditor({ datasetIds, column, values, disabled, onChange }: {
  datasetIds: string[]; column: string; values: Record<string, unknown>; disabled: boolean; onChange: (values: Record<string, unknown>) => void;
}) {
  const { options, truncated, loading, error } = useColumnValues(
    datasetIds,
    column,
    Boolean(column)
  );
  if (!column) {
    return <div className="inspector-empty compact">Select a category column to enable searchable source-value suggestions.</div>;
  }
  return <div className="row-editor">
    <PairTable leftLabel="Source value" rightLabel="New value" values={values} disabled={disabled} onChange={onChange} suggestions={options} />
    {loading && <small className="metadata-hint">Loading category values from the full dataset…</small>}
    {!loading && !options.length && <small className="metadata-hint">
      {error || "No value list is available for this column yet. You can still type values manually."}
    </small>}
    {truncated && <small className="metadata-hint">Suggestions show the 100 most frequent values from the full dataset.</small>}
  </div>;
}

function PairTable({ leftLabel, rightLabel, values, disabled, onChange, suggestions = [] }: { leftLabel: string; rightLabel: string; values: Record<string, unknown>; disabled: boolean; onChange: (values: Record<string, unknown>) => void; suggestions?: string[]; }) {
  const rows = Object.entries(values);
  const rowIds = useRef(new Map<string, string>());
  const nextRowId = useRef(1);
  for (const [key] of rows) {
    if (!rowIds.current.has(key)) {
      rowIds.current.set(key, `mapping-row-${nextRowId.current++}`);
    }
  }
  const addMapping = () => {
    const suggested = suggestions.find((item) => !(item in values));
    const key = suggested ?? ("" in values ? `manual_${rows.length + 1}` : "");
    if (!rowIds.current.has(key)) {
      rowIds.current.set(key, `mapping-row-${nextRowId.current++}`);
    }
    onChange({ ...values, [key]: "" });
  };
  return <div className="row-editor"><div className="config-table-head"><span>{leftLabel}</span><span>{rightLabel}</span></div>{rows.map(([key, value]) => <div className="pair-row" key={rowIds.current.get(key)}>
    <MappingValueCombobox value={key} suggestions={suggestions} disabled={disabled} onChange={(nextKey) => {
      const rowId = rowIds.current.get(key);
      const next = { ...values };
      delete next[key];
      next[nextKey] = value;
      rowIds.current.delete(key);
      if (rowId) rowIds.current.set(nextKey, rowId);
      onChange(next);
    }} />
    <input value={String(value ?? "")} onChange={(event) => onChange({ ...values, [key]: parseScalar(event.target.value) })} disabled={disabled} />
    <button className="icon-button" type="button" onClick={() => {
      const next = { ...values };
      delete next[key];
      rowIds.current.delete(key);
      onChange(next);
    }}><Trash2 size={14} /></button>
  </div>)}{!rows.length && <div className="config-empty">No mappings yet. Add a row and choose a source value from suggestions or type one manually.</div>}<button className="secondary-button compact-button" type="button" onClick={addMapping} disabled={disabled}><Plus size={14} /> Add mapping</button></div>;
}

function MappingValueCombobox({ value, suggestions, disabled, onChange }: { value: string; suggestions: string[]; disabled: boolean; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const query = value.toLowerCase();
  const filtered = suggestions
    .filter((item) => item.toLowerCase().includes(query))
    .slice(0, 100);
  return <div className="mapping-combobox">
    <input value={value} onFocus={() => setOpen(true)} onChange={(event) => { onChange(event.target.value); setOpen(true); }} onBlur={() => window.setTimeout(() => setOpen(false), 120)} placeholder="Choose or type value" disabled={disabled} />
    {open && !disabled && suggestions.length > 0 && (
      <div className="mapping-combobox-list">
        {filtered.map((item) => <button key={item} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(item); setOpen(false); }}>{item}</button>)}
        {!filtered.length && <small>No values contain "{value}". You can keep the typed value.</small>}
      </div>
    )}
  </div>;
}

function TextField({
  label,
  value,
  onChange,
  disabled,
  textarea = false,
  list
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  textarea?: boolean;
  list?: string;
}) {
  return (
    <label>
      {label}
      {textarea ? (
        <textarea className="compact-textarea mapping-input" value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} />
      ) : (
        <input value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} list={list} />
      )}
    </label>
  );
}

function SchemaSummary({ dataset, columns }: { dataset: DataAsset; columns: DatasetColumn[] }) {
  return (
    <div className="source-schema">
      <span>{dataset.row_count ?? "?"} rows · {columns.length} columns</span>
      <div>
        {columns.slice(0, 12).map((column) => <code key={column.name}>{column.name} <small>{column.type}</small></code>)}
        {columns.length > 12 && <code>+{columns.length - 12} more</code>}
      </div>
    </div>
  );
}

type SourceOption = { reference: PipelinePortReference; label: string };

function availableSources(definition: PipelineDefinition, beforeStepIndex?: number): SourceOption[] {
  const inputs = definition.inputs.map((input) => ({
    reference: { node_id: input.input_id, port_id: input.output_port_id },
    label: `Source · ${input.input_id}`
  }));
  const steps = definition.steps
    .slice(0, beforeStepIndex ?? definition.steps.length)
    .map((step, index) => ({
      reference: { node_id: step.step_id, port_id: step.output_port_id },
      label: `Block ${index + 1} · ${stepOptions.find((item) => item.type === step.type)?.label ?? step.type}`
    }));
  return [...inputs, ...steps];
}

function defaultInputs(
  type: PipelineStepType,
  first: PipelinePortReference,
  second: PipelinePortReference
): PipelineStepDefinition["inputs"] {
  if (type === "join") {
    return [
      { port_id: "left", source: first },
      { port_id: "right", source: second }
    ];
  }
  if (type === "union") {
    return [
      { port_id: "input_1", source: first },
      { port_id: "input_2", source: second }
    ];
  }
  return [{ port_id: "input", source: first }];
}

function defaultConfig(type: PipelineStepType, columns: string[] = []): Record<string, unknown> {
  const first = columns[0] ?? "column_name";
  const configs: Record<PipelineStepType, Record<string, unknown>> = {
    select_columns: { columns: columns.length ? columns : [first] },
    add_identifier: { mode: "record_hash", output_column: "row_id" },
    rename_columns: { renames: Object.fromEntries((columns.length ? columns : [first]).map((column) => [column, column])) },
    cast_columns: { casts: { [first]: "VARCHAR" } },
    filter_rows: { mode: "visual", conditions: [{ column: first, operator: "eq", value: "" }], combine: "and" },
    sort_rows: { columns: [{ column: first, direction: "asc" }] },
    deduplicate: { columns: [] },
    impute_missing: { rules: [{ column: first, method: "fixed", value: 0, add_indicator: false }] },
    derive_column: {
      name: "new_column",
      expression: {
        operator: "multiply",
        left: { column: first },
        right: { literal: 1 }
      }
    },
    aggregate: { group_by: [], aggregations: [{ column: "*", function: "count", alias: "row_count" }] },
    join: { join_type: "inner", keys: [{ left: first, right: first }], right_suffix: "_right" },
    union: { by_name: true },
    map_categories: { column: first, mapping: {} },
    custom_sql: { sql: "SELECT *\nFROM input" }
  };
  return configs[type];
}

function columnsForDataset(dataset: DataAsset | undefined, cache: Record<string, DatasetColumn[]>): DatasetColumn[] {
  if (!dataset) return [];
  if (cache[dataset.id]) return cache[dataset.id];
  const stored = dataset.metadata.source_schema;
  if (!Array.isArray(stored)) return [];
  return stored.flatMap((column) => {
    if (!column || typeof column !== "object" || !("name" in column)) return [];
    const value = column as Record<string, unknown>;
    return [{ name: String(value.name), type: normalizeColumnType(String(value.type ?? "text")) }];
  });
}

function normalizeColumnType(value: string): DatasetColumn["type"] {
  const normalized = value.toLowerCase();
  if (["number", "integer", "bigint", "double", "float", "decimal", "smallint", "tinyint"].some((item) => normalized.includes(item))) return "number";
  if (normalized.includes("bool")) return "boolean";
  if (normalized.includes("date") || normalized.includes("time")) return "date";
  if (["text", "varchar", "string"].some((item) => normalized.includes(item))) return "text";
  return ["empty", "mixed", "unsupported"].includes(normalized)
    ? normalized as DatasetColumn["type"]
    : "text";
}

function datasetIdsForStepInputs(definition: PipelineDefinition, step: PipelineStepDefinition): string[] {
  return Array.from(new Set(step.inputs.flatMap((input) => datasetIdsForNode(definition, input.source.node_id))));
}

function datasetIdsForNode(definition: PipelineDefinition, nodeId: string, visited = new Set<string>()): string[] {
  if (visited.has(nodeId)) return [];
  visited.add(nodeId);
  const input = definition.inputs.find((item) => item.input_id === nodeId);
  if (input) return [input.dataset_id];
  const step = definition.steps.find((item) => item.step_id === nodeId);
  return step ? step.inputs.flatMap((item) => datasetIdsForNode(definition, item.source.node_id, new Set(visited))) : [];
}

function physicalDatasetId(datasets: DataAsset[], datasetId: string) {
  const exact = datasets.find((dataset) => dataset.id === datasetId);
  if (exact) return exact.id;
  return datasets
    .filter((dataset) => dataset.logical_id === datasetId)
    .sort((left, right) => right.version_number - left.version_number)[0]?.id ?? datasetId;
}

function columnRoles(dataset: DataAsset | undefined): Record<string, string> {
  if (!dataset) return {};
  const dataRoles = recordValue(dataset.metadata.data_roles);
  const roles = recordValue(dataRoles.column_roles);
  return Object.fromEntries(Object.entries(roles).map(([name, role]) => [name, String(role)]));
}

function datasetOutput(
  input: PipelinePortReference | undefined,
  outputId = "result",
  existing?: Partial<PipelineOutputDefinition>,
  outputNameSuggestion = "result"
): PipelineOutputDefinition {
  return {
    output_id: outputId || "result",
    input: input ?? { node_id: "", port_id: "out" },
    materialization: "dataset",
    write_mode: "replace",
    dataset_name: existing?.dataset_name || outputNameSuggestion || outputId || "result",
    business_case_role: existing?.business_case_role ?? "source",
    data_contract: existing?.data_contract
  };
}

function referenceKey(reference: PipelinePortReference | undefined) {
  return reference ? `${reference.node_id}::${reference.port_id}` : "";
}

function referenceFromKey(value: string): PipelinePortReference {
  const [node_id, port_id = "out"] = value.split("::");
  return { node_id, port_id };
}

function nextStableId(prefix: string, used: Set<string>) {
  let index = 1;
  while (used.has(`${prefix}_${index}`)) index += 1;
  return `${prefix}_${index}`;
}

function isNodeReferenced(definition: PipelineDefinition, nodeId: string) {
  return definition.steps.some((step) => step.inputs.some((input) => input.source.node_id === nodeId))
    || definition.outputs.some((output) => output.input.node_id === nodeId);
}

function useColumnValues(
  datasetIds: string[] | string | undefined,
  column: string | undefined,
  enabled: boolean
) {
  const [state, setState] = useState({
    options: [] as string[],
    truncated: false,
    loading: false,
    error: ""
  });
  const datasetKey = (Array.isArray(datasetIds) ? datasetIds : [datasetIds])
    .filter((datasetId): datasetId is string => Boolean(datasetId))
    .join("|");
  useEffect(() => {
    let active = true;
    if (!enabled || !datasetKey || !column) {
      setState({ options: [], truncated: false, loading: false, error: "" });
      return;
    }
    setState((current) => ({ ...current, loading: true }));
    void (async () => {
      let lastError = "";
      for (const datasetId of datasetKey.split("|")) {
        try {
          const result = await api.visualizationGroups(datasetId, column, 100);
          if (active) setState({
            options: result.values,
            truncated: result.truncated,
            loading: false,
            error: ""
          });
          return;
        } catch (error) {
          lastError = error instanceof Error ? error.message : "Unknown error";
        }
      }
      if (active) setState({
        options: [],
        truncated: false,
        loading: false,
        error: `Could not load source values from upstream datasets: ${lastError}`
      });
    })();
    return () => { active = false; };
  }, [column, datasetKey, enabled]);
  return state;
}

function isCategorical(column: PipelineColumn | undefined) {
  if (!column) return false;
  return column.type === "boolean"
    || ["feature_categorical", "feature_ordinal", "boolean", "target"].includes(column.role ?? "");
}

function categoricalColumns(columns: PipelineColumn[]) {
  const explicit = columns.filter(isCategorical);
  return explicit.length ? explicit : columns.filter((column) => ["text", "boolean"].includes(column.type));
}

function operatorsForColumn(column: PipelineColumn | undefined): Array<[string, string]> {
  const common: Array<[string, string]> = [["eq", "equals"], ["ne", "does not equal"]];
  const empty: Array<[string, string]> = [["is_null", "is empty"], ["not_null", "is not empty"]];
  if (isCategorical(column) || column?.type === "boolean") return [...common, ["in", "is one of"], ["not_in", "is not one of"], ...empty];
  if (column?.type === "number" || column?.type === "date") return [...common, ["gt", "greater than"], ["gte", "at least"], ["lt", "less than"], ["lte", "at most"], ...empty];
  return [...common, ["contains", "contains"], ["starts_with", "starts with"], ["ends_with", "ends with"], ["in", "is one of"], ...empty];
}

function defaultOperator(column: PipelineColumn | undefined) {
  return "eq";
}

function deriveOperators(column: PipelineColumn | undefined) {
  return column?.type === "text" || isCategorical(column) ? ["concat"] : ["add", "subtract", "multiply", "divide"];
}

function aggregateFunctions(column: PipelineColumn | undefined) {
  if (!column) return ["count"];
  return column.type === "number" ? ["sum", "avg", "min", "max", "count", "count_distinct"] : ["count", "count_distinct", "min", "max"];
}

function imputeMethodOptions(column: PipelineColumn): Array<[string, string]> {
  const base: Array<[string, string]> = [["fixed", "Fixed value"], ["drop_rows", "Drop rows"], ["mode", "Most frequent"]];
  if (column.type === "number") return [["fixed", "Fixed value"], ["mean", "Mean"], ["median", "Median"], ["mode", "Most frequent"], ["drop_rows", "Drop rows"]];
  if (column.type === "text" || isCategorical(column)) return [["constant", "Constant"], ["unknown", "Unknown"], ["mode", "Most frequent"], ["drop_rows", "Drop rows"]];
  if (column.type === "boolean") return [["fixed", "Fixed value"], ["mode", "Most frequent"], ["drop_rows", "Drop rows"]];
  return base;
}

function defaultImputeMethod(column: PipelineColumn) {
  return column.type === "number" ? "median" : column.type === "text" || isCategorical(column) ? "unknown" : "fixed";
}

function normalizeImputeRules(config: Record<string, unknown>, columns: PipelineColumn[]) {
  const known = new Set(columns.map((column) => column.name));
  const rawRules = recordList(config.rules).filter((rule) => known.has(String(rule.column)));
  if (rawRules.length) return rawRules;
  const values = recordValue(config.values);
  return Object.entries(values)
    .filter(([column]) => known.has(column))
    .map(([column, value]) => ({ column, method: "fixed", value, add_indicator: false }));
}

function suggestedDuckDbType(type: DatasetColumn["type"]) {
  return type === "number" ? "DOUBLE" : type === "boolean" ? "BOOLEAN" : type === "date" ? "TIMESTAMP" : "VARCHAR";
}

function defaultValueForType(type: DatasetColumn["type"]) {
  return type === "number" ? 0 : type === "boolean" ? false : "";
}

function compatibleTypes(left: DatasetColumn["type"], right: DatasetColumn["type"]) {
  return left === right || ["empty", "mixed", "unsupported"].includes(left) || ["empty", "mixed", "unsupported"].includes(right);
}

function suggestJoinKey(left: string, rightColumns: PipelineColumn[]) {
  const exact = rightColumns.find((column) => column.name === left);
  if (exact) return exact.name;
  return rightColumns[0]?.name ?? "";
}

function quoteSqlIdentifier(value: string) {
  return `"${value.replaceAll("\"", "\"\"")}"`;
}

function safeDomId(value: string | undefined) {
  return (value ?? "none").replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 80);
}

function splitComma(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>> : [];
}

function parseScalar(value: string): string | number | boolean | null {
  const trimmed = value.trim();
  if (trimmed === "null") return null;
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (trimmed !== "" && Number.isFinite(Number(trimmed))) return Number(trimmed);
  return value;
}

function withoutKey(value: Record<string, unknown>, key: string) {
  const next = { ...value };
  delete next[key];
  return next;
}

function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
