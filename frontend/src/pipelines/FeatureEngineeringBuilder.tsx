import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  CalendarDays,
  Check,
  ChevronDown,
  Database,
  GitBranch,
  Info,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCaseDataAttachment,
  DataAsset,
  DatasetColumn
} from "../api/client";
import {
  defaultFeatureTransform
} from "./featureEngineeringContract";
import type {
  FeatureEngineeringDefinition,
  FeatureEvaluation,
  FeatureInputRole,
  FeatureTransformation,
  FeatureTransformType
} from "./featureEngineeringContract";
import type { PipelineDefinition } from "./pipelineContract";
import {
  datasetColumns,
  inferPipelineOutputColumns,
  inputDatasetIds
} from "./pipelineSchema";

const transformOptions: Array<{
  type: FeatureTransformType;
  label: string;
  description: string;
}> = [
  { type: "impute", label: "Missing values", description: "Learn replacements from training only." },
  { type: "scale_numeric", label: "Numeric scaling", description: "Standard, min-max or robust scaling." },
  { type: "encode_categorical", label: "Categorical encoding", description: "Bounded ordinal, one-hot or frequency encoding." },
  { type: "datetime_features", label: "Date and time", description: "Calendar parts and cyclical representations." },
  { type: "numeric_interaction", label: "Numeric interaction", description: "An explicit arithmetic relationship between two features." },
  { type: "math_transform", label: "Mathematical transform", description: "Square, root, exponential, logarithm or absolute value." },
  { type: "sql_expression", label: "SQL expression", description: "Create one feature with a controlled scalar DuckDB SQL expression." },
  { type: "pca", label: "PCA projection", description: "Fit reusable principal components on the training partition." }
];

const splitOptions: Array<{
  value: FeatureEvaluation["split_strategy"];
  label: string;
  description: string;
}> = [
  { value: "predefined", label: "Existing datasets", description: "Use datasets already assigned as training, validation and test." },
  { value: "random", label: "Random holdout", description: "Deterministic row-level split using the row ID and seed." },
  { value: "stratified", label: "Stratified holdout", description: "Preserve target class proportions across partitions." },
  { value: "group", label: "Group holdout", description: "Keep every entity/group entirely inside one partition." },
  { value: "time", label: "Time holdout", description: "Train on the past, validate next and test on the newest records." }
];

