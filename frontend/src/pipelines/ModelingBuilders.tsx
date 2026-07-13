import {
  AlertTriangle,
  BrainCircuit,
  ListChecks,
  Search,
  SlidersHorizontal,
  Sparkles,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import {
  classificationAlgorithms,
  regressionAlgorithms,
  validateTrainingConfiguration
} from "./modelingContract";
import type {
  ModelingDefaults,
  ScoringDefinition,
  TrainingAlgorithm,
  TrainingAlgorithmSpec,
  TrainingCatalog,
  TrainingDefinition
} from "./modelingContract";
import type { ModelArtifact } from "../api/client";

export function TrainingBuilder({ definition, defaults, disabled, onChange }: {
  definition: TrainingDefinition;
  defaults: ModelingDefaults;
  disabled: boolean;
  onChange: (definition: TrainingDefinition) => void;
}) {
  const [openDialog, setOpenDialog] = useState<"features" | "parameters" | null>(null);
  const { catalog, loading, error } = useTrainingCatalog();
  const update = (patch: Partial<TrainingDefinition>) => onChange({ ...definition, ...patch });
  const algorithms = useMemo(() => catalog?.algorithms.filter((item) =>
    item.problem_types.includes(definition.problem_type)
  ) ?? [], [catalog, definition.problem_type]);
  const selectedAlgorithm = algorithms.find((item) => item.id === definition.algorithm)
    ?? catalog?.algorithms.find((item) => item.id === definition.algorithm);
  const isAutoML = definition.optimization.mode === "automl";
  const automaticCandidates = algorithms.filter((item) => item.available && item.automl_default);
  const validationIssues = validateTrainingConfiguration(definition);
  const updateAlgorithm = (algorithm: TrainingAlgorithm) => update({
    algorithm,
    parameters: Object.fromEntries(
      (catalog?.algorithms.find((item) => item.id === algorithm)?.parameters ?? [])
        .map((parameter) => [parameter.id, parameter.default])
    ),
    early_stopping: false
  });
  const families = Array.from(new Set(algorithms.map((item) => item.family)));
  return <div className="inspector-form modeling-builder">
    <div className="scope-badge">Full-data training with explicit memory and search budgets. No silent sampling.</div>
    <div className="fe-suggestion">
      <Sparkles size={17} />
      <span>Defaults combine the Business Case and the upstream Feature Engineering contract.</span>
    </div>
    <label>Problem type<select value={definition.problem_type} disabled={disabled} onChange={(event) => {
      const problem_type = event.target.value as TrainingDefinition["problem_type"];
      const compatible = catalog?.algorithms.find((item) =>
        item.problem_types.includes(problem_type) && item.available && item.automl_default
      );
      const algorithm = compatible?.id
        ?? (problem_type === "regression" ? regressionAlgorithms[0] : classificationAlgorithms[0]);
      const parameters = Object.fromEntries(
        (compatible?.parameters ?? []).map((parameter) => [parameter.id, parameter.default])
      );
      update({ problem_type, algorithm, parameters, early_stopping: false });
    }}>
      <option value="binary_classification">Binary classification</option>
      <option value="multiclass_classification">Multiclass classification</option>
      <option value="regression">Regression</option>
    </select></label>
    {!isAutoML && <label>Algorithm<select value={definition.algorithm} disabled={disabled}
      onChange={(event) => updateAlgorithm(event.target.value as TrainingAlgorithm)}>
      {!algorithms.length && <option value={definition.algorithm}>
        {loading ? "Loading algorithm catalog…" : definition.algorithm}
      </option>}
      {families.map((family) => <optgroup label={family} key={family}>
        {algorithms.filter((item) => item.family === family).map((algorithm) =>
          <option value={algorithm.id} key={algorithm.id} disabled={!algorithm.available}>
            {algorithm.label}{algorithm.available ? "" : ` — install ${algorithm.dependency}`}
          </option>
        )}
      </optgroup>)}
    </select></label>}
    {isAutoML && <div className="fe-suggestion">
      <BrainCircuit size={17} />
      <span><strong>Algorithm family is selected automatically</strong><br />
        AutoML currently searches {definition.optimization.candidate_algorithms.length
          ? definition.optimization.candidate_algorithms.length
          : automaticCandidates.length} compatible candidate families. Configure an allow-list in Training parameters only when needed.
      </span>
    </div>}
    {catalog && <div className="training-catalog-count">
      <BrainCircuit size={16} />
      <span><strong>{algorithms.filter((item) => item.available).length} executable algorithms</strong>
        <small>{catalog.algorithm_count} registered across classification and regression</small></span>
    </div>}
    {error && <div className="training-warning"><AlertTriangle size={16} /><span>{error}</span></div>}
    {validationIssues.length > 0 && <div className="training-warning training-validation-warning">
      <AlertTriangle size={16} />
      <span><strong>Model settings need attention</strong>
        {validationIssues.slice(0, 4).map((issue) => <small key={issue}>{issue}</small>)}
        {validationIssues.length > 4 && <small>And {validationIssues.length - 4} more validation issue(s).</small>}
      </span>
    </div>}
    {!isAutoML && selectedAlgorithm && <AlgorithmSummary algorithm={selectedAlgorithm} />}
    <label>Model name<input value={definition.model_name} disabled={disabled}
      onChange={(event) => update({ model_name: event.target.value })} /></label>
    <ColumnSelect label="Target column" value={definition.target_column}
      columns={defaults.available_columns} disabled={disabled}
      onChange={(target_column) => update({
        target_column,
        feature_columns: definition.feature_columns.filter((item) => item !== target_column)
      })} />
    <label>Feature selection<select value={definition.feature_selection} disabled={disabled}
      onChange={(event) => update({
        feature_selection: event.target.value as TrainingDefinition["feature_selection"]
      })}>
      <option value="upstream_contract">Use upstream Feature Engineering contract</option>
      <option value="explicit">Select columns manually</option>
    </select></label>
    {isAutoML && definition.auto_feature_engineering.enabled && <div className="fe-suggestion">
      <Sparkles size={17} />
      <span><strong>AutoFE owns the estimator feature contract</strong><br />
        Empty feature selection means that the planner evaluates every supported non-target column.
        A manual list acts as an allow-list before automatic transformations.</span>
    </div>}
    {definition.feature_selection === "upstream_contract" && (
      <div className="fe-suggestion">
        <Sparkles size={17} />
        <span>
          Runtime uses every upstream column marked as a model feature. A direct DE → AutoML
          workflow currently needs an explicit feature selection until model-aware AutoML FE is enabled.
        </span>
      </div>
    )}
    <div className="modeling-action-grid">
      <button className="modeling-config-button" type="button"
        disabled={disabled || definition.feature_selection === "upstream_contract"}
        onClick={() => setOpenDialog("features")}>
        <ListChecks size={18} />
        <span><strong>Add features</strong>
          <small>{definition.feature_selection === "upstream_contract"
            ? "Resolved from the fitted FE manifest at runtime"
            : `${definition.feature_columns.length} selected from ${defaults.available_columns.length} available`}</small></span>
      </button>
      <button className="modeling-config-button" type="button" disabled={disabled}
        onClick={() => setOpenDialog("parameters")}>
        <SlidersHorizontal size={18} />
        <span><strong>Training parameters</strong>
          <small>{parameterSummary(definition, selectedAlgorithm)}</small></span>
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
      subtitle={isAutoML
        ? "Automatic algorithm-family and hyperparameter search · governed full-data execution"
        : `${selectedAlgorithm?.label ?? definition.algorithm} · governed full-data execution`}
      onClose={() => setOpenDialog(null)}>
      <TrainingParameters definition={definition} defaults={defaults} catalog={catalog}
        algorithm={selectedAlgorithm} disabled={disabled} onChange={onChange} />
    </ModelingDialog>}
  </div>;
}

