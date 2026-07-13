import { Brain, Download, Eye, GitBranch, History, Play, Plus, Rocket, Search, Share2, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  DataAsset,
  DatasetLineageReference,
  BusinessCase,
  Deployment,
  ModelArtifact,
  Pipeline,
  ScoreResponse
} from "../api/client";
import { AssetList } from "../components/AssetList";
import { ArtifactFilters, pipelineMatches } from "../components/ArtifactFilters";
import { DatasetLineageList } from "./DatasetLineageList";

type NoticeSetter = (message: string) => void;

export function ModelsPanel({
  models,
  businessCases,
  pipelines,
  initialBusinessCaseId = "",
  onOpenDataset
}: {
  models: ModelArtifact[];
  businessCases: BusinessCase[];
  pipelines: Pipeline[];
  initialBusinessCaseId?: string;
  onOpenDataset?: (datasetId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [businessCaseId, setBusinessCaseId] = useState(initialBusinessCaseId);
  const [purposeFilter, setPurposeFilter] = useState("");
  const [pipelineFilter, setPipelineFilter] = useState("");
  const [selectedModel, setSelectedModel] = useState<ModelArtifact | null>(null);
  const [historyModel, setHistoryModel] = useState<ModelArtifact | null>(null);
  const businessCaseById = useMemo(
    () => new Map(businessCases.map((item) => [item.id, item])),
    [businessCases]
  );
  const pipelineById = useMemo(
    () => new Map(pipelines.map((item) => [item.id, item])),
    [pipelines]
  );
  const modelFamilies = useMemo(() => {
    const grouped = new Map<string, ModelArtifact[]>();
    for (const model of models) {
      const versions = grouped.get(model.logical_id) ?? [];
      versions.push(model);
      grouped.set(model.logical_id, versions);
    }
    return [...grouped.values()].map((versions) => {
      const ordered = [...versions].sort((left, right) => right.version_number - left.version_number);
      return { latest: ordered[0], versions: ordered };
    });
  }, [models]);
  const visibleFamilies = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return modelFamilies.filter(({ latest, versions }) =>
      (!businessCaseId || latest.business_case_id === businessCaseId)
      && pipelineMatches(latest.pipeline_id, pipelines, purposeFilter, pipelineFilter)
      && (!normalized || [
        latest.name,
        latest.algorithm,
        latest.problem_type,
        ...versions.map((version) => version.version)
      ].some((value) => value.toLowerCase().includes(normalized)))
    );
  }, [businessCaseId, modelFamilies, pipelineFilter, pipelines, purposeFilter, query]);
  const availablePipelines = businessCaseId
    ? pipelines.filter((pipeline) => pipeline.business_case_id === businessCaseId)
    : pipelines;

  useEffect(() => setBusinessCaseId(initialBusinessCaseId), [initialBusinessCaseId]);

  return (
    <section className="model-registry-screen">
      <div className="panel model-registry-panel">
        <div className="catalog-toolbar">
          <div>
            <span className="builder-kicker">Governance</span>
            <h2>Model registry</h2>
            <p>
              {visibleFamilies.length} of {modelFamilies.length} model families shown
              {" · "}{models.length} immutable versions
            </p>
          </div>
          <div className="model-registry-summary">
            <Brain size={18} />
            <span>Training is managed through versioned pipelines</span>
          </div>
        </div>

        <div className="model-registry-filters">
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search models"
              placeholder="Search by model name, algorithm, version or problem"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label>
            <span><SlidersHorizontal size={14} /> Business case</span>
            <select value={businessCaseId} onChange={(event) => {
              setBusinessCaseId(event.target.value);
              setPipelineFilter("");
            }}>
              <option value="">All business cases</option>
              {businessCases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
        </div>
        <ArtifactFilters
          pipelines={availablePipelines}
          purpose={purposeFilter}
          pipelineId={pipelineFilter}
          onPurposeChange={setPurposeFilter}
          onPipelineChange={setPipelineFilter}
        />

        <div className="model-registry-table" role="table" aria-label="Model registry">
          <div className="model-registry-row head" role="row">
            <span>Model</span>
            <span>Business case</span>
            <span>Algorithm</span>
            <span>Created</span>
            <span>Status</span>
            <span />
          </div>
          {visibleFamilies.map(({ latest: model, versions }) => (
            <div className="model-registry-row" role="row" key={model.id}>
              <span>
                <strong>{model.name}</strong>
                <small>
                  {model.version} latest · {versions.length} version{versions.length === 1 ? "" : "s"}
                  {" · "}{model.problem_type || "problem not recorded"}
                </small>
              </span>
              <span>
                <strong>{businessCaseById.get(model.business_case_id)?.name ?? "Unassigned"}</strong>
                <small>{pipelineById.get(model.pipeline_id)?.name ?? `run ${shortId(model.pipeline_run_id)}`}</small>
              </span>
              <span>{model.algorithm}</span>
              <span>{formatDate(model.created_at)}</span>
              <span><i className={`pipeline-status ${model.stage}`}>{model.stage}</i></span>
              <span>
                <div className="model-row-actions">
                  <button className="secondary-button compact-button" type="button" onClick={() => setHistoryModel(model)}>
                    <History size={14} /> Versions
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => setSelectedModel(model)}>
                    <Eye size={14} /> View latest
                  </button>
                </div>
              </span>
            </div>
          ))}
          {!visibleFamilies.length && (
            <div className="catalog-empty">No models match the selected name and Business Case filters.</div>
          )}
        </div>
      </div>
      {selectedModel && (
        <ModelDetailsDialog
          model={selectedModel}
          businessCaseName={businessCaseById.get(selectedModel.business_case_id)?.name ?? "Unassigned"}
          pipelineName={pipelineById.get(selectedModel.pipeline_id)?.name ?? "Unknown pipeline"}
          onClose={() => setSelectedModel(null)}
          onOpenDataset={onOpenDataset}
        />
      )}
      {historyModel && (
        <ModelVersionHistoryDialog
          model={historyModel}
          businessCaseName={businessCaseById.get(historyModel.business_case_id)?.name ?? "Unassigned"}
          pipelineName={pipelineById.get(historyModel.pipeline_id)?.name ?? "Unknown pipeline"}
          onClose={() => setHistoryModel(null)}
          onView={(version) => {
            setHistoryModel(null);
            setSelectedModel(version);
          }}
        />
      )}
    </section>
  );
}