export function FeatureEngineeringBuilder({
  definition,
  datasets,
  dataAttachments,
  upstreamDefinition,
  hasUpstream,
  disabled,
  onChange
}: {
  definition: FeatureEngineeringDefinition;
  datasets: DataAsset[];
  dataAttachments: BusinessCaseDataAttachment[];
  upstreamDefinition?: PipelineDefinition;
  hasUpstream: boolean;
  disabled: boolean;
  onChange: (definition: FeatureEngineeringDefinition) => void;
}) {
  const [schemaCache, setSchemaCache] = useState<Record<string, DatasetColumn[]>>({});
  const [selectedNodeId, setSelectedNodeId] = useState("__data__");
  const relevantDatasetIds = useMemo(
    () => Array.from(new Set([
      ...inputDatasetIds(upstreamDefinition),
      ...definition.inputs.map((input) => input.dataset_id).filter(Boolean)
    ])),
    [definition.inputs, upstreamDefinition]
  );
  useEffect(() => {
    for (const datasetId of relevantDatasetIds) {
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
  }, [datasets, relevantDatasetIds, schemaCache]);

  const upstreamColumns = useMemo(
    () => inferPipelineOutputColumns(upstreamDefinition, datasets, schemaCache),
    [datasets, schemaCache, upstreamDefinition]
  );
  const directColumns = useMemo(
    () => definition.inputs.flatMap((input) =>
      datasetColumns(datasets.find((item) => item.id === input.dataset_id), schemaCache)
    ),
    [datasets, definition.inputs, schemaCache]
  );
  const availableColumns = useMemo(
    () => mergeColumns(hasUpstream ? [...upstreamColumns, ...directColumns] : directColumns),
    [directColumns, hasUpstream, upstreamColumns]
  );
  const finalColumns = useMemo(
    () => inferFeatureRecipeColumns(availableColumns, definition.transformations),
    [availableColumns, definition.transformations]
  );
  const roleColumns = useMemo(
    () => mergeColumns([
      ...finalColumns,
      ...definition.transformations
        .filter((transform) =>
          transform.type === "encode_categorical"
          && transform.config.method === "one_hot"
          && transform.config.drop_original !== false
        )
        .flatMap((transform) => transform.columns)
        .map((name) => availableColumns.find((column) => column.name === name))
        .filter((column): column is DatasetColumn => Boolean(column))
    ]),
    [availableColumns, definition.transformations, finalColumns]
  );
  const dateColumns = roleColumns.filter((column) => column.type === "date");
  const primaryDatasetId = inputDatasetIds(upstreamDefinition)[0]
    ?? definition.inputs.find((item) => item.role === "training")?.dataset_id;
  const attachment = dataAttachments.find((item) => item.data_asset_id === primaryDatasetId);
  const suggestedTarget = attachment?.target_column ?? "";
  const suggestedRowId = attachment?.primary_key_column ?? "";
  const suggestedFeatures = roleColumns
    .map((column) => column.name)
    .filter((name) => ![suggestedTarget, suggestedRowId].includes(name));

  function updateInput(index: number, datasetId: string) {
    onChange({
      ...definition,
      inputs: definition.inputs.map((item, itemIndex) =>
        itemIndex === index ? { ...item, dataset_id: datasetId } : item
      )
    });
  }

  function updateInputVersionPolicy(index: number, versionPolicy: "latest" | "select_at_run") {
    onChange({
      ...definition,
      inputs: definition.inputs.map((item, itemIndex) =>
        itemIndex === index ? { ...item, version_policy: versionPolicy } : item
      )
    });
  }

  function addInput(role: FeatureInputRole) {
    if (definition.inputs.some((item) => item.role === role)) return;
    onChange({
      ...definition,
      inputs: [...definition.inputs, { input_id: role, role, dataset_id: "", version_policy: "latest" }],
      outputs: [...definition.outputs, outputForRole(role)]
    });
  }

  function removeInput(inputId: string) {
    onChange({
      ...definition,
      inputs: definition.inputs.filter((item) => item.input_id !== inputId),
      outputs: definition.outputs.filter((item) => item.input_id !== inputId)
    });
  }

  function setSplitStrategy(strategy: FeatureEvaluation["split_strategy"]) {
    const generated = strategy !== "predefined";
    onChange({
      ...definition,
      evaluation: {
        ...definition.evaluation,
        split_strategy: strategy,
        stratify_column: strategy === "stratified"
          ? definition.evaluation.stratify_column || definition.target_column
          : definition.evaluation.stratify_column,
        group_column: strategy === "group"
          ? definition.evaluation.group_column || definition.group_column
          : definition.evaluation.group_column,
        time_column: strategy === "time"
          ? definition.evaluation.time_column || definition.event_time_column
          : definition.evaluation.time_column
      },
      inputs: generated
        ? [definition.inputs.find((item) => item.role === "training")
          ?? { input_id: "training", role: "training", dataset_id: "", version_policy: "latest" }]
        : definition.inputs,
      outputs: generated
        ? generatedOutputs(definition.evaluation.validation_size)
        : definition.inputs.map((item) => outputForRole(item.role))
    });
  }

  function updateEvaluation(patch: Partial<FeatureEvaluation>) {
    const next = { ...definition.evaluation, ...patch };
    onChange({
      ...definition,
      evaluation: next,
      outputs: next.split_strategy === "predefined"
        ? definition.outputs
        : generatedOutputs(next.validation_size)
    });
  }

  function addTransform(type: FeatureTransformType) {
    const transform = defaultFeatureTransform(type, definition.transformations.length + 1);
    onChange({
      ...definition,
      transformations: [...definition.transformations, transform]
    });
    setSelectedNodeId(`transform:${transform.transform_id}`);
  }

  function moveTransform(index: number, direction: -1 | 1) {
    const destination = index + direction;
    if (destination < 0 || destination >= definition.transformations.length) return;
    const transformations = [...definition.transformations];
    [transformations[index], transformations[destination]] = [
      transformations[destination],
      transformations[index]
    ];
    onChange({ ...definition, transformations });
  }

  return (
    <div className="de-designer fe-block-designer">
      <aside className="de-palette fe-block-palette">
        <div>
          <span className="builder-kicker">Toolbox</span>
          <h3>FE blocks</h3>
          <p>Required contract blocks are always present. Add only the preprocessing your model needs.</p>
        </div>
        <div className="palette-divider">Required contract</div>
        <button type="button" onClick={() => setSelectedNodeId("__data__")}>
          <GitBranch size={16} />
          <span><strong>Data & evaluation</strong><small>Inputs, holdout and cross-validation</small></span>
          <Check size={14} />
        </button>
        <button type="button" onClick={() => setSelectedNodeId("__roles__")}>
          <SlidersHorizontal size={16} />
          <span><strong>Feature roles</strong><small>Features, target and protected keys</small></span>
          <Check size={14} />
        </button>
        <button type="button" onClick={() => setSelectedNodeId("__outputs__")}>
          <Database size={16} />
          <span><strong>Feature outputs</strong><small>Parquet datasets and fitted state</small></span>
          <Check size={14} />
        </button>
        <div className="palette-divider">Optional transformations</div>
        {transformOptions.map((option) => (
          <button key={option.type} type="button" onClick={() => addTransform(option.type)}
            disabled={disabled || availableColumns.length === 0}>
            <Sparkles size={16} />
            <span><strong>{option.label}</strong><small>{option.description}</small></span>
            <Plus size={14} />
          </button>
        ))}
      </aside>

      <div className="de-canvas fe-block-canvas">
        <div className="canvas-toolbar">
          <span>Feature flow</span>
          <small>Click a block to configure it</small>
        </div>
        <div className="de-flow fe-block-flow">
          <button className={selectedNodeId === "__data__" ? "de-node source selected" : "de-node source"}
            type="button" onClick={() => setSelectedNodeId("__data__")}>
            <GitBranch size={19} />
            <span><small>REQUIRED · DATA</small><strong>Data & evaluation</strong>
              <em>{definition.mode === "fit_transform"
                ? `${title(definition.evaluation.split_strategy)} split`
                : "Reuse fitted state"}</em></span>
          </button>
          <ArrowRight className="de-edge-arrow" size={27} />
          <div className="de-transform-chain">
            {definition.transformations.map((transform, index) => {
              const nodeId = `transform:${transform.transform_id}`;
              const option = transformOptions.find((item) => item.type === transform.type);
              return (
                <div className="de-chain-item" key={transform.transform_id}>
                  {index > 0 && <ArrowRight className="de-edge-arrow inline" size={24} />}
                  <button className={selectedNodeId === nodeId ? "de-node transform selected" : "de-node transform"}
                    type="button" onClick={() => setSelectedNodeId(nodeId)}>
                    <Sparkles size={19} />
                    <span><small>TRANSFORMATION {index + 1}</small><strong>{option?.label ?? transform.type}</strong>
                      <em>{transform.columns.length
                        ? `${transform.columns.length} selected columns`
                        : "Needs configuration"}</em></span>
                  </button>
                </div>
              );
            })}
            {!definition.transformations.length && (
              <div className="canvas-empty-node compact">
                <strong>No preprocessing required</strong>
                <span>Selected features can pass through unchanged.</span>
              </div>
            )}
          </div>
          <ArrowRight className="de-edge-arrow" size={27} />
          <button className={selectedNodeId === "__roles__" ? "de-node source selected" : "de-node source"}
            type="button" onClick={() => setSelectedNodeId("__roles__")}>
            <SlidersHorizontal size={19} />
            <span><small>REQUIRED · FINAL CONTRACT</small><strong>Feature roles</strong>
              <em>{definition.feature_columns.length} model features</em></span>
          </button>
          <ArrowRight className="de-edge-arrow" size={27} />
          <button className={selectedNodeId === "__outputs__" ? "de-node output selected" : "de-node output"}
            type="button" onClick={() => setSelectedNodeId("__outputs__")}>
            <Database size={19} />
            <span><small>REQUIRED · OUTPUT</small><strong>Feature datasets</strong>
              <em>{definition.outputs.length} Parquet output{definition.outputs.length === 1 ? "" : "s"}</em></span>
          </button>
        </div>
      </div>

      <aside className="de-inspector fe-block-inspector">
        <div>
          <span className="builder-kicker">Inspector</span>
          <h3>Block settings</h3>
        </div>
        <div className="fe-inspector-content">
      <section className={`fe-section fe-mode-section ${selectedNodeId === "__data__" ? "active" : ""}`}>
        <SectionHeading
          kicker="Execution"
          title="How should this recipe run?"
          description="Fit learns state only from training. Transform reuses one pinned, immutable state artifact."
        />
        <div className="fe-choice-grid two">
          {(["fit_transform", "transform"] as const).map((mode) => (
            <button
              className={definition.mode === mode ? "fe-choice selected" : "fe-choice"}
              type="button"
              key={mode}
              disabled={disabled}
              onClick={() => onChange({ ...definition, mode })}
            >
              {definition.mode === mode && <Check size={16} />}
              <strong>{mode === "fit_transform" ? "Fit a new recipe state" : "Reuse fitted state"}</strong>
              <span>{mode === "fit_transform"
                ? "For experiments and final fitting on a declared training partition."
                : "For scoring with exactly the same learned statistics and categories."}</span>
            </button>
          ))}
        </div>
        {definition.mode === "transform" && (
          <label className="fe-field">
            <span>Fitted transform artifact</span>
            <input
              value={definition.fitted_state_artifact_id}
              disabled={disabled}
              onChange={(event) => onChange({
                ...definition,
                fitted_state_artifact_id: event.target.value
              })}
              placeholder="Paste the ID shown after an official FE run"
            />
            <small>The platform never resolves this as “latest”.</small>
          </label>
        )}
      </section>

      {definition.mode === "fit_transform" && (
        <section className={`fe-section ${selectedNodeId === "__data__" ? "active" : ""}`}>
          <SectionHeading
            kicker="Evaluation"
            title="Holdout split and cross-validation"
            description="The split happens before fitting feature statistics, preventing validation and test leakage."
          />
          <div className="fe-choice-grid">
            {splitOptions.map((option) => (
              <button
                className={definition.evaluation.split_strategy === option.value
                  ? "fe-choice selected"
                  : "fe-choice"}
                type="button"
                key={option.value}
                disabled={disabled}
                onClick={() => setSplitStrategy(option.value)}
              >
                {definition.evaluation.split_strategy === option.value && <Check size={16} />}
                <strong>{option.label}</strong>
                <span>{option.description}</span>
              </button>
            ))}
          </div>

          {definition.evaluation.split_strategy === "predefined" ? (
            <PredefinedInputs
              definition={definition}
              datasets={datasets}
              hasUpstream={hasUpstream}
              disabled={disabled}
              onDatasetChange={updateInput}
              onVersionPolicyChange={updateInputVersionPolicy}
              onAdd={addInput}
              onRemove={removeInput}
            />
          ) : (
            <GeneratedSplitControls
              definition={definition}
              columns={availableColumns}
              datasets={datasets}
              hasUpstream={hasUpstream}
              disabled={disabled}
              onDatasetChange={(datasetId) => updateInput(0, datasetId)}
              onVersionPolicyChange={(policy) => updateInputVersionPolicy(0, policy)}
              onEvaluationChange={updateEvaluation}
            />
          )}

          <div className="fe-cv-panel">
            <label className="fe-toggle">
              <input
                type="checkbox"
                checked={definition.evaluation.cross_validation.enabled}
                disabled={disabled}
                onChange={(event) => updateEvaluation({
                  cross_validation: {
                    ...definition.evaluation.cross_validation,
                    enabled: event.target.checked
                  }
                })}
              />
              <span><strong>Prepare cross-validation folds</strong>
                <small>Adds an auditable <code>__mlapp_cv_fold</code> column to training.</small></span>
            </label>
            {definition.evaluation.cross_validation.enabled && (
              <div className="fe-inline-grid">
                <label className="fe-field"><span>CV strategy</span>
                  <select
                    value={definition.evaluation.cross_validation.strategy}
                    disabled={disabled}
                    onChange={(event) => updateEvaluation({
                      cross_validation: {
                        ...definition.evaluation.cross_validation,
                        strategy: event.target.value as FeatureEvaluation["cross_validation"]["strategy"]
                      }
                    })}
                  >
                    <option value="kfold">K-fold</option>
                    <option value="stratified">Stratified K-fold</option>
                    <option value="group">Group K-fold</option>
                    <option value="time">Time-aware folds</option>
                  </select>
                </label>
                <label className="fe-field"><span>Number of folds</span>
                  <input type="number" min={2} max={20}
                    value={definition.evaluation.cross_validation.folds}
                    disabled={disabled}
                    onChange={(event) => updateEvaluation({
                      cross_validation: {
                        ...definition.evaluation.cross_validation,
                        folds: Number(event.target.value)
                      }
                    })} />
                </label>
                <label className="fe-field"><span>CV seed</span>
                  <input type="number" value={definition.evaluation.cross_validation.seed}
                    disabled={disabled}
                    onChange={(event) => updateEvaluation({
                      cross_validation: {
                        ...definition.evaluation.cross_validation,
                        seed: Number(event.target.value)
                      }
                    })} />
                </label>
                {["kfold", "stratified"].includes(definition.evaluation.cross_validation.strategy) && (
                  <label className="fe-toggle compact"><input type="checkbox"
                    checked={definition.evaluation.cross_validation.shuffle}
                    disabled={disabled}
                    onChange={(event) => updateEvaluation({
                      cross_validation: {
                        ...definition.evaluation.cross_validation,
                        shuffle: event.target.checked
                      }
                    })} />
                    <span><strong>Shuffle deterministically</strong></span>
                  </label>
                )}
              </div>
            )}
          </div>

          {needsRowId(definition) && !definition.row_id_column && (
            <div className="fe-warning"><Info size={17} />
              <span>Open the <strong>Feature roles</strong> block and set <strong>Stable row ID</strong>. It keeps split and fold assignments reproducible after rows are reordered.</span>
            </div>
          )}
          {needsTarget(definition) && !definition.evaluation.stratify_column && (
            <div className="fe-warning"><Info size={17} />
              <span>Open the <strong>Feature roles</strong> block and set <strong>Target</strong> for stratified evaluation.</span>
            </div>
          )}
          {needsGroup(definition) && !definition.evaluation.group_column && (
            <div className="fe-warning"><Info size={17} />
              <span>Open the <strong>Feature roles</strong> block and set <strong>Group/entity key</strong> so one entity cannot cross fold or holdout boundaries.</span>
            </div>
          )}
          {needsTime(definition) && !definition.evaluation.time_column && (
            <div className="fe-warning"><Info size={17} />
              <span>Open the <strong>Feature roles</strong> block and set <strong>Event timestamp</strong>. Time evaluation always trains on earlier observations.</span>
            </div>
          )}

          <div className="fe-training-note">
            <Info size={18} />
            <div><strong>What happens during model training?</strong>
              <p>
                This step prepares holdout datasets and a fold plan. The future Training step must
                clone and fit this FE recipe separately inside every fold, train the estimator,
                aggregate fold metrics, then refit on the complete training partition. FE itself
                does not train a model or report model quality.
              </p>
            </div>
          </div>
        </section>
      )}

      <section className={`fe-section ${selectedNodeId === "__roles__" ? "active" : ""}`}>
        <SectionHeading
          kicker="Feature contract"
          title="Assign column roles"
          description="Choose from the detected upstream schema. IDs, target and time keys remain protected."
        />
        {roleColumns.length === 0 ? (
          <div className="fe-empty-schema"><Database size={19} />
            <span><strong>Waiting for a source schema</strong>
              <small>Select a DE source or dataset first.</small></span></div>
        ) : (
          <>
            {(suggestedTarget || suggestedRowId) && (
              <div className="fe-suggestion">
                <Sparkles size={17} />
                <span>Business Case metadata suggests
                  {suggestedTarget ? ` target “${suggestedTarget}”` : ""}
                  {suggestedTarget && suggestedRowId ? " and" : ""}
                  {suggestedRowId ? ` row ID “${suggestedRowId}”` : ""}.</span>
                <button type="button" className="secondary-button compact-button" disabled={disabled}
                  onClick={() => onChange({
                    ...definition,
                    target_column: suggestedTarget,
                    row_id_column: suggestedRowId,
                    feature_columns: suggestedFeatures
                  })}>Apply suggestions</button>
              </div>
            )}
            <div className="fe-role-grid">
              <div className="fe-role-main">
                <ColumnPicker
                  label="Model features"
                  columns={roleColumns.filter((column) =>
                    ![
                      definition.target_column,
                      definition.row_id_column,
                      definition.group_column,
                      definition.event_time_column
                    ].includes(column.name)
                  )}
                  selected={definition.feature_columns}
                  disabled={disabled}
                  onChange={(feature_columns) => onChange({ ...definition, feature_columns })}
                />
              </div>
              <div className="fe-role-selects">
                <ColumnSelect label="Target" value={definition.target_column}
                  columns={roleColumns} optional disabled={disabled}
                  onChange={(target_column) => onChange({
                    ...definition,
                    target_column,
                    feature_columns: definition.feature_columns.filter((item) => item !== target_column),
                    evaluation: {
                      ...definition.evaluation,
                      stratify_column: definition.evaluation.stratify_column || target_column
                    }
                  })} />
                <ColumnSelect label="Stable row ID" value={definition.row_id_column}
                  columns={roleColumns} optional disabled={disabled}
                  onChange={(row_id_column) => onChange({
                    ...definition,
                    row_id_column,
                    feature_columns: definition.feature_columns.filter((item) => item !== row_id_column)
                  })} />
                <ColumnSelect label="Group/entity key" value={definition.group_column}
                  columns={roleColumns} optional disabled={disabled}
                  onChange={(group_column) => onChange({
                    ...definition,
                    group_column,
                    feature_columns: definition.feature_columns.filter((item) => item !== group_column),
                    evaluation: { ...definition.evaluation, group_column }
                  })} />
                <ColumnSelect label="Event timestamp" value={definition.event_time_column}
                  columns={dateColumns.length ? dateColumns : roleColumns} optional disabled={disabled}
                  onChange={(event_time_column) => onChange({
                    ...definition,
                    event_time_column,
                    feature_columns: definition.feature_columns.filter((item) => item !== event_time_column),
                    evaluation: { ...definition.evaluation, time_column: event_time_column }
                  })} />
              </div>
            </div>
          </>
        )}
      </section>

      <section className={`fe-section ${selectedNodeId.startsWith("transform:") ? "active" : ""}`}>
        <div className="fe-heading-with-action">
          <SectionHeading
            kicker="Feature recipe"
            title="Selected transformation"
            description="Configure compatible columns and learned behavior. State is fitted on training only."
          />
        </div>
        <div className="fe-transform-list">
          {definition.transformations.map((transform, index) => ({ transform, index }))
            .filter(({ transform }) => selectedNodeId === `transform:${transform.transform_id}`)
            .map(({ transform, index }) => {
              const inputColumns = inferFeatureRecipeColumns(
                availableColumns,
                definition.transformations.slice(0, index)
              );
              return (
                <FeatureTransformCard
                  key={transform.transform_id}
                  index={index}
                  transform={transform}
                  columns={inputColumns}
                  numericColumns={inputColumns.filter((column) => column.type === "number")}
                  categoricalColumns={inputColumns.filter((column) =>
                    ["text", "boolean", "mixed"].includes(column.type)
                  )}
                  dateColumns={inputColumns.filter((column) => column.type === "date")}
                  disabled={disabled}
                  canMoveUp={index > 0}
                  canMoveDown={index < definition.transformations.length - 1}
                  onMove={(direction) => moveTransform(index, direction)}
                  onChange={(next) => onChange({
                    ...definition,
                    transformations: definition.transformations.map((item, itemIndex) =>
                      itemIndex === index ? next : item
                    )
                  })}
                  onRemove={() => {
                    onChange({
                      ...definition,
                      transformations: definition.transformations.filter((_, itemIndex) => itemIndex !== index)
                    });
                    setSelectedNodeId("__roles__");
                  }}
                />
              );
            })}
        </div>
      </section>

      <section className={`fe-section ${selectedNodeId === "__outputs__" ? "active" : ""}`}>
        <SectionHeading
          kicker="Outputs"
          title="Feature datasets created by this step"
          description="An official run saves these full-scope Parquet datasets. A dry-run creates temporary previews only."
        />
        <div className="fe-output-grid">
          {definition.outputs.map((output, index) => (
            <article className={`fe-output-card ${output.business_case_role}`} key={output.output_id}>
              <div className="fe-output-icon"><Database size={19} /></div>
              <div className="fe-output-copy">
                <span>{title(output.business_case_role)} partition</span>
                <strong>{output.dataset_name || "Unnamed feature dataset"}</strong>
                <small>
                  {output.business_case_role === "training"
                    ? "Used to fit preprocessing and the future model."
                    : output.business_case_role === "validation"
                      ? "Used for model selection without fitting preprocessing."
                      : "Held back for final unbiased evaluation."}
                </small>
                <label className="fe-field"><span>Saved dataset name</span>
                  <input value={output.dataset_name} disabled={disabled}
                    onChange={(event) => onChange({
                      ...definition,
                      outputs: definition.outputs.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, dataset_name: event.target.value } : item
                      )
                    })} />
                </label>
                <em>Parquet · Business Case role: {output.business_case_role}</em>
              </div>
            </article>
          ))}
        </div>
        <div className="fe-artifact-note"><GitBranch size={17} />
          <span>A fitted transform artifact is also created, separately from the datasets, so scoring can reuse exactly the same state.</span>
        </div>
      </section>
        </div>
      </aside>
    </div>
  );
}