function TrainingParameters({ definition, defaults, catalog, algorithm, disabled, onChange }: {
  definition: TrainingDefinition;
  defaults: ModelingDefaults;
  catalog: TrainingCatalog | null;
  algorithm?: TrainingAlgorithmSpec;
  disabled: boolean;
  onChange: (definition: TrainingDefinition) => void;
}) {
  const update = (patch: Partial<TrainingDefinition>) => onChange({ ...definition, ...patch });
  const updateParameters = (patch: Record<string, unknown>) => update({
    parameters: { ...definition.parameters, ...patch }
  });
  const updateOptimization = (patch: Partial<TrainingDefinition["optimization"]>) => update({
    optimization: { ...definition.optimization, ...patch }
  });
  const updateSearchSpace = (parameterId: string, search: Record<string, unknown>) => updateOptimization({
    search_space: { ...optimization.search_space, [parameterId]: search }
  });
  const resetSearchSpace = (parameterId: string) => {
    const next = { ...optimization.search_space };
    delete next[parameterId];
    updateOptimization({ search_space: next });
  };
  const updateLimits = (patch: Partial<TrainingDefinition["resource_limits"]>) => update({
    resource_limits: { ...definition.resource_limits, ...patch }
  });
  const updateAutoFE = (patch: Partial<TrainingDefinition["auto_feature_engineering"]>) => update({
    auto_feature_engineering: { ...definition.auto_feature_engineering, ...patch }
  });
  const optimization = definition.optimization;
  const metrics = catalog?.metrics[definition.problem_type] ?? [];
  const autoMlCandidates = catalog?.algorithms.filter((item) =>
    item.available && item.problem_types.includes(definition.problem_type) && item.automl_default
  ) ?? [];
  const selectedCandidates = optimization.candidate_algorithms.length
    ? optimization.candidate_algorithms
    : autoMlCandidates.map((item) => item.id);
  const tunableParameters = algorithm?.parameters.filter((parameter) => parameter.search) ?? [];
  const fixedParameters = algorithm?.parameters.filter((parameter) => !parameter.search) ?? [];
  const autoFEHasHoldout = definition.auto_feature_engineering.enabled
    && (defaults.has_validation || Boolean(definition.auto_feature_engineering.row_id_column));
  const optimizationUsesCrossValidation = optimization.mode !== "single"
    && (optimization.validation_strategy === "cross_validation"
      || (optimization.validation_strategy === "auto" && !defaults.has_validation && !autoFEHasHoldout));
  const usesUpstreamFoldPlan = optimizationUsesCrossValidation && defaults.has_cv_plan;
  const estimatedRecipeCount = definition.auto_feature_engineering.enabled
    && definition.auto_feature_engineering.joint_search_enabled
    ? Math.max(1, definition.auto_feature_engineering.max_recipe_candidates)
    : 1;
  const estimatedFoldCount = optimizationUsesCrossValidation
    ? Math.max(2, usesUpstreamFoldPlan ? defaults.cv_folds : optimization.cv_folds)
    : 1;
  const estimatedFits = optimization.max_trials * estimatedFoldCount;
  const twoPhaseSearch = definition.auto_feature_engineering.enabled
    && definition.auto_feature_engineering.joint_search_enabled
    && definition.auto_feature_engineering.two_phase_search_enabled;
  const trialsPerRecipe = optimization.max_trials / estimatedRecipeCount;
  const trialAllocation = Number.isInteger(trialsPerRecipe)
    ? `${trialsPerRecipe}`
    : `${Math.floor(trialsPerRecipe)}–${Math.ceil(trialsPerRecipe)}`;
  return <div className="modeling-modal-content">
    <section className="training-config-section">
      <header><div><strong>Optimization strategy</strong>
        <small>Choose this first; the model form below changes with the selected strategy.</small></div></header>
      <div className="optimization-mode-grid">
        {(catalog?.optimization_modes ?? []).map((mode) => <label key={mode.id}
          className={optimization.mode === mode.id ? "selected" : ""}>
          <input type="radio" name="optimization-mode" value={mode.id}
            checked={optimization.mode === mode.id} disabled={disabled}
            onChange={() => update({
              optimization: { ...optimization, mode: mode.id },
              early_stopping: mode.id === "single" ? definition.early_stopping : false
            })} />
          <span><strong>{mode.label}</strong><small>{mode.description}</small></span>
        </label>)}
      </div>
      {optimizationUsesCrossValidation && defaults.has_fitted_transformations
        && !definition.auto_feature_engineering.enabled &&
        <div className="training-warning"><AlertTriangle size={16} /><span>
          Leakage-safe CV cannot reuse preprocessing fitted on the whole training partition.
          Add an explicit validation output and use holdout optimization. The backend rejects
          potentially leaked CV scores.
        </span></div>}
      {usesUpstreamFoldPlan && !defaults.has_fitted_transformations &&
        <div className="fe-suggestion"><Sparkles size={16} /><span>
          Training will use the upstream auditable {defaults.cv_folds}-fold plan rather than
          generate different folds.
        </span></div>}
      {optimization.mode !== "single" && <div className="step-grid">
        <label>Validation strategy<select value={optimization.validation_strategy} disabled={disabled}
          onChange={(event) => updateOptimization({
            validation_strategy: event.target.value as typeof optimization.validation_strategy
          })}>
          <option value="auto">Auto — holdout if present, otherwise CV</option>
          <option value="holdout" disabled={!defaults.has_validation && !autoFEHasHoldout}>Validation holdout</option>
          <option value="cross_validation"
            disabled={definition.auto_feature_engineering.enabled && defaults.has_fitted_transformations}>
            {definition.auto_feature_engineering.enabled
              ? "Fold-local cross-validation"
              : "Cross-validation on training data"}
          </option>
        </select></label>
        <label>Primary metric<select value={optimization.primary_metric} disabled={disabled}
          onChange={(event) => updateOptimization({ primary_metric: event.target.value })}>
          <option value="auto">Recommended for problem type</option>
          {metrics.map((metric) => <option value={metric.id} key={metric.id}>{metric.label}</option>)}
        </select></label>
        <label>CV folds<input type="number" min={2} max={20}
          value={usesUpstreamFoldPlan ? defaults.cv_folds : optimization.cv_folds}
          disabled={disabled || optimization.validation_strategy === "holdout" || usesUpstreamFoldPlan}
          onChange={(event) => updateOptimization({ cv_folds: Number(event.target.value) })} /></label>
        <label>{optimization.mode === "grid_search" ? "Maximum grid combinations" : "Maximum trials"}<input type="number" min={1} max={optimization.mode === "grid_search" ? 100000 : 1000} value={optimization.max_trials}
          disabled={disabled}
          onChange={(event) => updateOptimization({ max_trials: Number(event.target.value) })} /></label>
        <label>Time budget (seconds)<input type="number" min={10} max={604800}
          value={optimization.timeout_seconds} disabled={disabled}
          onChange={(event) => updateOptimization({ timeout_seconds: Number(event.target.value) })} /></label>
      </div>}
      {optimization.mode !== "single" && <div className="training-help">
        <strong>Validation settings</strong>
        <span>
          Auto uses an explicit validation holdout when the upstream pipeline provides one; otherwise it falls back
          to CV. The primary metric chooses the best trial. CV folds control cross-validation stability/cost.
          Maximum trials caps sampled candidates for random, Optuna and AutoML. For grid search, Maximum grid
          combinations can go up to 100,000 and caps the deterministic grid. The time budget is a hard wall-clock
          safety limit.
        </span>
      </div>}
      {optimization.mode !== "single" && <div className="training-help">
        <strong>Estimated search cost</strong>
        <span>
          <strong>{optimization.max_trials}</strong> is the maximum for the whole search, not a guaranteed completed
          count. With up to <strong>{estimatedRecipeCount}</strong> FE {estimatedRecipeCount === 1 ? "recipe" : "recipes"},
          {twoPhaseSearch
            ? <> every executable recipe first receives <strong>{definition.auto_feature_engineering.exploration_trials_per_recipe} exploration trial(s)</strong>, then up to <strong>{definition.auto_feature_engineering.promotion_top_k}</strong> recipes share the remaining budget.</>
            : <> the budget is allocated as about <strong>{trialAllocation} trials per recipe</strong>.</>} {estimatedFoldCount > 1
            ? <>Each trial is evaluated on <strong>{estimatedFoldCount} folds</strong>, for up to approximately <strong>{estimatedFits} model fits</strong>.</>
            : <>Each trial requires one validation fit, for up to approximately <strong>{estimatedFits} model fits</strong>.</>}
          {" "}The run can complete fewer trials when the time budget expires; the result keeps the best successful
          trial found so far.
        </span>
      </div>}
      {optimization.mode === "automl" && <fieldset className="automl-candidates">
        <legend>AutoML candidates <span>{selectedCandidates.length} selected</span></legend>
        <small>An empty stored selection means the curated, available defaults shown below.</small>
        <div>{autoMlCandidates.map((candidate) => <label key={candidate.id}>
          <input type="checkbox" disabled={disabled} checked={selectedCandidates.includes(candidate.id)}
            onChange={(event) => {
              const next = event.target.checked
                ? [...selectedCandidates, candidate.id]
                : selectedCandidates.filter((item) => item !== candidate.id);
              updateOptimization({ candidate_algorithms: next });
            }} />
          <span><strong>{candidate.label}</strong>
            <small>{candidate.family} · {candidate.scale_profile} · FE {candidate.feature_capabilities.profile}</small></span>
        </label>)}</div>
      </fieldset>}
    </section>
    {optimization.mode === "single" && <section className="training-config-section">
      <header><div><strong>Model and fixed hyperparameters</strong>
        <small>Single model fits exactly these values on the full training scope.</small></div></header>
      {algorithm?.parameters.length
        ? <div className="training-parameter-grid">
          {algorithm.parameters.map((parameter) => <ParameterField key={parameter.id}
            parameter={parameter} value={definition.parameters[parameter.id] ?? parameter.default}
            disabled={disabled} onChange={(value) => updateParameters({ [parameter.id]: value })} />)}
        </div>
        : <div className="inspector-empty compact">This estimator has no configurable hyperparameters.</div>}
    </section>}
    {optimization.mode !== "single" && optimization.mode !== "automl" && <section className="training-config-section">
      <header><div><strong>{searchSpaceTitle(optimization.mode)}</strong>
        <small>{searchSpaceDescription(optimization.mode)}</small></div></header>
      {tunableParameters.length
        ? <SearchSpaceSummary parameters={tunableParameters} mode={optimization.mode}
          searchSpace={optimization.search_space} disabled={disabled}
          onChange={updateSearchSpace} onReset={resetSearchSpace} />
        : <div className="inspector-empty compact">This estimator has no curated tuning space.</div>}
      {fixedParameters.length > 0 && <div className="training-fixed-parameters">
        <strong>Fixed estimator parameters</strong>
        <div className="training-parameter-grid">
          {fixedParameters.map((parameter) => <ParameterField key={parameter.id}
            parameter={parameter} value={definition.parameters[parameter.id] ?? parameter.default}
            disabled={disabled} onChange={(value) => updateParameters({ [parameter.id]: value })} />)}
        </div>
      </div>}
    </section>}
    {optimization.mode === "automl" && <section className="training-config-section">
      <header><div><strong>AutoML search space</strong>
        <small>
          AutoML searches the selected algorithm families and their backend-curated hyperparameter spaces.
        </small></div></header>
      <div className="training-help">
        <strong>No single-model hyperparameters here</strong>
        <span>
          The values for one currently selected estimator would be misleading in AutoML. The run summary records
          the selected algorithm, best parameters, trial history and exact search space used by the backend.
        </span>
      </div>
      <label className="fe-toggle">
        <input type="checkbox" checked={definition.auto_feature_engineering.enabled}
          disabled={disabled}
          onChange={(event) => update({
            auto_feature_engineering: {
              ...definition.auto_feature_engineering,
              enabled: event.target.checked
            },
            optimization: {
              ...definition.optimization,
              validation_strategy: event.target.checked ? "auto" : definition.optimization.validation_strategy
            }
          })} />
        <span><strong>Intelligent AutoFE</strong>
          <small>Profile the full training scope, fit preprocessing only on train, and reuse its state on validation.</small>
        </span>
      </label>
      {definition.auto_feature_engineering.enabled && <>
        <label className="fe-toggle">
          <input type="checkbox" checked={definition.auto_feature_engineering.joint_search_enabled}
            disabled={disabled}
            onChange={(event) => updateAutoFE({ joint_search_enabled: event.target.checked })} />
          <span><strong>Joint FE + model search</strong>
            <small>Compare complete model-aware FE recipe and algorithm pairs on the same holdout or fold-local CV plan.</small>
          </span>
        </label>
        <div className="step-grid">
          <ColumnSelect label="Stable row ID for holdout or CV folds"
            value={definition.auto_feature_engineering.row_id_column}
            columns={defaults.available_columns.filter((item) => item !== definition.target_column)}
            disabled={disabled || defaults.has_validation}
            onChange={(row_id_column) => updateAutoFE({ row_id_column })} />
          <label>Validation share<input type="number" min={0.01} max={0.49} step={0.01}
            value={definition.auto_feature_engineering.validation_size}
            disabled={disabled || defaults.has_validation}
            onChange={(event) => updateAutoFE({ validation_size: Number(event.target.value) })} /></label>
          <label>Fixed numeric scaling<select value={definition.auto_feature_engineering.numeric_scaling}
            disabled={disabled || definition.auto_feature_engineering.numeric_scaling_search}
            onChange={(event) => updateAutoFE({
              numeric_scaling: event.target.value as TrainingDefinition["auto_feature_engineering"]["numeric_scaling"]
            })}>
            <option value="standard">Standard</option>
            <option value="robust">Robust</option>
            <option value="minmax">Min-max</option>
            <option value="none">None</option>
          </select></label>
          <label>One-hot cardinality limit<input type="number" min={2} max={500}
            value={definition.auto_feature_engineering.max_one_hot_categories} disabled={disabled}
            onChange={(event) => updateAutoFE({ max_one_hot_categories: Number(event.target.value) })} /></label>
          <label>Minimum category frequency<input type="number" min={1} max={1000000}
            value={definition.auto_feature_engineering.min_category_frequency} disabled={disabled}
            onChange={(event) => updateAutoFE({ min_category_frequency: Number(event.target.value) })} /></label>
          <label>Maximum FE recipe candidates<input type="number" min={1} max={24}
            value={definition.auto_feature_engineering.max_recipe_candidates}
            disabled={disabled || !definition.auto_feature_engineering.joint_search_enabled}
            onChange={(event) => updateAutoFE({ max_recipe_candidates: Number(event.target.value) })} /></label>
        </div>
        <label className="fe-toggle">
          <input type="checkbox" checked={definition.auto_feature_engineering.two_phase_search_enabled}
            disabled={disabled || !definition.auto_feature_engineering.joint_search_enabled}
            onChange={(event) => updateAutoFE({ two_phase_search_enabled: event.target.checked })} />
          <span><strong>Two-phase recipe scheduler</strong>
            <small>Explore every recipe, then spend the remaining global budget only on the strongest candidates.</small>
          </span>
        </label>
        {definition.auto_feature_engineering.two_phase_search_enabled && <div className="step-grid">
          <label>Exploration trials per recipe<input type="number" min={1} max={10}
            value={definition.auto_feature_engineering.exploration_trials_per_recipe} disabled={disabled}
            onChange={(event) => updateAutoFE({ exploration_trials_per_recipe: Number(event.target.value) })} /></label>
          <label>Exploration time share<input type="number" min={0.1} max={0.8} step={0.05}
            value={definition.auto_feature_engineering.exploration_time_fraction} disabled={disabled}
            onChange={(event) => updateAutoFE({ exploration_time_fraction: Number(event.target.value) })} /></label>
          <label>Recipes promoted<input type="number" min={1} max={12}
            value={definition.auto_feature_engineering.promotion_top_k} disabled={disabled}
            onChange={(event) => updateAutoFE({ promotion_top_k: Number(event.target.value) })} /></label>
        </div>}
        <label className="fe-toggle">
          <input type="checkbox" checked={definition.auto_feature_engineering.numeric_feature_search}
            disabled={disabled || !definition.auto_feature_engineering.joint_search_enabled}
            onChange={(event) => updateAutoFE({ numeric_feature_search: event.target.checked })} />
          <span><strong>Numeric feature generation + selection</strong>
            <small>Compare baseline recipes with fold-local winsorization, signed-log features and low-variance filtering.</small>
          </span>
        </label>
        {definition.auto_feature_engineering.numeric_feature_search && <div className="step-grid">
          <label className="fe-toggle"><input type="checkbox"
            checked={definition.auto_feature_engineering.numeric_scaling_search} disabled={disabled}
            onChange={(event) => updateAutoFE({ numeric_scaling_search: event.target.checked })} />
            <span><strong>Search numeric scaling</strong><small>Compare compatible scaling methods as separate recipes.</small></span>
          </label>
          {definition.auto_feature_engineering.numeric_scaling_search &&
            (["standard", "robust", "minmax", "none"] as const).map((method) => {
              const selected = definition.auto_feature_engineering.numeric_scaling_candidates.includes(method);
              return <label className="fe-toggle" key={method}><input type="checkbox" checked={selected}
                disabled={disabled || (selected && definition.auto_feature_engineering.numeric_scaling_candidates.length === 1)}
                onChange={(event) => updateAutoFE({
                  numeric_scaling_candidates: event.target.checked
                    ? [...definition.auto_feature_engineering.numeric_scaling_candidates, method]
                    : definition.auto_feature_engineering.numeric_scaling_candidates.filter((item) => item !== method)
                })} />
                <span><strong>{method === "minmax" ? "Min-max" : method === "none" ? "None" : method[0].toUpperCase() + method.slice(1)}</strong>
                  <small>{method === "standard" ? "Mean/std scaling" : method === "robust" ? "Median/IQR scaling" : method === "minmax" ? "Bounded non-negative scaling" : "Unscaled numeric values"}</small></span>
              </label>;
            })}
          <label>Winsor lower quantile<input type="number" min={0} max={0.49} step={0.01}
            value={definition.auto_feature_engineering.winsorization_lower_quantile} disabled={disabled}
            onChange={(event) => updateAutoFE({ winsorization_lower_quantile: Number(event.target.value) })} /></label>
          <label>Winsor upper quantile<input type="number" min={0.51} max={1} step={0.01}
            value={definition.auto_feature_engineering.winsorization_upper_quantile} disabled={disabled}
            onChange={(event) => updateAutoFE({ winsorization_upper_quantile: Number(event.target.value) })} /></label>
          <label className="fe-toggle"><input type="checkbox"
            checked={definition.auto_feature_engineering.signed_log_features} disabled={disabled}
            onChange={(event) => updateAutoFE({ signed_log_features: event.target.checked })} />
            <span><strong>Signed-log features</strong><small>Keep originals and add sign(x) · log(1 + |x|).</small></span>
          </label>
          <label className="fe-toggle"><input type="checkbox"
            checked={definition.auto_feature_engineering.low_variance_selection} disabled={disabled}
            onChange={(event) => updateAutoFE({ low_variance_selection: event.target.checked })} />
            <span><strong>Low-variance selection</strong><small>Fit the selector on train/fold-train only.</small></span>
          </label>
          {definition.auto_feature_engineering.low_variance_selection &&
            <label>Variance threshold<input type="number" min={0} step={0.000001}
              value={definition.auto_feature_engineering.variance_threshold} disabled={disabled}
              onChange={(event) => updateAutoFE({ variance_threshold: Number(event.target.value) })} /></label>}
        </div>}
        {!defaults.has_validation && !definition.auto_feature_engineering.row_id_column
          && <div className="training-warning"><AlertTriangle size={16} /><span>
            Choose a stable row ID so AutoFE can create deterministic leakage-safe holdout or CV folds.
          </span></div>}
        <div className="training-help"><strong>Model-aware AutoFE scope</strong><span>
          Classification and regression only. Joint search independently compares baseline, winsorized, signed-log
          and combined numeric recipes plus compatible scaling methods. Tree and non-negative model constraints prune
          redundant or invalid combinations. Cross-validation fits every learned transformation and selector inside
          each fold, then refits the winning complete recipe and model.
        </span></div>
      </>}
    </section>}
    <section className="training-config-section">
      <header><div><strong>Execution and resources</strong>
        <small>Full-matrix algorithms fail before loading if the complete scope exceeds this budget.</small></div></header>
      <div className="step-grid">
        {algorithm?.execution_mode === "incremental" && <label>Maximum epochs<input type="number"
          min={1} max={100} value={definition.epochs} disabled={disabled}
          onChange={(event) => update({ epochs: Number(event.target.value) })} /></label>}
        <label>Batch size<input type="number" min={100} max={100000} value={definition.batch_size}
          disabled={disabled} onChange={(event) => update({ batch_size: Number(event.target.value) })} /></label>
        <label>Random seed<input type="number" value={definition.random_seed} disabled={disabled}
          onChange={(event) => update({ random_seed: Number(event.target.value) })} /></label>
        <label>Memory budget (MiB)<input type="number" min={128} max={262144}
          value={definition.resource_limits.max_memory_mb} disabled={disabled}
          onChange={(event) => updateLimits({ max_memory_mb: Number(event.target.value) })} /></label>
        <label>Parallel estimator jobs<input type="number" min={1} max={64}
          value={definition.resource_limits.max_parallel_jobs} disabled={disabled}
          onChange={(event) => updateLimits({ max_parallel_jobs: Number(event.target.value) })} /></label>
      </div>
      {algorithm?.execution_mode === "incremental" && optimization.mode === "single" &&
        <label className="fe-toggle">
          <input type="checkbox" checked={definition.early_stopping}
            disabled={disabled || !defaults.has_validation}
            onChange={(event) => update({ early_stopping: event.target.checked })} />
          <span><strong>Early stopping</strong>
            <small>{defaults.has_validation
              ? "Keep the best validation model and stop after the patience budget."
              : "Add an explicit validation output in Feature Engineering to enable this."}</small>
          </span>
        </label>}
      {algorithm?.execution_mode === "incremental" && optimization.mode === "single" && definition.early_stopping
        && defaults.has_validation && <div className="step-grid">
        <label>Patience (epochs)<input type="number" min={1} max={50}
          value={definition.early_stopping_patience} disabled={disabled}
          onChange={(event) => update({ early_stopping_patience: Number(event.target.value) })} /></label>
        <label>Minimum improvement<input type="number" min={0} max={1} step={0.0001}
          value={definition.early_stopping_min_delta} disabled={disabled}
          onChange={(event) => update({ early_stopping_min_delta: Number(event.target.value) })} /></label>
      </div>}
    </section>
  </div>;
}