export function ModelVersionHistoryDialog({
  model,
  businessCaseName,
  pipelineName,
  onClose,
  onView
}: {
  model: ModelArtifact;
  businessCaseName: string;
  pipelineName: string;
  onClose: () => void;
  onView: (model: ModelArtifact) => void;
}) {
  const [versions, setVersions] = useState<ModelArtifact[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.listModelVersions(model.logical_id)
      .then((items) => active && setVersions([...items].sort((left, right) => right.version_number - left.version_number)))
      .catch((requestError) => active && setError(
        requestError instanceof Error ? requestError.message : "Could not load model versions"
      ));
    return () => { active = false; };
  }, [model.logical_id]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog model-version-dialog" role="dialog" aria-modal="true" aria-label={`Versions of ${model.name}`}>
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Model family</span>
            <h2>{model.name}</h2>
            <p>{businessCaseName} · {pipelineName}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close model versions"><X size={18} /></button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {!versions.length && !error && <div className="empty-state">Loading model versions…</div>}
        <div className="model-version-list">
          {versions.map((version, index) => (
            <article key={version.id}>
              <div className="model-version-marker"><span>{version.version}</span></div>
              <div>
                <strong>
                  {version.version}
                  {index === 0 && <i className="pipeline-status published">latest</i>}
                </strong>
                <span>{formatDate(version.created_at)} · run {shortId(version.pipeline_run_id)}</span>
                <small>
                  pipeline definition {shortId(version.pipeline_version_id)}
                  {" · "}model hash {shortId(version.model_hash)}
                </small>
              </div>
              <button className="secondary-button compact-button" type="button" onClick={() => onView(version)}>
                <Eye size={14} /> View
              </button>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ModelDetailsDialog({
  model,
  businessCaseName,
  pipelineName,
  onClose,
  onOpenDataset
}: {
  model: ModelArtifact;
  businessCaseName: string;
  pipelineName: string;
  onClose: () => void;
  onOpenDataset?: (datasetId: string) => void;
}) {
  const [tab, setTab] = useState<"overview" | "training" | "search" | "parameters" | "lineage">("overview");
  const [dataLineage, setDataLineage] = useState<DatasetLineageReference[]>([]);
  const [lineageError, setLineageError] = useState("");
  const weights = model.model_parameters.weights ?? [];
  const optimization = optimizationSummary(model.metrics);
  useEffect(() => {
    if (model.id.startsWith("dry-run:")) {
      setDataLineage([]);
      return;
    }
    let active = true;
    api.getModelDataLineage(model.id)
      .then((items) => active && setDataLineage(items))
      .catch((error) => active && setLineageError(
        error instanceof Error ? error.message : "Could not load model data lineage"
      ));
    return () => { active = false; };
  }, [model.id]);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog model-details-dialog" role="dialog" aria-modal="true" aria-label={`Model details: ${model.name}`}>
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Model version</span>
            <h2>{model.name}</h2>
            <p>{businessCaseName} · {pipelineName} · {model.version}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close model details"><X size={18} /></button>
        </div>
        <div className="model-detail-tabs" role="tablist">
          {(["overview", "training", "search", "parameters", "lineage"] as const).map((item) => (
            <button className={tab === item ? "active" : ""} type="button" key={item} onClick={() => setTab(item)}>
              {item === "search" ? searchTabLabel(optimization) : item}
            </button>
          ))}
        </div>
        {tab === "overview" && (
          <>
            <div className="model-detail-metrics">
              <DetailMetric label="Stage" value={model.stage} />
              <DetailMetric label="Algorithm" value={model.algorithm} />
              <DetailMetric label="Problem" value={model.problem_type || "not recorded"} />
              <DetailMetric label="Target" value={model.target_column || "not recorded"} />
            </div>
            <section className="model-detail-section">
              <h3>Evaluation metrics</h3>
              <MetricsGrid metrics={model.metrics} />
            </section>
            {optimization && <OptimizationWinner optimization={optimization} />}
            <section className="model-detail-section">
              <h3>Feature contract</h3>
              <div className="model-feature-list">{model.feature_columns.map((item) => <code key={item}>{item}</code>)}</div>
            </section>
            <DatasetLineageList
              items={dataLineage}
              error={lineageError}
              onOpenDataset={onOpenDataset}
            />
          </>
        )}
        {tab === "training" && (
          <section className="model-detail-section">
            <h3>Training configuration and hyperparameters</h3>
            <TrainingConfigSummary config={model.training_config} />
          </section>
        )}
        {tab === "search" && (
          <SearchDetailsTab optimization={optimization} />
        )}
        {tab === "parameters" && (
          <section className="model-detail-section">
            <h3>Fitted model parameters</h3>
            <p className="model-detail-note">
              {weights.length} of {model.model_parameters.total_weight_count ?? weights.length} weights shown
              {model.model_parameters.truncated ? " · bounded registry preview" : ""}.
            </p>
            <div className="model-weights-table">
              <div className="head"><span>Class</span><span>Feature</span><span>Weight</span></div>
              {weights.map((item, index) => (
                <div key={`${item.feature}-${index}`}>
                  <span>{item.class === null ? "—" : String(item.class)}</span>
                  <code>{item.feature}</code>
                  <strong>{formatNumber(item.weight)}</strong>
                </div>
              ))}
              {!weights.length && <div className="catalog-empty">No inspectable weights were recorded.</div>}
            </div>
            {(model.model_parameters.intercepts?.length ?? 0) > 0 && (
              <p className="model-detail-note">Intercepts: {model.model_parameters.intercepts?.map(formatNumber).join(", ")}</p>
            )}
          </section>
        )}
        {tab === "lineage" && (
          <section className="model-detail-section">
            <h3><GitBranch size={16} /> Reproducibility and lineage</h3>
            <KeyValueGrid values={{
              artifact_id: model.id,
              model_hash: model.model_hash,
              pipeline_id: model.pipeline_id,
              pipeline_version_id: model.pipeline_version_id,
              pipeline_run_id: model.pipeline_run_id,
              pipeline_step_id: model.pipeline_step_id,
              input_artifact_ids: model.lineage.input_artifact_ids,
              created_at: model.created_at
            }} empty="No lineage recorded." />
          </section>
        )}
      </div>
    </div>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

type OptimizationTrial = {
  number?: number;
  status?: string;
  algorithm?: string;
  score?: number | null;
  fold_scores?: number[];
  parameters?: Record<string, unknown>;
  error?: string;
};

type OptimizationSummary = {
  mode?: string;
  primary_metric?: string;
  validation_strategy?: string;
  random_seed?: number;
  trial_count?: number;
  planned_trial_count?: number;
  total_candidate_count?: number;
  max_trials?: number;
  successful_trial_count?: number;
  failed_trial_count?: number;
  best_score?: number | null;
  best_algorithm?: string;
  best_parameters?: Record<string, unknown>;
  search_space?: Record<string, unknown>;
  trials?: OptimizationTrial[];
  timed_out?: boolean;
  stopped_by_max_trials?: boolean;
  elapsed_seconds?: number;
  timeout_seconds?: number;
  cv_fold_source?: string;
};

function optimizationSummary(metrics: Record<string, unknown>): OptimizationSummary | null {
  const value = metrics.optimization;
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as OptimizationSummary
    : null;
}

function searchTabLabel(optimization: OptimizationSummary | null) {
  if (!optimization?.mode || optimization.mode === "single") return "Search details";
  if (optimization.mode === "grid_search") return "Grid search details";
  if (optimization.mode === "random_search") return "Random search details";
  if (optimization.mode === "optuna") return "Optuna details";
  if (optimization.mode === "automl") return "AutoML details";
  return "Search details";
}

function MetricsGrid({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics)
    .filter(([key, value]) => key !== "optimization" && value !== "" && value !== undefined && value !== null);
  if (!entries.length) return <div className="empty-state">No evaluation metrics recorded.</div>;
  return <div className="model-key-value-grid">
    {entries.map(([key, value]) => (
      <div key={key}><span>{key.replaceAll("_", " ")}</span><code>{displayValue(value)}</code></div>
    ))}
  </div>;
}

function OptimizationWinner({ optimization }: { optimization: OptimizationSummary }) {
  return <section className="model-detail-section optimization-winner">
    <h3>{searchTabLabel(optimization)}</h3>
    <div className="model-detail-metrics">
      <DetailMetric label="Winning model" value={optimization.best_algorithm || "not recorded"} />
      <DetailMetric label="Best score" value={optimization.best_score == null ? "—" : formatNumber(optimization.best_score)} />
      <DetailMetric label="Primary metric" value={optimization.primary_metric || "auto"} />
      <DetailMetric label="Trials" value={`${optimization.successful_trial_count ?? 0}/${optimization.trial_count ?? 0} succeeded`} />
    </div>
    {optimization.best_parameters && (
      <div className="parameter-chip-list">
        {Object.entries(optimization.best_parameters).map(([key, value]) => (
          <span key={key}><strong>{key}</strong>{displayValue(value)}</span>
        ))}
      </div>
    )}
  </section>;
}

function TrainingConfigSummary({ config }: { config: Record<string, unknown> }) {
  if (!Object.keys(config).length) {
    return <div className="empty-state">Training configuration was not recorded for this model.</div>;
  }
  const parameters = objectValue(config.parameters);
  const optimization = objectValue(config.optimization);
  const resourceLimits = objectValue(config.resource_limits);
  const autoFE = objectValue(config.auto_feature_engineering);
  const jointStudy = objectValue(autoFE.joint_study);
  const scheduler = objectValue(jointStudy.scheduler);
  const crossValidation = objectValue(jointStudy.cross_validation);
  const candidates = Array.isArray(jointStudy.candidates)
    ? jointStudy.candidates.filter((item): item is Record<string, unknown> => Boolean(item)
      && typeof item === "object" && !Array.isArray(item))
    : [];
  const selectedCandidate = candidates.find((item) => item.recipe_id === jointStudy.selected_recipe_id);
  const selectedRecipe = objectValue(selectedCandidate?.recipe_contract);
  const selectedFeatureBudget = objectValue(selectedRecipe.feature_budget);
  const selectedDistributionTransforms = Array.isArray(selectedRecipe.distribution_transforms)
    ? selectedRecipe.distribution_transforms.filter((item): item is Record<string, unknown> => Boolean(item)
      && typeof item === "object" && !Array.isArray(item))
    : [];
  const selectedInteractions = Array.isArray(selectedRecipe.numeric_interactions)
    ? selectedRecipe.numeric_interactions.filter((item): item is Record<string, unknown> => Boolean(item)
      && typeof item === "object" && !Array.isArray(item))
    : [];
  const selectedOOF = objectValue(selectedCandidate?.selected_oof_summary);
  const foldCache = objectValue(selectedCandidate?.fold_cache);
  const completedJointTrials = candidates.reduce((total, candidate) => {
    const candidateOptimization = objectValue(candidate.optimization);
    return total + (typeof candidate.trial_count === "number"
      ? candidate.trial_count
      : typeof candidateOptimization.trial_count === "number"
        ? candidateOptimization.trial_count
      : 0);
  }, 0);
  const basic = {
    algorithm: config.algorithm,
    problem_type: config.problem_type,
    target_column: config.target_column,
    random_seed: config.random_seed,
    batch_size: config.batch_size,
    epochs: config.epochs,
    early_stopping: config.early_stopping,
  };
  return <div className="training-config-readable">
    <KeyValueGrid values={basic} empty="No basic training configuration recorded." />
    <section>
      <h4>Fixed parameters</h4>
      <ParameterList parameters={parameters} empty="No fixed parameters recorded." />
    </section>
    <section>
      <h4>Optimization setup</h4>
      <KeyValueGrid values={{
        mode: optimization.mode,
        validation_strategy: optimization.validation_strategy,
        primary_metric: optimization.primary_metric,
        cv_folds: optimization.cv_folds,
        max_trials: optimization.max_trials,
        timeout_seconds: optimization.timeout_seconds,
        candidate_algorithms: optimization.candidate_algorithms,
      }} empty="No optimization settings recorded." />
    </section>
    <section>
      <h4>Resource limits</h4>
      <KeyValueGrid values={resourceLimits} empty="No resource limits recorded." />
    </section>
    {Object.keys(jointStudy).length > 0 && <section>
      <h4>AutoFE experiment</h4>
      <KeyValueGrid values={{
        mode: jointStudy.mode,
        selected_recipe: jointStudy.selected_recipe_id,
        selected_algorithm: jointStudy.selected_algorithm,
        best_score: jointStudy.best_score,
        recipe_candidates: jointStudy.recipe_candidate_count,
        configured_recipe_candidates: jointStudy.configured_recipe_candidate_count,
        generated_recipe_candidates: jointStudy.generated_recipe_candidate_count,
        scheduler_mode: scheduler.mode,
        promoted_recipes: jointStudy.promoted_recipe_count,
        pruned_recipes: jointStudy.pruned_recipe_count,
        skipped_recipes: jointStudy.skipped_recipe_count,
        configured_trial_budget: jointStudy.trial_budget,
        completed_trials_all_recipes: completedJointTrials,
        exploration_trial_budget: scheduler.allocated_exploration_trials,
        deepening_trial_budget: scheduler.allocated_deepening_trials,
        cv_folds: crossValidation.fold_count,
        cv_scope_rows: crossValidation.planned_row_count,
        oof_predictions: selectedOOF.prediction_count,
        oof_coverage: selectedOOF.coverage,
        oof_fold_score_std: selectedOOF.fold_score_std,
        fold_cache_hits: foldCache.hit_count,
        fold_cache_misses: foldCache.miss_count,
        planner_contract: selectedRecipe.contract_version,
        generated_features: selectedFeatureBudget.generated_feature_count,
        generated_feature_limit: selectedFeatureBudget.requested_max_generated_features,
        memory_feature_capacity: selectedFeatureBudget.memory_feature_capacity,
        distribution_transforms: selectedDistributionTransforms.length,
        numeric_interactions: selectedInteractions.length,
      }} empty="No AutoFE experiment provenance recorded." />
      {(selectedDistributionTransforms.length > 0 || selectedInteractions.length > 0) && <>
        <h4>Planner v2 generation decisions</h4>
        <div className="parameter-chip-list">
          {selectedDistributionTransforms.map((decision, index) => (
            <span key={`distribution-${index}`}><strong>{String(decision.column ?? "feature")}</strong>
              {String(decision.operation ?? "transform")} · {String(decision.reason ?? "profile rule")}</span>
          ))}
          {selectedInteractions.map((decision, index) => (
            <span key={`interaction-${index}`}><strong>{String(decision.output_column ?? "interaction")}</strong>
              {String(decision.operator ?? "interaction")} · {String(decision.reason ?? "pair ranking")}</span>
          ))}
        </div>
      </>}
      <h4>Full-pipeline leaderboard</h4>
      <div className="optimization-trial-table">
        <div className="head"><span>Recipe</span><span>Status</span><span>Variant / scaling</span><span>Algorithm</span><span>Score</span><span>Features / reason</span></div>
        {candidates.map((candidate, index) => {
          const recipe = objectValue(candidate.recipe_contract);
          return <div key={`${String(candidate.recipe_id ?? "recipe")}-${index}`}>
            <code>{String(candidate.recipe_id ?? "—")}</code>
            <span className={`trial-status ${String(candidate.status ?? "unknown")}`}>{String(candidate.status ?? "unknown")}</span>
            <span>{String(recipe.numeric_variant ?? "baseline")} / {String(recipe.numeric_scaling ?? "none")}</span>
            <code>{String(candidate.best_algorithm ?? "—")}</code>
            <strong>{typeof candidate.score === "number" ? formatNumber(candidate.score) : "—"}</strong>
            <span>{candidate.status === "skipped" || candidate.status === "pruned"
              ? String(candidate.reason ?? "budget/capability constraint")
              : candidate.status === "promoted"
                ? `${String(candidate.resolved_feature_count ?? "—")} features · exploration ${formatMaybeNumber(candidate.exploration_score)} · deepening ${formatMaybeNumber(candidate.deepening_score)}`
                : `${String(candidate.resolved_feature_count ?? "—")} features`}</span>
          </div>;
        })}
        {!candidates.length && <div className="catalog-empty">No recipe candidates were recorded.</div>}
      </div>
      {selectedOOF.predictions_persisted === false && <div className="training-help">
        OOF metrics cover the full training scope. Row-level candidate predictions remain temporary and are not
        persisted; only bounded fold summaries are retained.
      </div>}
    </section>}
  </div>;
}

function SearchDetailsTab({ optimization }: { optimization: OptimizationSummary | null }) {
  const [heatmapX, setHeatmapX] = useState("");
  const [heatmapY, setHeatmapY] = useState("");
  if (!optimization || optimization.mode === "single") {
    return <section className="model-detail-section">
      <h3>Search details</h3>
      <div className="empty-state">This model was trained as a single fit, without hyperparameter search.</div>
    </section>;
  }
  const trials = optimization.trials ?? [];
  const heatmapDimensions = heatmapParameterOptions(trials);
  const xAxis = heatmapX || heatmapDimensions[0] || "";
  const yAxis = heatmapY || heatmapDimensions.find((item) => item !== xAxis) || "";
  return <section className="model-detail-section">
    <h3>{searchTabLabel(optimization)}</h3>
    <div className="model-detail-metrics">
      <DetailMetric label="Mode" value={displayMode(optimization.mode)} />
      <DetailMetric label="Validation" value={optimization.validation_strategy || "not recorded"} />
      <DetailMetric label="Candidates evaluated" value={candidateProgress(optimization)} />
      <DetailMetric label="CV folds source" value={optimization.cv_fold_source || "not recorded"} />
      <DetailMetric label="Elapsed / timeout" value={`${formatMaybeNumber(optimization.elapsed_seconds)} / ${formatMaybeNumber(optimization.timeout_seconds)} s`} />
    </div>
    {optimization.stopped_by_max_trials && <div className="training-warning">
      This search was capped by Maximum trials = {optimization.max_trials}. Increase the cap to evaluate more
      combinations, or narrow the search space.
    </div>}
    {optimization.timed_out && <div className="training-warning">
      The time budget expired after {optimization.trial_count ?? 0} of up to {optimization.max_trials ?? optimization.planned_trial_count ?? "—"} allocated trials.
      Maximum trials is a cap, not a promise that every trial will finish. The best successful trial was retained.
    </div>}
    <h4>Winning trial</h4>
    <ParameterList parameters={optimization.best_parameters ?? {}} empty="Best parameters were not recorded." />
    <h4>Search space</h4>
    <SearchSpaceList searchSpace={optimization.search_space} />
    {optimization.mode === "grid_search" ? <>
      <h4>Search result heatmap</h4>
      <SearchHeatmap
        trials={trials}
        dimensions={heatmapDimensions}
        xAxis={xAxis}
        yAxis={yAxis}
        onXAxisChange={setHeatmapX}
        onYAxisChange={setHeatmapY}
      />
    </> : optimization.mode === "random_search" ? <RandomSearchInsights trials={trials} />
      : <OptunaInsights trials={trials} />}
    <h4>Trials</h4>
    <div className="optimization-trial-table">
      <div className="head"><span>#</span><span>Status</span><span>Algorithm</span><span>Score</span><span>Parameters</span><span>Folds</span></div>
      {trials.map((trial, index) => (
        <div key={`${trial.number ?? index}-${trial.algorithm ?? "trial"}`}>
          <span>{(trial.number ?? index) + 1}</span>
          <span className={`trial-status ${trial.status ?? "unknown"}`}>{trial.status ?? "unknown"}</span>
          <code>{trial.algorithm ?? optimization.best_algorithm ?? "—"}</code>
          <strong>{trial.score == null ? "—" : formatNumber(trial.score)}</strong>
          <span>{compactParameters(trial.parameters)}</span>
          <span>{trial.fold_scores?.length ? trial.fold_scores.map(formatNumber).join(", ") : "—"}</span>
        </div>
      ))}
      {!trials.length && <div className="catalog-empty">No trial history was recorded.</div>}
    </div>
  </section>;
}

type ScoredTrial = OptimizationTrial & { score: number; parameters: Record<string, unknown>; index: number };

function successfulTrials(trials: OptimizationTrial[]): ScoredTrial[] {
  return trials.flatMap((trial, index) => typeof trial.score === "number" && Number.isFinite(trial.score)
    && trial.status === "succeeded" && trial.parameters
    ? [{ ...trial, score: trial.score, parameters: trial.parameters, index }]
    : []);
}

function RandomSearchInsights({ trials }: { trials: OptimizationTrial[] }) {
  const successful = useMemo(() => successfulTrials(trials), [trials]);
  const dimensions = useMemo(() => heatmapParameterOptions(trials), [trials]);
  return <div className="search-insights">
    <div className="search-insights-heading">
      <h4>Random Search sample map</h4>
      <small>Each point is one sampled configuration. Point color represents the trial score.</small>
    </div>
    <ScoreDistribution trials={successful} />
    <PairwiseScatter trials={successful} dimensions={dimensions} mode="random" />
  </div>;
}

function OptunaInsights({ trials }: { trials: OptimizationTrial[] }) {
  const successful = useMemo(() => successfulTrials(trials), [trials]);
  const dimensions = useMemo(() => heatmapParameterOptions(trials), [trials]);
  return <div className="search-insights">
    <div className="search-insights-heading">
      <h4>Optuna study insights</h4>
      <small>Read how the study improved, which parameters show the strongest observed signal, and where high-scoring trials concentrate.</small>
    </div>
    <OptimizationHistory trials={successful} />
    <ObservedParameterSignals trials={successful} dimensions={dimensions} />
    <SlicePlot trials={successful} dimensions={dimensions} />
    <PairwiseScatter trials={successful} dimensions={dimensions} mode="optuna" />
  </div>;
}

function OptimizationHistory({ trials }: { trials: ScoredTrial[] }) {
  if (!trials.length) return <div className="empty-state">No successful trials are available for optimization history.</div>;
  const min = Math.min(...trials.map((trial) => trial.score));
  const max = Math.max(...trials.map((trial) => trial.score));
  let best = -Infinity;
  const points = trials.map((trial, index) => {
    best = Math.max(best, trial.score);
    return { x: chartX(index, trials.length), y: chartY(best, min, max) };
  });
  return <section className="search-chart-card history-chart-card">
    <header><strong>Optimization history</strong><small>Dots are trial scores; the line is the best score reached so far.</small></header>
    <svg className="search-svg" viewBox="0 0 720 240" role="img" aria-label="Optuna optimization history">
      <ChartGrid min={min} max={max} />
      <polyline className="best-so-far-line" points={points.map((point) => `${point.x},${point.y}`).join(" ")} />
      {trials.map((trial, index) => <circle key={`${trial.number ?? index}`} className="trial-dot"
        cx={chartX(index, trials.length)} cy={chartY(trial.score, min, max)} r="4"
        fill={scoreColor(trial.score, min, max)}><title>Trial {(trial.number ?? index) + 1}: {formatNumber(trial.score)}</title></circle>)}
      <text className="chart-axis-label" x="360" y="232">Trial</text>
      <text className="chart-axis-label" x="12" y="26">score</text>
    </svg>
  </section>;
}

function ScoreDistribution({ trials }: { trials: ScoredTrial[] }) {
  if (!trials.length) return <div className="empty-state">No successful trials are available for score distribution.</div>;
  const min = Math.min(...trials.map((trial) => trial.score));
  const max = Math.max(...trials.map((trial) => trial.score));
  const bins = Math.min(10, Math.max(4, Math.ceil(Math.sqrt(trials.length))));
  const counts = Array.from({ length: bins }, () => 0);
  for (const trial of trials) {
    const position = max === min ? 0 : Math.min(bins - 1, Math.floor(((trial.score - min) / (max - min)) * bins));
    counts[position] += 1;
  }
  const ceiling = Math.max(...counts, 1);
  return <section className="search-chart-card score-distribution-card">
    <header><strong>Sampled score distribution</strong><small>{trials.length} successful random samples; higher score is better.</small></header>
    <div className="score-histogram" aria-label="Random Search score distribution">
      {counts.map((count, index) => <div key={index} title={`${count} trial(s)`}>
        <i style={{ height: `${Math.max(5, (count / ceiling) * 100)}%` }} />
        <span>{formatNumber(min + ((index + 0.5) / bins) * (max - min))}</span>
      </div>)}
    </div>
  </section>;
}

function ObservedParameterSignals({ trials, dimensions }: { trials: ScoredTrial[]; dimensions: string[] }) {
  const signals = useMemo(() => dimensions.map((parameter) => ({ parameter, signal: parameterSignal(trials, parameter) }))
    .filter((item) => item.signal > 0).sort((left, right) => right.signal - left.signal).slice(0, 6), [trials, dimensions]);
  if (!signals.length) return <div className="empty-state">At least two observed values per parameter are needed to estimate parameter signal.</div>;
  const maximum = Math.max(...signals.map((item) => item.signal));
  return <section className="search-chart-card parameter-signal-card">
    <header><strong>Observed parameter signal</strong><small>Score spread between value groups. It is an exploratory hint, not causal feature importance.</small></header>
    <div className="parameter-signal-bars">
      {signals.map(({ parameter, signal }) => <div key={parameter}>
        <code>{parameter}</code><span><i style={{ width: `${(signal / maximum) * 100}%` }} /></span><strong>{formatNumber(signal)}</strong>
      </div>)}
    </div>
  </section>;
}

function SlicePlot({ trials, dimensions }: { trials: ScoredTrial[]; dimensions: string[] }) {
  const [parameter, setParameter] = useState("");
  const selected = parameter || dimensions[0] || "";
  const points = trials.filter((trial) => selected in trial.parameters);
  if (!selected || !points.length) return <div className="empty-state">No parameter values are available for a slice plot.</div>;
  const scale = parameterScale(points, selected);
  const min = Math.min(...points.map((trial) => trial.score));
  const max = Math.max(...points.map((trial) => trial.score));
  return <section className="search-chart-card slice-chart-card">
    <header><strong>Parameter slice</strong><label>Parameter<select value={selected} onChange={(event) => setParameter(event.target.value)}>
      {dimensions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></header>
    <small>Each dot is a completed trial. The horizontal position is this parameter; the vertical position is the trial score.</small>
    <svg className="search-svg" viewBox="0 0 720 240" role="img" aria-label={`Parameter slice for ${selected}`}>
      <ChartGrid min={min} max={max} />
      {points.map((trial, index) => <circle key={`${trial.number ?? index}`} className="trial-dot"
        cx={parameterX(trial.parameters[selected], scale)} cy={chartY(trial.score, min, max)} r="4"
        fill={scoreColor(trial.score, min, max)}><title>{selected}: {displayValue(trial.parameters[selected])}; score: {formatNumber(trial.score)}</title></circle>)}
      <text className="chart-axis-label" x="360" y="232">{selected}{scale.log ? " (log scale)" : ""}</text>
      <text className="chart-axis-label" x="12" y="26">score</text>
    </svg>
  </section>;
}

function PairwiseScatter({ trials, dimensions, mode }: { trials: ScoredTrial[]; dimensions: string[]; mode: "random" | "optuna" }) {
  const [xChoice, setXChoice] = useState("");
  const [yChoice, setYChoice] = useState("");
  const xAxis = xChoice || dimensions[0] || "";
  const yAxis = yChoice || dimensions.find((item) => item !== xAxis) || "";
  const points = trials.filter((trial) => xAxis in trial.parameters && yAxis in trial.parameters);
  if (!xAxis || !yAxis || !points.length) return <div className="empty-state">Choose two varied parameters to inspect sampled interactions.</div>;
  const xScale = parameterScale(points, xAxis);
  const yScale = parameterScale(points, yAxis);
  const min = Math.min(...points.map((trial) => trial.score));
  const max = Math.max(...points.map((trial) => trial.score));
  return <section className="search-chart-card pairwise-chart-card">
    <header><strong>{mode === "optuna" ? "Optuna parameter interaction" : "Random Search sampled interaction"}</strong>
      <div className="search-chart-controls"><label>X<select value={xAxis} onChange={(event) => setXChoice(event.target.value)}>{dimensions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>Y<select value={yAxis} onChange={(event) => setYChoice(event.target.value)}>{dimensions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div></header>
    <small>Each point is a trial. Color represents score; unlike an exact-value heatmap, continuous values stay readable.</small>
    {xAxis === yAxis ? <div className="empty-state">Choose two different parameters.</div> : <svg className="search-svg" viewBox="0 0 720 240" role="img" aria-label={`Interaction of ${xAxis} and ${yAxis}`}>
      <ScatterGrid />
      {points.map((trial, index) => <circle key={`${trial.number ?? index}`} className="trial-dot"
        cx={parameterX(trial.parameters[xAxis], xScale)} cy={parameterY(trial.parameters[yAxis], yScale)} r="5"
        fill={scoreColor(trial.score, min, max)}><title>{xAxis}: {displayValue(trial.parameters[xAxis])}; {yAxis}: {displayValue(trial.parameters[yAxis])}; score: {formatNumber(trial.score)}</title></circle>)}
      <text className="chart-axis-label" x="360" y="232">{xAxis}{xScale.log ? " (log scale)" : ""}</text>
      <text className="chart-axis-label" x="12" y="26">{yAxis}{yScale.log ? " (log scale)" : ""}</text>
    </svg>}
  </section>;
}

type ParameterScale = { numeric: boolean; log: boolean; minimum: number; maximum: number; categories: string[] };

function parameterScale(trials: ScoredTrial[], parameter: string): ParameterScale {
  const values = trials.map((trial) => trial.parameters[parameter]);
  const numbers = values.map(Number);
  const numeric = numbers.every(Number.isFinite);
  if (!numeric) return { numeric: false, log: false, minimum: 0, maximum: 1, categories: sortHeatmapValues([...new Set(values.map(heatmapValue))]) };
  const minimum = Math.min(...numbers);
  const maximum = Math.max(...numbers);
  return { numeric: true, log: minimum > 0 && maximum / minimum >= 50, minimum, maximum, categories: [] };
}

function parameterPosition(value: unknown, scale: ParameterScale) {
  if (!scale.numeric) return scale.categories.length <= 1 ? 0.5 : scale.categories.indexOf(heatmapValue(value)) / (scale.categories.length - 1);
  const numeric = Number(value);
  if (scale.maximum === scale.minimum) return 0.5;
  if (scale.log) return (Math.log(numeric) - Math.log(scale.minimum)) / (Math.log(scale.maximum) - Math.log(scale.minimum));
  return (numeric - scale.minimum) / (scale.maximum - scale.minimum);
}

function parameterX(value: unknown, scale: ParameterScale) { return 52 + parameterPosition(value, scale) * 640; }
function parameterY(value: unknown, scale: ParameterScale) { return 202 - parameterPosition(value, scale) * 168; }
function chartX(index: number, count: number) { return count <= 1 ? 372 : 52 + (index / (count - 1)) * 640; }
function chartY(value: number, minimum: number, maximum: number) { return maximum === minimum ? 118 : 202 - ((value - minimum) / (maximum - minimum)) * 168; }
function scoreColor(score: number, minimum: number, maximum: number) { return heatmapColor(score, minimum, maximum); }

function parameterSignal(trials: ScoredTrial[], parameter: string) {
  const scale = parameterScale(trials.filter((trial) => parameter in trial.parameters), parameter);
  const groups = new Map<string, number[]>();
  for (const trial of trials) {
    if (!(parameter in trial.parameters)) continue;
    const position = parameterPosition(trial.parameters[parameter], scale);
    const group = scale.numeric ? `bin-${Math.min(3, Math.floor(position * 4))}` : heatmapValue(trial.parameters[parameter]);
    groups.set(group, [...(groups.get(group) ?? []), trial.score]);
  }
  const means = [...groups.values()].filter((items) => items.length > 0).map((items) => items.reduce((sum, item) => sum + item, 0) / items.length);
  return means.length > 1 ? Math.max(...means) - Math.min(...means) : 0;
}

function ChartGrid({ min, max }: { min: number; max: number }) {
  return <>
    {[34, 76, 118, 160, 202].map((y) => <line key={y} className="chart-grid-line" x1="52" x2="692" y1={y} y2={y} />)}
    <text className="chart-value-label" x="18" y="38">{formatNumber(max)}</text>
    <text className="chart-value-label" x="18" y="206">{formatNumber(min)}</text>
  </>;
}

function ScatterGrid() {
  return <>{[52, 212, 372, 532, 692].map((x) => <line key={`x-${x}`} className="chart-grid-line" x1={x} x2={x} y1="34" y2="202" />)}
    {[34, 76, 118, 160, 202].map((y) => <line key={`y-${y}`} className="chart-grid-line" x1="52" x2="692" y1={y} y2={y} />)}</>;
}

function SearchHeatmap({
  trials,
  dimensions,
  xAxis,
  yAxis,
  onXAxisChange,
  onYAxisChange
}: {
  trials: OptimizationTrial[];
  dimensions: string[];
  xAxis: string;
  yAxis: string;
  onXAxisChange: (value: string) => void;
  onYAxisChange: (value: string) => void;
}) {
  const heatmap = useMemo(() => buildHeatmap(trials, xAxis, yAxis), [trials, xAxis, yAxis]);
  if (dimensions.length < 2) {
    return <div className="empty-state">At least two varied parameters are needed for a heatmap.</div>;
  }
  const scores = heatmap.cells.map((cell) => cell.score).filter((value): value is number => typeof value === "number");
  if (!scores.length) {
    return <div className="empty-state">No successful trials are available for this heatmap.</div>;
  }
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  return <div className="search-heatmap-panel">
    <div className="search-heatmap-controls">
      <label>X axis<select value={xAxis} onChange={(event) => onXAxisChange(event.target.value)}>
        {dimensions.map((dimension) => <option key={dimension} value={dimension}>{dimension}</option>)}
      </select></label>
      <label>Y axis<select value={yAxis} onChange={(event) => onYAxisChange(event.target.value)}>
        {dimensions.map((dimension) => <option key={dimension} value={dimension}>{dimension}</option>)}
      </select></label>
    </div>
    {xAxis === yAxis
      ? <div className="empty-state">Choose two different parameters.</div>
      : <div className="search-heatmap-scroll">
        <div className="search-heatmap-grid" style={{
          gridTemplateColumns: `minmax(88px, auto) repeat(${heatmap.xValues.length}, minmax(72px, 1fr))`
        }}>
          <span className="search-heatmap-corner">{yAxis} / {xAxis}</span>
          {heatmap.xValues.map((xValue) => <strong key={xValue}>{xValue}</strong>)}
          {heatmap.yValues.map((yValue) => (
            <div className="search-heatmap-row" style={{ display: "contents" }} key={yValue}>
              <strong>{yValue}</strong>
              {heatmap.xValues.map((xValue) => {
                const cell = heatmap.byKey.get(`${xValue}\u0000${yValue}`);
                return <span
                  key={`${xValue}-${yValue}`}
                  className="search-heatmap-cell"
                  style={{ background: heatmapColor(cell?.score, min, max) }}
                  title={cell ? `${formatNumber(cell.score)} across ${cell.count} trial(s)` : "No evaluated trial"}
                >
                  {cell ? formatNumber(cell.score) : "-"}
                </span>;
              })}
            </div>
          ))}
        </div>
      </div>}
    {xAxis !== yAxis && <div className="search-heatmap-legend">
      <span>{formatNumber(min)}</span>
      <i aria-hidden="true" />
      <span>{formatNumber(max)}</span>
    </div>}
  </div>;
}

function heatmapParameterOptions(trials: OptimizationTrial[]) {
  const valuesByKey = new Map<string, Set<string>>();
  for (const trial of trials) {
    if (trial.status !== "succeeded" || typeof trial.score !== "number" || !trial.parameters) continue;
    for (const [key, value] of Object.entries(trial.parameters)) {
      const values = valuesByKey.get(key) ?? new Set<string>();
      values.add(heatmapValue(value));
      valuesByKey.set(key, values);
    }
  }
  return [...valuesByKey.entries()]
    .filter(([, values]) => values.size > 1)
    .map(([key]) => key);
}

function buildHeatmap(trials: OptimizationTrial[], xAxis: string, yAxis: string) {
  const aggregate = new Map<string, { x: string; y: string; total: number; count: number }>();
  const xValues = new Set<string>();
  const yValues = new Set<string>();
  for (const trial of trials) {
    if (trial.status !== "succeeded" || typeof trial.score !== "number" || !trial.parameters) continue;
    if (!(xAxis in trial.parameters) || !(yAxis in trial.parameters)) continue;
    const x = heatmapValue(trial.parameters[xAxis]);
    const y = heatmapValue(trial.parameters[yAxis]);
    xValues.add(x);
    yValues.add(y);
    const key = `${x}\u0000${y}`;
    const current = aggregate.get(key) ?? { x, y, total: 0, count: 0 };
    current.total += trial.score;
    current.count += 1;
    aggregate.set(key, current);
  }
  const byKey = new Map<string, { score: number; count: number }>();
  for (const [key, value] of aggregate.entries()) {
    byKey.set(key, { score: value.total / value.count, count: value.count });
  }
  return {
    xValues: sortHeatmapValues([...xValues]),
    yValues: sortHeatmapValues([...yValues]),
    cells: [...byKey.values()],
    byKey
  };
}

function heatmapValue(value: unknown) {
  return value == null ? "None" : displayValue(value);
}

function sortHeatmapValues(values: string[]) {
  return values.sort((left, right) => {
    const leftNumber = Number(left);
    const rightNumber = Number(right);
    if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) return leftNumber - rightNumber;
    return left.localeCompare(right, undefined, { numeric: true });
  });
}

function heatmapColor(score: number | undefined, min: number, max: number) {
  if (score === undefined || !Number.isFinite(score)) return "#f1f5f7";
  const ratio = max === min ? 0.72 : (score - min) / (max - min);
  const hue = 195 - ratio * 155;
  const lightness = 92 - ratio * 42;
  return `hsl(${hue}, 72%, ${lightness}%)`;
}

function SearchSpaceList({ searchSpace }: { searchSpace: Record<string, unknown> | undefined }) {
  if (!searchSpace || !Object.keys(searchSpace).length) {
    return <div className="empty-state">Search space was not recorded.</div>;
  }
  return <div className="parameter-chip-list">
    {Object.entries(searchSpace).map(([key, value]) => (
      <span key={key}><strong>{key}</strong>{displaySearchSpaceValue(value)}</span>
    ))}
  </div>;
}

function ParameterList({ parameters, empty }: { parameters: Record<string, unknown>; empty: string }) {
  const entries = Object.entries(parameters).filter(([, value]) => value !== undefined);
  if (!entries.length) return <div className="empty-state">{empty}</div>;
  return <div className="parameter-chip-list">
    {entries.map(([key, value]) => (
      <span key={key}><strong>{key}</strong>{displayValue(value)}</span>
    ))}
  </div>;
}

function KeyValueGrid({ values, empty }: { values: Record<string, unknown>; empty: string }) {
  const entries = Object.entries(values).filter(([, value]) => value !== "" && value !== undefined);
  if (!entries.length) return <div className="empty-state">{empty}</div>;
  return (
    <div className="model-key-value-grid">
      {entries.map(([key, value]) => (
        <div key={key}><span>{key.replaceAll("_", " ")}</span><code>{displayValue(value)}</code></div>
      ))}
    </div>
  );
}

function displayValue(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function compactParameters(parameters: Record<string, unknown> | undefined) {
  if (!parameters || !Object.keys(parameters).length) return "—";
  return Object.entries(parameters)
    .map(([key, value]) => `${key}=${displayValue(value)}`)
    .join(" · ");
}

function displaySearchSpaceValue(value: unknown) {
  if (Array.isArray(value)) return value.map(displayValue).join(" · ");
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (Array.isArray(record.values)) return record.values.map(displayValue).join(" · ");
    if (record.low !== undefined || record.high !== undefined) {
      return `${displayValue(record.low)} → ${displayValue(record.high)}${record.points ? ` · ${record.points} values` : ""}${record.log ? " · log" : ""}`;
    }
  }
  return displayValue(value);
}

function displayMode(value: string | undefined) {
  return value ? value.replaceAll("_", " ") : "not recorded";
}

function formatMaybeNumber(value: unknown) {
  return typeof value === "number" ? formatNumber(value) : "—";
}

function candidateProgress(optimization: OptimizationSummary) {
  const evaluated = optimization.trial_count ?? 0;
  const total = optimization.total_candidate_count;
  if (typeof total === "number" && total > 0) {
    return `${evaluated} / ${total}`;
  }
  const planned = optimization.planned_trial_count;
  return typeof planned === "number" && planned > 0
    ? `${evaluated} / ${planned}`
    : String(evaluated);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 }).format(value);
}

function formatDate(value: string) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function shortId(value: string) {
  return value ? value.slice(0, 8) : "unknown";
}

export function ServingPanel({
  deployments,
  models,
  onRefresh,
  setNotice
}: {
  deployments: Deployment[];
  models: ModelArtifact[];
  onRefresh: () => Promise<void>;
  setNotice: NoticeSetter;
}) {
  const [modelId, setModelId] = useState("");
  const [deploymentId, setDeploymentId] = useState("");
  const [scoreResult, setScoreResult] = useState<ScoreResponse | null>(null);

  async function createDeployment() {
    const selectedModel = modelId || models[0]?.id || "demo-model";
    await api.createDeployment({
      model_id: selectedModel,
      name: "online-scorer"
    });
    setNotice("Deployment requested");
    await onRefresh();
  }

  async function score() {
    const selectedDeployment = deploymentId || deployments[0]?.id;
    if (!selectedDeployment) {
      setNotice("Create a deployment first");
      return;
    }
    const result = await api.score(selectedDeployment, [{ age: 39, income: 65000 }]);
    setScoreResult(result);
    setNotice("Online scoring completed");
  }

  return (
    <section className="two-column">
      <div className="panel form-panel">
        <div className="panel-header">
          <h2>Deploy and score</h2>
          <Rocket size={18} />
        </div>
        <label>
          Model
          <select value={modelId} onChange={(event) => setModelId(event.target.value)}>
            <option value="">Demo model</option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Deployment
          <select value={deploymentId} onChange={(event) => setDeploymentId(event.target.value)}>
            <option value="">First available</option>
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deployment.name}
              </option>
            ))}
          </select>
        </label>
        <div className="button-row">
          <button className="secondary-button" onClick={createDeployment} type="button">
            <Plus size={16} />
            Deploy
          </button>
          <button className="primary-button" onClick={score} type="button">
            <Play size={16} />
            Score
          </button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Scoring output</h2>
        </div>
        <pre className="json-output">{JSON.stringify(scoreResult ?? { status: "waiting" }, null, 2)}</pre>
      </div>
    </section>
  );
}

export function SharePanel({
  datasets,
  models,
  deployments,
  setNotice
}: {
  datasets: DataAsset[];
  models: ModelArtifact[];
  deployments: Deployment[];
  setNotice: NoticeSetter;
}) {
  const [targetUser, setTargetUser] = useState("analyst@example.com");

  async function shareResource() {
    const dataset = datasets[0];
    await api.share({
      target_user_id: targetUser,
      resource_kind: "dataset",
      resource_id: dataset?.id ?? "demo-dataset",
      permission: "read"
    });
    setNotice("Share grant created");
  }

  async function exportResource() {
    const model = models[0];
    await api.exportResource({
      resource_kind: model ? "model" : "dataset",
      resource_id: model?.id ?? datasets[0]?.id ?? "demo-resource",
      format: model ? "pickle" : "csv"
    });
    setNotice("Export job queued");
  }

  return (
    <section className="two-column">
      <div className="panel form-panel">
        <div className="panel-header">
          <h2>Collaboration</h2>
          <Share2 size={18} />
        </div>
        <label>
          User
          <input value={targetUser} onChange={(event) => setTargetUser(event.target.value)} />
        </label>
        <div className="button-row">
          <button className="secondary-button" onClick={shareResource} type="button">
            <Share2 size={16} />
            Share
          </button>
          <button className="primary-button" onClick={exportResource} type="button">
            <Download size={16} />
            Export
          </button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Available resources</h2>
        </div>
        <div className="resource-strip">
          <span>{datasets.length} datasets</span>
          <span>{models.length} models</span>
          <span>{deployments.length} deployments</span>
        </div>
      </div>
    </section>
  );
}