function PredefinedInputs({
  definition,
  datasets,
  hasUpstream,
  disabled,
  onDatasetChange,
  onVersionPolicyChange,
  onAdd,
  onRemove
}: {
  definition: FeatureEngineeringDefinition;
  datasets: DataAsset[];
  hasUpstream: boolean;
  disabled: boolean;
  onDatasetChange: (index: number, datasetId: string) => void;
  onVersionPolicyChange: (index: number, policy: "latest" | "select_at_run") => void;
  onAdd: (role: FeatureInputRole) => void;
  onRemove: (inputId: string) => void;
}) {
  return (
    <div className="fe-input-panel">
      <div className="fe-subheading"><div><strong>Input partitions</strong>
        <span>Training is mandatory. Add validation and test when they already exist.</span></div>
        <div className="fe-compact-actions">
          {(["validation", "test"] as FeatureInputRole[]).map((role) => (
            <button className="secondary-button compact-button" type="button" key={role}
              disabled={disabled || definition.inputs.some((item) => item.role === role)}
              onClick={() => onAdd(role)}><Plus size={14} /> {title(role)}</button>
          ))}
        </div>
      </div>
      <div className="fe-input-grid">
        {definition.inputs.map((input, index) => (
          <article className={`fe-input-card ${input.role}`} key={input.input_id}>
            <div><span>{title(input.role)}</span>
              <strong>{input.role === "training" && hasUpstream
                ? "Data Engineering output"
                : datasets.find((item) => item.id === input.dataset_id)?.name || "Choose a dataset"}</strong></div>
            {input.role === "training" && hasUpstream ? (
              <div className="fe-upstream-badge"><GitBranch size={15} /> Connected from previous step</div>
            ) : (
              <>
              <label className="fe-field"><span>Dataset</span>
                <select value={input.dataset_id} disabled={disabled}
                  onChange={(event) => onDatasetChange(index, event.target.value)}>
                  <option value="">Choose dataset…</option>
                  {datasets.filter(isUsableDataset).map((dataset) => (
                    <option value={dataset.id} key={dataset.id}>
                      {dataset.name} · {dataset.row_count ?? "?"} rows
                    </option>
                  ))}
                </select>
              </label>
              <label className="fe-field"><span>Version policy</span>
                <select value={input.version_policy ?? "latest"} disabled={disabled}
                  onChange={(event) => onVersionPolicyChange(index, event.target.value as "latest" | "select_at_run")}>
                  <option value="latest">Latest at run start</option>
                  <option value="select_at_run">Select at run</option>
                </select>
              </label>
              </>
            )}
            {input.role !== "training" && (
              <button className="fe-remove-link" type="button" disabled={disabled}
                onClick={() => onRemove(input.input_id)}><Trash2 size={14} /> Remove</button>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

function GeneratedSplitControls({
  definition,
  columns,
  datasets,
  hasUpstream,
  disabled,
  onDatasetChange,
  onVersionPolicyChange,
  onEvaluationChange
}: {
  definition: FeatureEngineeringDefinition;
  columns: DatasetColumn[];
  datasets: DataAsset[];
  hasUpstream: boolean;
  disabled: boolean;
  onDatasetChange: (datasetId: string) => void;
  onVersionPolicyChange: (policy: "latest" | "select_at_run") => void;
  onEvaluationChange: (patch: Partial<FeatureEvaluation>) => void;
}) {
  const evaluation = definition.evaluation;
  const trainingShare = Math.max(0, 1 - evaluation.validation_size - evaluation.test_size);
  return (
    <div className="fe-split-panel">
      <div className="fe-split-source">
        <Database size={18} />
        <div><span>Source to partition</span>
          {hasUpstream ? <strong>Data Engineering output</strong> : (
            <select value={definition.inputs[0]?.dataset_id ?? ""} disabled={disabled}
              onChange={(event) => onDatasetChange(event.target.value)}>
              <option value="">Choose dataset…</option>
              {datasets.filter(isUsableDataset).map((dataset) => (
                <option value={dataset.id} key={dataset.id}>{dataset.name}</option>
              ))}
            </select>
          )}</div>
        {!hasUpstream && (
          <label className="fe-field"><span>Version policy</span>
            <select value={definition.inputs[0]?.version_policy ?? "latest"} disabled={disabled}
              onChange={(event) => onVersionPolicyChange(event.target.value as "latest" | "select_at_run")}>
              <option value="latest">Latest at run start</option>
              <option value="select_at_run">Select at run</option>
            </select>
          </label>
        )}
      </div>
      <div className="fe-split-bars">
        <div className="train" style={{ flex: trainingShare }}><strong>{percent(trainingShare)}</strong><span>Train</span></div>
        {evaluation.validation_size > 0 && (
          <div className="validation" style={{ flex: evaluation.validation_size }}>
            <strong>{percent(evaluation.validation_size)}</strong><span>Validation</span>
          </div>
        )}
        <div className="test" style={{ flex: evaluation.test_size }}><strong>{percent(evaluation.test_size)}</strong><span>Test</span></div>
      </div>
      <div className="fe-inline-grid">
        <label className="fe-field"><span>Validation share</span>
          <input type="number" min={0} max={0.4} step={0.05}
            value={evaluation.validation_size} disabled={disabled}
            onChange={(event) => onEvaluationChange({ validation_size: Number(event.target.value) })} />
        </label>
        <label className="fe-field"><span>Test share</span>
          <input type="number" min={0.05} max={0.5} step={0.05}
            value={evaluation.test_size} disabled={disabled}
            onChange={(event) => onEvaluationChange({ test_size: Number(event.target.value) })} />
        </label>
        <label className="fe-field"><span>Deterministic seed</span>
          <input type="number" value={evaluation.seed} disabled={disabled}
            onChange={(event) => onEvaluationChange({ seed: Number(event.target.value) })} />
        </label>
        {evaluation.split_strategy === "stratified" && (
          <ColumnSelect label="Stratify by" value={evaluation.stratify_column}
            columns={columns} disabled={disabled}
            onChange={(stratify_column) => onEvaluationChange({ stratify_column })} />
        )}
        {evaluation.split_strategy === "group" && (
          <ColumnSelect label="Keep groups together by" value={evaluation.group_column}
            columns={columns} disabled={disabled}
            onChange={(group_column) => onEvaluationChange({ group_column })} />
        )}
        {evaluation.split_strategy === "time" && (
          <ColumnSelect label="Order chronologically by" value={evaluation.time_column}
            columns={columns.filter((column) => column.type === "date").length
              ? columns.filter((column) => column.type === "date")
              : columns}
            disabled={disabled}
            onChange={(time_column) => onEvaluationChange({ time_column })} />
        )}
      </div>
    </div>
  );
}

function FeatureTransformCard({
  index,
  transform,
  columns,
  numericColumns,
  categoricalColumns,
  dateColumns,
  disabled,
  canMoveUp,
  canMoveDown,
  onMove,
  onChange,
  onRemove
}: {
  index: number;
  transform: FeatureTransformation;
  columns: DatasetColumn[];
  numericColumns: DatasetColumn[];
  categoricalColumns: DatasetColumn[];
  dateColumns: DatasetColumn[];
  disabled: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMove: (direction: -1 | 1) => void;
  onChange: (transform: FeatureTransformation) => void;
  onRemove: () => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const option = transformOptions.find((item) => item.type === transform.type)!;
  const config = transform.config;
  const setConfig = (patch: Record<string, unknown>) => onChange({
    ...transform,
    config: { ...config, ...patch }
  });
  const compatibleColumns = [
    "scale_numeric", "numeric_interaction", "math_transform", "pca"
  ].includes(transform.type)
    ? numericColumns
    : transform.type === "encode_categorical"
      ? categoricalColumns
      : transform.type === "datetime_features"
        ? dateColumns
        : columns;
  return (
    <article className="fe-transform-card">
      <button className="fe-transform-summary" type="button" onClick={() => setExpanded(!expanded)}>
        <span className="fe-step-number">{index + 1}</span>
        <span><strong>{option.label}</strong>
          <small>{transform.columns.length
            ? `${transform.columns.length} selected column${transform.columns.length === 1 ? "" : "s"}`
            : option.description}</small></span>
        <code>{transform.transform_id}</code>
        <ChevronDown size={17} className={expanded ? "expanded" : ""} />
      </button>
      {expanded && (
        <div className="fe-transform-body">
          {!["numeric_interaction", "sql_expression"].includes(transform.type) && (
            <ColumnPicker
              label="Apply to columns"
              columns={compatibleColumns}
              selected={transform.columns}
              disabled={disabled}
              onChange={(selected) => onChange({
                ...transform,
                columns: selected,
                config: transform.type === "pca"
                  ? {
                    ...config,
                    n_components: Math.min(
                      Number(config.n_components ?? 2),
                      Math.max(selected.length, 1)
                    )
                  }
                  : config
              })}
              compact
            />
          )}
          <div className="fe-transform-settings">
            {transform.type === "impute" && (
              <>
                <OptionSelect label="Replacement method" value={String(config.method ?? "median")}
                  values={["constant", "mean", "median", "mode"]} disabled={disabled}
                  onChange={(method) => setConfig({ method })} />
                {config.method === "constant" && (
                  <label className="fe-field"><span>Constant value</span>
                    <input value={String(config.value ?? "")} disabled={disabled}
                      onChange={(event) => setConfig({ value: event.target.value })} /></label>
                )}
                <label className="fe-toggle compact"><input type="checkbox"
                  checked={Boolean(config.add_indicator)} disabled={disabled}
                  onChange={(event) => setConfig({ add_indicator: event.target.checked })} />
                  <span><strong>Add missing-value indicator</strong></span></label>
              </>
            )}
            {transform.type === "scale_numeric" && (
              <OptionSelect label="Scaling method" value={String(config.method ?? "standard")}
                values={["standard", "minmax", "robust"]} disabled={disabled}
                onChange={(method) => setConfig({ method })} />
            )}
            {transform.type === "encode_categorical" && (
              <>
                <OptionSelect label="Encoding" value={String(config.method ?? "ordinal")}
                  values={["ordinal", "one_hot", "frequency"]} disabled={disabled}
                  onChange={(method) => setConfig({ method })} />
                <label className="fe-field"><span>Maximum categories</span>
                  <input type="number" min={2} max={500}
                    value={Number(config.max_categories ?? 50)} disabled={disabled}
                    onChange={(event) => setConfig({ max_categories: Number(event.target.value) })} />
                  <small>Prevents accidental creation of thousands of columns.</small>
                </label>
                <OptionSelect label="Unseen categories" value={String(config.handle_unknown ?? "other")}
                  values={["other", "error"]} disabled={disabled}
                  onChange={(handle_unknown) => setConfig({ handle_unknown })} />
              </>
            )}
            {transform.type === "datetime_features" && (
              <ColumnPicker
                label="Generated date parts"
                columns={["year", "quarter", "month", "day", "day_of_week", "hour", "is_weekend"]
                  .map((name) => ({ name, type: "date" as const }))}
                selected={Array.isArray(config.features) ? config.features.map(String) : []}
                disabled={disabled}
                onChange={(features) => setConfig({ features })}
                compact
              />
            )}
            {transform.type === "numeric_interaction" && (
              <>
                <ColumnSelect label="Left feature" value={String(config.left ?? "")}
                  columns={numericColumns} disabled={disabled}
                  onChange={(left) => setConfig({ left })} />
                <OptionSelect label="Operation" value={String(config.operator ?? "multiply")}
                  values={["add", "subtract", "multiply", "divide"]} disabled={disabled}
                  onChange={(operator) => setConfig({ operator })} />
                <ColumnSelect label="Right feature" value={String(config.right ?? "")}
                  columns={numericColumns} disabled={disabled}
                  onChange={(right) => setConfig({ right })} />
                <label className="fe-field"><span>New feature name</span>
                  <input value={String(config.output_column ?? "")} disabled={disabled}
                    onChange={(event) => setConfig({ output_column: event.target.value })} /></label>
              </>
            )}
            {transform.type === "math_transform" && (
              <>
                <OptionSelect label="Function" value={String(config.operation ?? "square")}
                  values={["square", "sqrt", "exp", "log", "log1p", "abs"]}
                  disabled={disabled}
                  onChange={(operation) => setConfig({
                    operation,
                    output_suffix: defaultMathSuffix(operation)
                  })} />
                <label className="fe-field"><span>Output suffix</span>
                  <input value={String(config.output_suffix ?? "__squared")} disabled={disabled}
                    onChange={(event) => setConfig({ output_suffix: event.target.value })} />
                </label>
                <small className="fe-setting-note">
                  Invalid domains are returned as NULL for square root and logarithms.
                </small>
              </>
            )}
            {transform.type === "sql_expression" && (
              <>
                <label className="fe-field"><span>DuckDB SQL expression</span>
                  <textarea className="compact-textarea fe-sql-expression"
                    value={String(config.expression ?? "")}
                    disabled={disabled}
                    placeholder={'Example: ln(1 + "amount") / nullif("days_active", 0)'}
                    onChange={(event) => setConfig({ expression: event.target.value })} />
                  <small>Enter one scalar expression only. SELECT, FROM, subqueries and external reads are blocked.</small>
                </label>
                <div className="fe-expression-columns">
                  {columns.map((column) => <code key={column.name}>{column.name}</code>)}
                </div>
                <label className="fe-field"><span>New feature name</span>
                  <input value={String(config.output_column ?? "derived_feature")} disabled={disabled}
                    onChange={(event) => setConfig({ output_column: event.target.value })} />
                </label>
                <OptionSelect label="Result type" value={String(config.output_type ?? "number")}
                  values={["number", "text", "boolean", "date"]} disabled={disabled}
                  onChange={(output_type) => setConfig({ output_type })} />
              </>
            )}
            {transform.type === "pca" && (
              <>
                <label className="fe-field"><span>Number of components</span>
                  <input type="number" min={1} max={Math.max(transform.columns.length, 1)}
                    value={Number(config.n_components ?? 2)} disabled={disabled}
                    onChange={(event) => setConfig({ n_components: Number(event.target.value) })} />
                </label>
                <label className="fe-field"><span>Output prefix</span>
                  <input value={String(config.output_prefix ?? "pca_")} disabled={disabled}
                    onChange={(event) => setConfig({ output_prefix: event.target.value })} />
                </label>
                <label className="fe-toggle compact"><input type="checkbox"
                  checked={Boolean(config.whiten)} disabled={disabled}
                  onChange={(event) => setConfig({ whiten: event.target.checked })} />
                  <span><strong>Whiten components</strong></span>
                </label>
                <label className="fe-toggle compact"><input type="checkbox"
                  checked={Boolean(config.drop_original)} disabled={disabled}
                  onChange={(event) => setConfig({ drop_original: event.target.checked })} />
                  <span><strong>Drop PCA input columns</strong></span>
                </label>
                <small className="fe-setting-note">
                  PCA is centered automatically. Place Numeric scaling before PCA when standardized PCA is intended.
                  Missing values must be imputed earlier in the flow.
                </small>
              </>
            )}
          </div>
          <div className="fe-transform-order">
            <button className="secondary-button compact-button" type="button"
              disabled={disabled || !canMoveUp} onClick={() => onMove(-1)}>
              <ArrowUp size={14} /> Move earlier
            </button>
            <button className="secondary-button compact-button" type="button"
              disabled={disabled || !canMoveDown} onClick={() => onMove(1)}>
              <ArrowDown size={14} /> Move later
            </button>
          </div>
          <button className="fe-remove-link" type="button" disabled={disabled} onClick={onRemove}>
            <Trash2 size={14} /> Remove transformation
          </button>
        </div>
      )}
    </article>
  );
}

function ColumnPicker({
  label,
  columns,
  selected,
  disabled,
  onChange,
  compact = false
}: {
  label: string;
  columns: DatasetColumn[];
  selected: string[];
  disabled: boolean;
  onChange: (selected: string[]) => void;
  compact?: boolean;
}) {
  const [query, setQuery] = useState("");
  const visible = columns.filter((column) =>
    column.name.toLowerCase().includes(query.toLowerCase())
  );
  return (
    <fieldset className={compact ? "fe-column-picker compact" : "fe-column-picker"}>
      <legend>{label}<span>{selected.length} selected</span></legend>
      <div className="fe-column-toolbar">
        <label><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter columns…" disabled={disabled} /></label>
        <button type="button" disabled={disabled} onClick={() => onChange(columns.map((column) => column.name))}>All</button>
        <button type="button" disabled={disabled} onClick={() => onChange([])}>Clear</button>
      </div>
      <div className="fe-column-options">
        {visible.map((column) => (
          <label key={column.name}>
            <input type="checkbox" checked={selected.includes(column.name)} disabled={disabled}
              onChange={(event) => onChange(event.target.checked
                ? [...selected, column.name]
                : selected.filter((item) => item !== column.name))} />
            <span>{column.name}<small>{column.type}</small></span>
          </label>
        ))}
        {!visible.length && <div className="fe-no-columns">No matching columns</div>}
      </div>
    </fieldset>
  );
}

function ColumnSelect({
  label,
  value,
  columns,
  optional = false,
  disabled,
  onChange
}: {
  label: string;
  value: string;
  columns: DatasetColumn[];
  optional?: boolean;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="fe-field"><span>{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        <option value="">{optional ? "Not assigned" : "Choose column…"}</option>
        {columns.map((column) => (
          <option value={column.name} key={column.name}>{column.name} · {column.type}</option>
        ))}
      </select>
    </label>
  );
}

function OptionSelect({
  label,
  value,
  values,
  disabled,
  onChange
}: {
  label: string;
  value: string;
  values: string[];
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="fe-field"><span>{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        {values.map((item) => <option value={item} key={item}>{title(item)}</option>)}
      </select>
    </label>
  );
}

function SectionHeading({
  kicker,
  title,
  description
}: {
  kicker: string;
  title: string;
  description: string;
}) {
  return (
    <div className="fe-section-heading">
      <span>{kicker}</span>
      <h4>{title}</h4>
      <p>{description}</p>
    </div>
  );
}

function outputForRole(role: FeatureInputRole) {
  return {
    output_id: `${role}_features`,
    input_id: role,
    dataset_name: `${title(role)} features`,
    business_case_role: role
  };
}

function generatedOutputs(validationSize: number) {
  const roles: FeatureInputRole[] = validationSize > 0
    ? ["training", "validation", "test"]
    : ["training", "test"];
  return roles.map(outputForRole);
}

function defaultMathSuffix(operation: string) {
  return {
    square: "__squared",
    sqrt: "__sqrt",
    exp: "__exp",
    log: "__log",
    log1p: "__log1p",
    abs: "__abs"
  }[operation] ?? "__transformed";
}

export function inferFeatureRecipeColumns(
  sourceColumns: DatasetColumn[],
  transformations: FeatureTransformation[]
): DatasetColumn[] {
  return transformations.reduce((columns, transform) => {
    const config = transform.config;
    if (transform.type === "impute") {
      const indicators = config.add_indicator
        ? transform.columns.map((name) => ({ name: `${name}__was_missing`, type: "boolean" as const }))
        : [];
      return mergeColumns([...columns, ...indicators]);
    }
    if (transform.type === "scale_numeric") {
      const suffix = String(config.output_suffix ?? "__scaled");
      return mergeColumns([
        ...columns,
        ...transform.columns.map((name) => ({ name: `${name}${suffix}`, type: "number" as const }))
      ]);
    }
    if (transform.type === "encode_categorical") {
      const method = String(config.method ?? "ordinal");
      const suffix = String(config.output_suffix ?? "");
      const retained = config.drop_original === false
        ? columns
        : columns.filter((column) => !transform.columns.includes(column.name));
      if (method === "one_hot") return retained;
      const ending = method === "frequency" ? "__frequency" : "__ordinal";
      return mergeColumns([
        ...retained,
        ...transform.columns.map((name) => ({
          name: `${name}${suffix}${ending}`,
          type: "number" as const
        }))
      ]);
    }
    if (transform.type === "datetime_features") {
      const retained = config.drop_original
        ? columns.filter((column) => !transform.columns.includes(column.name))
        : columns;
      const parts = Array.isArray(config.features) ? config.features.map(String) : [];
      const generated = transform.columns.flatMap((column) => [
        ...parts.map((part) => ({
          name: `${column}__${part}`,
          type: "number" as const
        })),
        ...(config.cyclical
          ? parts.filter((part) => ["month", "day_of_week", "hour"].includes(part))
            .flatMap((part) => [
              { name: `${column}__${part}_sin`, type: "number" as const },
              { name: `${column}__${part}_cos`, type: "number" as const }
            ])
          : [])
      ]);
      return mergeColumns([...retained, ...generated]);
    }
    if (transform.type === "numeric_interaction") {
      return mergeColumns([...columns, {
        name: String(config.output_column ?? "interaction"),
        type: "number" as const
      }]);
    }
    if (transform.type === "math_transform") {
      const suffix = String(config.output_suffix ?? "__transformed");
      return mergeColumns([
        ...columns,
        ...transform.columns.map((name) => ({ name: `${name}${suffix}`, type: "number" as const }))
      ]);
    }
    if (transform.type === "sql_expression") {
      return mergeColumns([...columns, {
        name: String(config.output_column ?? "derived_feature"),
        type: String(config.output_type ?? "number") as DatasetColumn["type"]
      }]);
    }
    if (transform.type === "pca") {
      const retained = config.drop_original
        ? columns.filter((column) => !transform.columns.includes(column.name))
        : columns;
      const count = Math.max(0, Number(config.n_components ?? 2));
      const prefix = String(config.output_prefix ?? "pca_");
      return mergeColumns([
        ...retained,
        ...Array.from({ length: count }, (_, index) => ({
          name: `${prefix}${index + 1}`,
          type: "number" as const
        }))
      ]);
    }
    return columns;
  }, sourceColumns);
}

function mergeColumns(columns: DatasetColumn[]) {
  const result = new Map<string, DatasetColumn>();
  for (const column of columns) if (!result.has(column.name)) result.set(column.name, column);
  return [...result.values()];
}

function isUsableDataset(dataset: DataAsset) {
  return dataset.status !== "deleted" && ["csv", "parquet"].includes(dataset.format);
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function needsRowId(definition: FeatureEngineeringDefinition) {
  return ["random", "stratified"].includes(definition.evaluation.split_strategy)
    || (
      definition.evaluation.cross_validation.enabled
      && ["kfold", "stratified"].includes(definition.evaluation.cross_validation.strategy)
    );
}

function needsTarget(definition: FeatureEngineeringDefinition) {
  return definition.evaluation.split_strategy === "stratified"
    || (
      definition.evaluation.cross_validation.enabled
      && definition.evaluation.cross_validation.strategy === "stratified"
    );
}

function needsGroup(definition: FeatureEngineeringDefinition) {
  return definition.evaluation.split_strategy === "group"
    || (
      definition.evaluation.cross_validation.enabled
      && definition.evaluation.cross_validation.strategy === "group"
    );
}

function needsTime(definition: FeatureEngineeringDefinition) {
  return definition.evaluation.split_strategy === "time"
    || (
      definition.evaluation.cross_validation.enabled
      && definition.evaluation.cross_validation.strategy === "time"
    );
}

function title(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