function SearchSpaceSummary({ parameters, mode, searchSpace, disabled, onChange, onReset }: {
  parameters: TrainingAlgorithmSpec["parameters"];
  mode: TrainingDefinition["optimization"]["mode"];
  searchSpace: TrainingDefinition["optimization"]["search_space"];
  disabled: boolean;
  onChange: (parameterId: string, search: Record<string, unknown>) => void;
  onReset: (parameterId: string) => void;
}) {
  return <div className="search-space-grid">
    {parameters.map((parameter) => {
      const search = effectiveSearchSpace(parameter, searchSpace);
      const edited = Boolean(searchSpace[parameter.id]);
      return <div key={parameter.id} className="search-space-card">
      <div className="search-space-card-heading">
        <strong>{parameter.label}</strong>
        {edited && <span>custom</span>}
      </div>
      <code>{formatSearchSpace(search, mode)}</code>
      <small>{searchSpaceHint(parameter, mode)}</small>
      <SearchSpaceEditor parameter={parameter} mode={mode} search={search} disabled={disabled}
        onChange={(next) => onChange(parameter.id, next)} />
      <button type="button" className="link-button" disabled={disabled || !edited}
        onClick={() => onReset(parameter.id)}>Reset to curated</button>
    </div>;
    })}
  </div>;
}

function SearchSpaceEditor({ parameter, mode, search, disabled, onChange }: {
  parameter: TrainingAlgorithmSpec["parameters"][number];
  mode: TrainingDefinition["optimization"]["mode"];
  search: Record<string, unknown> | null;
  disabled: boolean;
  onChange: (search: Record<string, unknown>) => void;
}) {
  if (!search) return null;
  if (isNumericSearchParameter(parameter)) {
    if (mode === "random_search") return <RandomSearchNumericEditor search={search} parameter={parameter}
      disabled={disabled} onChange={onChange} />;
    if (mode === "optuna") return <OptunaNumericEditor search={search} parameter={parameter}
      disabled={disabled} onChange={onChange} />;
    return <NumericSearchEditor search={search} parameter={parameter}
      disabled={disabled} onChange={onChange} />;
  }
  return <CategoricalSearchEditor search={search} parameter={parameter}
    disabled={disabled} onChange={onChange} />;
}

function RandomSearchNumericEditor({ search, parameter, disabled, onChange }: {
  search: Record<string, unknown>;
  parameter: TrainingAlgorithmSpec["parameters"][number];
  disabled: boolean;
  onChange: (search: Record<string, unknown>) => void;
}) {
  const isInteger = parameter.kind === "integer" || search.kind === "int";
  const values = numericSearchValues(search, parameter);
  const includeNone = search.include_null === true
    || (Array.isArray(search.values) && search.values.some((value) => value == null));
  const low = Number(search.low ?? values[0] ?? parameter.default ?? parameter.minimum ?? 0);
  const high = Number(search.high ?? values.at(-1) ?? parameter.default ?? parameter.maximum ?? low);
  const toNumber = (value: string) => isInteger ? Math.trunc(Number(value)) : Number(value);
  const update = (patch: Record<string, unknown>) => onChange({
    kind: isInteger ? "int" : "float", low, high,
    points: Math.max(1, numericSearchPoints(search)), log: search.log === true,
    include_null: includeNone, ...patch
  });
  return <div className="numeric-search-editor tailored-search-editor">
    <div className="search-space-editor-grid">
      <label>Minimum<input type="number" value={low} disabled={disabled} step={isInteger ? 1 : "any"}
        onChange={(event) => update({ low: toNumber(event.target.value) })} /></label>
      <label>Maximum<input type="number" value={high} disabled={disabled} step={isInteger ? 1 : "any"}
        onChange={(event) => update({ high: toNumber(event.target.value) })} /></label>
      <label>Candidate resolution<input type="number" value={numericSearchPoints(search)} disabled={disabled}
        min={1} max={200} step={1} onChange={(event) => update({
          points: Math.max(1, Math.min(200, Math.trunc(Number(event.target.value) || 1)))
        })} /></label>
      <label>Sampling distribution<select value={search.log === true ? "log" : "linear"} disabled={disabled}
        onChange={(event) => update({ log: event.target.value === "log" })}>
        <option value="linear">Uniform / linear</option>
        <option value="log">Log-uniform</option>
      </select></label>
    </div>
    <label className="search-space-log-toggle">
      <input type="checkbox" checked={includeNone} disabled={disabled || !parameter.nullable}
        onChange={(event) => update({ include_null: event.target.checked })} />
      Include None / automatic
    </label>
    <small>Random Search draws up to the trial budget from this reproducible candidate pool. Resolution controls how finely the numeric range is divided.</small>
  </div>;
}

function OptunaNumericEditor({ search, parameter, disabled, onChange }: {
  search: Record<string, unknown>;
  parameter: TrainingAlgorithmSpec["parameters"][number];
  disabled: boolean;
  onChange: (search: Record<string, unknown>) => void;
}) {
  const isInteger = parameter.kind === "integer" || search.kind === "int";
  const values = numericSearchValues(search, parameter);
  const includeNone = search.include_null === true
    || (Array.isArray(search.values) && search.values.some((value) => value == null));
  const low = Number(search.low ?? values[0] ?? parameter.default ?? parameter.minimum ?? 0);
  const high = Number(search.high ?? values.at(-1) ?? parameter.default ?? parameter.maximum ?? low);
  const step = search.step == null ? "" : Number(search.step);
  const isLog = search.log === true;
  const toNumber = (value: string) => isInteger ? Math.trunc(Number(value)) : Number(value);
  const update = (patch: Record<string, unknown>) => onChange({
    kind: isInteger ? "int" : "float", low, high,
    log: isLog, include_null: includeNone, ...patch
  });
  return <div className="numeric-search-editor tailored-search-editor">
    <div className="search-space-editor-grid">
      <label>Lower bound<input type="number" value={low} disabled={disabled} step={isInteger ? 1 : "any"}
        onChange={(event) => update({ low: toNumber(event.target.value) })} /></label>
      <label>Upper bound<input type="number" value={high} disabled={disabled} step={isInteger ? 1 : "any"}
        onChange={(event) => update({ high: toNumber(event.target.value) })} /></label>
      <label>Distribution<select value={isLog ? "log" : "linear"} disabled={disabled}
        onChange={(event) => {
          const log = event.target.value === "log";
          const next = { log } as Record<string, unknown>;
          if (log) next.step = undefined;
          update(next);
        }}>
        <option value="linear">Uniform</option>
        <option value="log">Log-uniform</option>
      </select></label>
      <label>Step <small>(optional; integers use 1 when empty)</small><input type="number" value={step} disabled={disabled || isLog}
        min={isInteger ? 1 : undefined} step={isInteger ? 1 : "any"} placeholder="continuous"
        onChange={(event) => {
          const next = { ...search } as Record<string, unknown>;
          delete next.points;
          if (event.target.value === "") delete next.step;
          else next.step = toNumber(event.target.value);
          onChange(next);
        }} /></label>
    </div>
    <label className="search-space-log-toggle">
      <input type="checkbox" checked={includeNone} disabled={disabled || !parameter.nullable}
        onChange={(event) => update({ include_null: event.target.checked })} />
      Also try None / automatic
    </label>
    <small>Optuna uses completed trials to choose the next value. For numbers, an empty Step means a continuous range; for integers it means every integer. Log-uniform is useful for learning rate and regularization.</small>
  </div>;
}

function NumericSearchEditor({ search, parameter, disabled, onChange }: {
  search: Record<string, unknown>;
  parameter: TrainingAlgorithmSpec["parameters"][number];
  disabled: boolean;
  onChange: (search: Record<string, unknown>) => void;
}) {
  const isInteger = parameter.kind === "integer" || search.kind === "int";
  const rangeSearch = search.kind === "int" || search.kind === "float";
  const values = numericSearchValues(search, parameter);
  const includeNone = search.include_null === true
    || (Array.isArray(search.values) && search.values.some((value) => value == null));
  const rangeLow = Number(search.low ?? values[0] ?? parameter.default ?? parameter.minimum ?? 0);
  const rangeHigh = Number(search.high ?? values[values.length - 1] ?? parameter.default ?? parameter.maximum ?? rangeLow);
  const toNumber = (value: string) => isInteger ? Math.trunc(Number(value)) : Number(value);
  const updateValues = (nextValues: number[], nextIncludeNone = includeNone) => onChange({
    kind: "categorical",
    values: [...(nextIncludeNone ? [null] : []), ...nextValues.map((value) => isInteger ? Math.trunc(value) : value)]
  });
  return <div className="numeric-search-editor">
    <div className="search-space-mode-row">
      <label>Grid mode<select value={rangeSearch ? "range" : "list"} disabled={disabled}
        onChange={(event) => {
          if (event.target.value === "range") {
            onChange({
              kind: isInteger ? "int" : "float",
              low: rangeLow,
              high: rangeHigh,
              points: Math.max(1, numericSearchPoints(search)),
              log: search.log === true,
              include_null: includeNone
            });
          } else {
            updateValues(values.length ? values : [rangeLow]);
          }
        }}>
        <option value="range">Linear / logarithmic range</option>
        <option value="list">Explicit value list</option>
      </select></label>
      <label className="search-space-log-toggle">
        <input type="checkbox" checked={includeNone} disabled={disabled || !parameter.nullable}
          onChange={(event) => {
            if (rangeSearch) onChange({ ...search, include_null: event.target.checked });
            else updateValues(values, event.target.checked);
          }} />
        Include None / automatic
      </label>
    </div>
    {rangeSearch ? <div className="search-space-editor-grid">
      <label>From<input type="number" value={rangeLow} disabled={disabled}
        step={isInteger ? 1 : "any"} onChange={(event) => onChange({
          ...search,
          low: toNumber(event.target.value)
        })} /></label>
      <label>To<input type="number" value={rangeHigh} disabled={disabled}
        step={isInteger ? 1 : "any"} onChange={(event) => onChange({
          ...search,
          high: toNumber(event.target.value)
        })} /></label>
      <label>Values count<input type="number" value={numericSearchPoints(search)} disabled={disabled}
        min={1} max={200} step={1} onChange={(event) => {
          const points = Math.max(1, Math.min(200, Math.trunc(Number(event.target.value) || 1)));
          const next: Record<string, unknown> = { ...search, points };
          delete next.step;
          onChange(next);
        }} /></label>
      <label>Scale<select value={search.log === true ? "log" : "linear"} disabled={disabled}
        onChange={(event) => onChange({ ...search, log: event.target.value === "log" })}>
        <option value="linear">Linear</option>
        <option value="log">Logarithmic</option>
      </select></label>
    </div> : <div className="categorical-search-editor">
      <div className="categorical-values-list">
        {values.map((value, index) => <div key={`${String(value)}-${index}`} className="categorical-value-row">
          <input type="number" value={value} disabled={disabled}
            step={isInteger ? 1 : "any"}
            onChange={(event) => {
              const next = [...values];
              next[index] = toNumber(event.target.value);
              updateValues(next);
            }} />
          <button type="button" className="link-button danger-link"
            disabled={disabled || (values.length <= 1 && !includeNone)}
            onClick={() => updateValues(values.filter((_, itemIndex) => itemIndex !== index))}>
            Remove
          </button>
        </div>)}
      </div>
      <button type="button" className="link-button" disabled={disabled}
        onClick={() => updateValues([...values, values.at(-1) ?? Number(parameter.default ?? parameter.minimum ?? 0)])}>
        Add value
      </button>
      <small>One explicit value is valid when this parameter should not expand the grid.</small>
    </div>}
  </div>;
}

function CategoricalSearchEditor({ search, parameter, disabled, onChange }: {
  search: Record<string, unknown>;
  parameter: TrainingAlgorithmSpec["parameters"][number];
  disabled: boolean;
  onChange: (search: Record<string, unknown>) => void;
}) {
  const values = Array.isArray(search.values) ? search.values : [];
  const includeNone = values.some((value) => value == null);
  const nonNullValues = values.filter((value) => value != null);
  const numericLike = parameter.kind === "integer" || parameter.kind === "number"
    || nonNullValues.every((value) => typeof value === "number");
  const optionValues = parameter.options.length
    ? parameter.options.filter((value) => value != null)
    : Array.from(new Map(nonNullValues.map((value) => [serializedOption(value), value])).values());
  const optionKeys = new Set(optionValues.map(serializedOption));
  const selectedOptionValues = optionValues.length
    ? nonNullValues.filter((value) => optionKeys.has(serializedOption(value)))
    : nonNullValues;
  const updateValues = (nextValues: unknown[]) => onChange({
    ...search,
    values: [...(includeNone ? [null] : []), ...nextValues]
  });
  const setIncludeNone = (checked: boolean) => onChange({
    ...search,
    values: [...(checked ? [null] : []), ...selectedOptionValues]
  });
  const toggleOption = (option: unknown, checked: boolean) => {
    const serialized = serializedOption(option);
    const next = checked
      ? [...selectedOptionValues, option]
      : selectedOptionValues.filter((value) => serializedOption(value) !== serialized);
    if (!next.length && !includeNone) return;
    updateValues(next);
  };
  if (optionValues.length) {
    return <div className="categorical-search-editor">
      <label className="search-space-log-toggle">
        <input type="checkbox" checked={includeNone} disabled={disabled || !parameter.nullable}
          onChange={(event) => setIncludeNone(event.target.checked)} />
        Include None / automatic
      </label>
      <details className="search-space-multiselect">
        <summary>
          <span>{selectedSearchSummary(selectedOptionValues)}</span>
          <small>{selectedOptionValues.length} selected</small>
        </summary>
        <div className="search-space-option-list">
          {optionValues.map((option, index) => {
            const serialized = serializedOption(option);
            const checked = selectedOptionValues.some((value) => serializedOption(value) === serialized);
            return <label key={`${parameter.id}-${index}-${serialized}`}>
              <input type="checkbox" checked={checked} disabled={disabled}
                onChange={(event) => toggleOption(option, event.target.checked)} />
              <span>{displaySearchOption(option)}</span>
            </label>;
          })}
        </div>
      </details>
    </div>;
  }
  return <div className="categorical-search-editor">
    <label className="search-space-log-toggle">
      <input type="checkbox" checked={includeNone} disabled={disabled || !parameter.nullable}
        onChange={(event) => setIncludeNone(event.target.checked)} />
      Include None / automatic
    </label>
    <div className="categorical-values-list">
      {nonNullValues.map((value, index) => <div key={`${String(value)}-${index}`} className="categorical-value-row">
        <input type={numericLike ? "number" : "text"} value={formatSearchValue(value)} disabled={disabled}
          step={parameter.kind === "integer" ? 1 : "any"}
          onChange={(event) => {
            const next = [...nonNullValues];
            next[index] = numericLike
              ? parameter.kind === "integer"
                ? Math.trunc(Number(event.target.value))
                : Number(event.target.value)
              : event.target.value;
            updateValues(next);
          }} />
        <button type="button" className="link-button danger-link" disabled={disabled}
          onClick={() => updateValues(nonNullValues.filter((_, itemIndex) => itemIndex !== index))}>
          Remove
        </button>
      </div>)}
    </div>
    <button type="button" className="link-button" disabled={disabled}
      onClick={() => updateValues([...nonNullValues, numericLike ? 0 : ""])}>
      Add value
    </button>
    <small>{numericLike
      ? "Use separate rows; None / automatic is controlled by the checkbox above."
      : "Use separate text rows; None / automatic is controlled by the checkbox above."}</small>
  </div>;
}

function effectiveSearchSpace(
  parameter: TrainingAlgorithmSpec["parameters"][number],
  overrides: TrainingDefinition["optimization"]["search_space"],
): Record<string, unknown> | null {
  return overrides[parameter.id] ?? parameter.search;
}

function formatSearchSpace(
  search: Record<string, unknown> | null,
  mode: TrainingDefinition["optimization"]["mode"] = "grid_search",
): string {
  if (!search) return "fixed";
  if (search.kind === "categorical" && Array.isArray(search.values)) {
    return search.values.map((value) => value == null ? "None" : String(value)).join(" · ");
  }
  const low = search.low == null ? "?" : String(search.low);
  const high = search.high == null ? "?" : String(search.high);
  const points = mode === "optuna"
    ? (search.step == null
      ? (search.kind === "int" ? ", integer step 1" : ", continuous")
      : `, step ${search.step}`)
    : `, ${numericSearchPoints(search)} ${mode === "random_search" ? "candidate points" : "values"}`;
  const scale = search.log ? "log" : "linear";
  const nullable = search.include_null === true ? ", + None" : "";
  return `${low} → ${high}${points}, ${scale}${nullable}`;
}

function searchSpaceTitle(mode: TrainingDefinition["optimization"]["mode"]): string {
  if (mode === "random_search") return "Random Search sampling space";
  if (mode === "optuna") return "Optuna suggestion space";
  return "Curated search space";
}

function searchSpaceDescription(mode: TrainingDefinition["optimization"]["mode"]): string {
  if (mode === "random_search") {
    return "Set reproducible sampling bounds and candidate resolution. Fixed estimator parameters below stay constant.";
  }
  if (mode === "optuna") {
    return "Set the domains Optuna can learn from across trials. Fixed estimator parameters below stay constant.";
  }
  return "Tunable parameters are generated by the backend catalog. Fixed parameters below stay constant unless edited.";
}

function numericSearchPoints(search: Record<string, unknown>): number {
  const points = Number(search.points);
  return Number.isFinite(points) && points >= 1 ? Math.trunc(points) : 3;
}

function formatSearchValue(value: unknown): string {
  return value == null ? "null" : String(value);
}

function isNumericSearchParameter(parameter: TrainingAlgorithmSpec["parameters"][number]) {
  return parameter.kind === "integer" || parameter.kind === "number";
}

function numericSearchValues(
  search: Record<string, unknown>,
  parameter: TrainingAlgorithmSpec["parameters"][number],
): number[] {
  if (Array.isArray(search.values)) {
    return search.values
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  }
  const low = Number(search.low ?? parameter.default ?? parameter.minimum ?? 0);
  const high = Number(search.high ?? low);
  const points = Math.max(1, numericSearchPoints(search));
  if (points === 1) return [parameter.kind === "integer" ? Math.trunc(low) : low];
  const values = Array.from({ length: points }, (_, index) => {
    const fraction = index / Math.max(1, points - 1);
    if (search.log && low > 0 && high > 0) {
      return Math.exp(Math.log(low) + (Math.log(high) - Math.log(low)) * fraction);
    }
    return low + (high - low) * fraction;
  });
  return Array.from(new Set(values.map((value) => parameter.kind === "integer" ? Math.round(value) : value)));
}

function displaySearchOption(value: unknown): string {
  if (Array.isArray(value)) return `[${value.join(", ")}]`;
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function selectedSearchSummary(values: unknown[]): string {
  if (!values.length) return "Choose values";
  const first = displaySearchOption(values[0]);
  if (values.length === 1) return first;
  if (values.length === 2) return `${first} + 1 more`;
  return `${first} + ${values.length - 1} more`;
}

function searchSpaceHint(
  parameter: TrainingAlgorithmSpec["parameters"][number],
  mode: TrainingDefinition["optimization"]["mode"],
): string {
  const search = parameter.search;
  if (!search) return "Held constant for every trial.";
  const condition = parameter.active_when && Object.entries(parameter.active_when)
    .map(([controller, values]) => `${controller} is ${values.map(displaySearchOption).join(" or ")}`)
    .join(" and ");
  const dependencyHint = condition ? ` Only expanded for branches where ${condition}.` : "";
  if (mode === "grid_search") return `Grid search evaluates deterministic discrete values from this curated range.${dependencyHint}`;
  if (mode === "random_search") return `Random search samples reproducibly from this curated space using the training seed.${dependencyHint}`;
  return `Optuna suggests values from this curated space using a seeded sampler.${dependencyHint}`;
}

function ParameterField({ parameter, value, disabled, onChange }: {
  parameter: TrainingAlgorithmSpec["parameters"][number];
  value: unknown;
  disabled: boolean;
  onChange: (value: unknown) => void;
}) {
  const hint = <small>{parameter.description || (
    parameter.search ? "Default value; search strategies tune this from the curated space." : "Fixed unless edited manually."
  )}</small>;
  if (parameter.kind === "boolean") {
    return <label>{parameter.label}<select value={value === true ? "true" : "false"} disabled={disabled}
      onChange={(event) => onChange(event.target.value === "true")}>
      <option value="true">Yes</option><option value="false">No</option>
    </select>{hint}</label>;
  }
  if (parameter.kind === "select") {
    return <label>{parameter.label}<select value={serializedOption(value)} disabled={disabled}
      onChange={(event) => onChange(JSON.parse(event.target.value) as unknown)}>
      {parameter.options.map((option, index) => <option value={serializedOption(option)}
        key={`${parameter.id}-${index}`}>{option == null ? "None / automatic" : String(option)}</option>)}
    </select>{hint}</label>;
  }
  if (parameter.kind === "integer_list") {
    const displayed = Array.isArray(value) ? value.join(", ") : String(value ?? "");
    return <label>{parameter.label}<input value={displayed} disabled={disabled}
      onChange={(event) => onChange(event.target.value.split(",")
        .map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0))} />
      {hint}</label>;
  }
  return <label>{parameter.label}<input type="number"
    value={value == null ? "" : Number(value)}
    min={parameter.minimum ?? undefined} max={parameter.maximum ?? undefined}
    step={parameter.step ?? (parameter.kind === "integer" ? 1 : "any")}
    disabled={disabled} onChange={(event) => onChange(
      event.target.value === "" && parameter.nullable
        ? null
        : parameter.kind === "integer"
          ? Math.trunc(Number(event.target.value))
          : Number(event.target.value)
    )} />{hint}</label>;
}

function AlgorithmSummary({ algorithm }: { algorithm: TrainingAlgorithmSpec }) {
  return <div className="algorithm-summary">
    <div><strong>{algorithm.family}</strong>
      <span className={`scale-profile ${algorithm.scale_profile}`}>{algorithm.scale_profile}</span>
      <span>{algorithm.execution_mode === "incremental" ? "streaming fit" : "full matrix"}</span></div>
    <p>{algorithm.description}</p>
    {algorithm.notes.map((note) => <small key={note}><AlertTriangle size={13} />{note}</small>)}
  </div>;
}

function useTrainingCatalog() {
  const [state, setState] = useState<{
    catalog: TrainingCatalog | null;
    loading: boolean;
    error: string;
  }>({ catalog: null, loading: true, error: "" });
  useEffect(() => {
    let active = true;
    void api.getModelTrainingCatalog<TrainingCatalog>()
      .then((catalog) => {
        if (active) setState({ catalog, loading: false, error: "" });
      })
      .catch((catalogError: unknown) => {
        if (active) setState({
          catalog: null,
          loading: false,
          error: catalogError instanceof Error
            ? `Algorithm catalog is unavailable: ${catalogError.message}`
            : "Algorithm catalog is unavailable."
        });
      });
    return () => { active = false; };
  }, []);
  return state;
}

function serializedOption(value: unknown) {
  return JSON.stringify(value);
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

function parameterSummary(definition: TrainingDefinition, algorithm?: TrainingAlgorithmSpec) {
  const early = definition.early_stopping ? ` · early stopping, patience ${definition.early_stopping_patience}` : "";
  const execution = algorithm?.execution_mode === "incremental"
    ? `max ${definition.epochs} epochs`
    : `${definition.resource_limits.max_memory_mb} MiB memory budget`;
  const mode = definition.optimization.mode === "single"
    ? "single fit"
    : definition.optimization.mode.replaceAll("_", " ");
  return `${mode} · ${execution}${early}`;
}

export function ScoringBuilder({ definition, defaults, models, disabled, onChange }: {
  definition: ScoringDefinition;
  defaults: ModelingDefaults;
  models: ModelArtifact[];
  disabled: boolean;
  onChange: (definition: ScoringDefinition) => void;
}) {
  const update = (patch: Partial<ScoringDefinition>) => onChange({ ...definition, ...patch });
  const pinnedModel = models.find((model) => model.id === definition.model_artifact_id);
  return <div className="inspector-form modeling-builder">
    <div className="scope-badge">
      {definition.purpose === "batch"
        ? "Full-scope batch inference with an immutable model and fitted FE state."
        : "Uses the exact model port and scans every test row."}
    </div>
    {definition.purpose === "batch" && (
      <label>Pinned model<input
        value={pinnedModel ? `${pinnedModel.name} · ${pinnedModel.version}` : definition.model_artifact_id}
        readOnly /></label>
    )}
    <ColumnSelect label="Row ID column" value={definition.row_id_column}
      columns={defaults.available_columns} disabled={disabled}
      onChange={(row_id_column) => update({ row_id_column })} />
    {definition.purpose === "test" && (
      <ColumnSelect label="Target column for test metrics" value={definition.target_column}
        columns={defaults.available_columns} optional disabled={disabled}
        onChange={(target_column) => update({ target_column })} />
    )}
    <label>Prediction column<input value={definition.prediction_column} disabled={disabled}
      onChange={(event) => update({ prediction_column: event.target.value })} /></label>
    <label>Output dataset name<input value={definition.dataset_name} disabled={disabled}
      onChange={(event) => update({ dataset_name: event.target.value })} /></label>
    {definition.purpose === "test" && (
      <label>Scoring report name<input value={definition.report_name} disabled={disabled}
        onChange={(event) => update({ report_name: event.target.value })} /></label>
    )}
    <label>Batch size<input type="number" min={100} max={100000} value={definition.batch_size} disabled={disabled}
      onChange={(event) => update({ batch_size: Number(event.target.value) })} /></label>
    <small>{definition.purpose === "batch"
      ? "Output: immutable Parquet prediction dataset. Performance metrics require a later monitoring pipeline with actuals."
      : "Output: Parquet test predictions and performance metrics."}</small>
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
