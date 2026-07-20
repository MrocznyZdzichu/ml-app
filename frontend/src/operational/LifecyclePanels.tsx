import { Activity, ArrowLeft, Brain, Copy, Eye, GitBranch, History, KeyRound, Play, Plus, Rocket, Search, Settings2, ShieldCheck, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  DataAsset,
  DatasetLineageReference,
  BusinessCase,
  ChallengerReplay,
  Deployment,
  DeploymentRevision,
  DeploymentRole,
  InferenceRequest,
  ModelArtifact,
  ModelServingUsage,
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
  onOpenDataset,
  onRefresh,
  setNotice
}: {
  models: ModelArtifact[];
  businessCases: BusinessCase[];
  pipelines: Pipeline[];
  initialBusinessCaseId?: string;
  onOpenDataset?: (datasetId: string) => void;
  onRefresh: () => Promise<void>;
  setNotice: NoticeSetter;
}) {
  const [query, setQuery] = useState("");
  const [businessCaseId, setBusinessCaseId] = useState(initialBusinessCaseId);
  const [stageFilter, setStageFilter] = useState("");
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
      && (!stageFilter || latest.stage === stageFilter)
      && pipelineMatches(latest.pipeline_id, pipelines, purposeFilter, pipelineFilter)
      && (!normalized || [
        latest.name,
        latest.algorithm,
        latest.problem_type,
        ...versions.map((version) => version.version)
      ].some((value) => value.toLowerCase().includes(normalized)))
    );
  }, [businessCaseId, modelFamilies, pipelineFilter, pipelines, purposeFilter, query, stageFilter]);
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
          <label>
            <span><SlidersHorizontal size={14} /> Status</span>
            <select aria-label="Model status" value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}>
              <option value="">All statuses</option>
              <option value="developed">Developed</option>
              <option value="staging">Staging</option>
              <option value="production">Production</option>
              <option value="archived">Archived</option>
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
            <div className="catalog-empty">No models match the selected filters.</div>
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
          onStageChanged={async (updated) => {
            setSelectedModel(updated);
            await onRefresh();
            setNotice(`Model ${updated.version} stage changed to ${updated.stage}`);
          }}
        />
      )}
      {historyModel && (
        <ModelVersionHistoryDialog
          model={historyModel}
          businessCaseName={businessCaseById.get(historyModel.business_case_id)?.name ?? "Unassigned"}
          pipelineName={pipelineById.get(historyModel.pipeline_id)?.name ?? "Unknown pipeline"}
          onClose={() => setHistoryModel(null)}
          onView={async (version) => {
            const fullModel = await api.getModel(version.id);
            setHistoryModel(null);
            setSelectedModel(fullModel);
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
  onView: (model: ModelArtifact) => Promise<void> | void;
}) {
  const [versions, setVersions] = useState<ModelArtifact[]>([]);
  const [servingUsage, setServingUsage] = useState<ModelServingUsage[]>([]);
  const [error, setError] = useState("");
  const [openingModelId, setOpeningModelId] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      api.listModelVersions(model.logical_id),
      api.listModelServingUsage(model.logical_id)
    ])
      .then(([items, usage]) => { if (active) {
        setVersions([...items].sort((left, right) => right.version_number - left.version_number));
        setServingUsage(usage);
      } })
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
          {versions.map((version, index) => {
            const usages = servingUsage.filter((item) => item.model_id === version.id);
            return <article key={version.id} className={usages.length ? "model-version-in-use" : ""}>
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
                {usages.length > 0 ? (
                  <div className="model-serving-usage">
                    <b><Rocket size={13} /> In production use · {usages.length} {usages.length === 1 ? "service" : "services"}</b>
                    {usages.map((usage) => (
                      <span key={`${usage.deployment_id}-${usage.role}`}>
                        {usage.deployment_name} · {usage.role} · revision v{usage.revision_version} · {usage.deployment_status}
                      </span>
                    ))}
                  </div>
                ) : <span className="model-version-unused">Not assigned to an active service</span>}
              </div>
              <button className="secondary-button compact-button" type="button" disabled={openingModelId === version.id} onClick={async () => {
                setOpeningModelId(version.id);
                try {
                  await onView(version);
                } finally {
                  setOpeningModelId("");
                }
              }}>
                <Eye size={14} /> {openingModelId === version.id ? "Opening…" : "View"}
              </button>
            </article>;
          })}
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
  onOpenDataset,
  onStageChanged
}: {
  model: ModelArtifact;
  businessCaseName: string;
  pipelineName: string;
  onClose: () => void;
  onOpenDataset?: (datasetId: string) => void;
  onStageChanged?: (model: ModelArtifact) => Promise<void> | void;
}) {
  const [tab, setTab] = useState<"overview" | "training" | "search" | "parameters" | "lineage">("overview");
  const [nextStage, setNextStage] = useState<"developed" | "staging" | "production" | "archived">(model.stage as "developed" | "staging" | "production" | "archived");
  const [stageBusy, setStageBusy] = useState(false);
  const [dataLineage, setDataLineage] = useState<DatasetLineageReference[]>([]);
  const [lineageError, setLineageError] = useState("");
  const weights = model.model_parameters.weights ?? [];
  const optimization = optimizationSummary(model.metrics);
  useEffect(() => setNextStage(model.stage as "developed" | "staging" | "production" | "archived"), [model.id, model.stage]);
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
            <section className="model-detail-section model-stage-control">
              <div>
                <h3>Lifecycle stage</h3>
                <p>Stage describes model readiness. Service roles such as champion or challenger are configured separately in Serving.</p>
              </div>
              <div className="model-stage-actions">
                <select aria-label="Model lifecycle stage" value={nextStage} onChange={(event) => setNextStage(event.target.value as typeof nextStage)}>
                  <option value="developed">Developed</option>
                  <option value="staging">Staging</option>
                  <option value="production">Production</option>
                  <option value="archived">Archived</option>
                </select>
                <button className="secondary-button" type="button" disabled={stageBusy || nextStage === model.stage} onClick={async () => {
                  setStageBusy(true);
                  try {
                    const updated = await api.promoteModel(model.id, nextStage);
                    await onStageChanged?.(updated);
                  } finally {
                    setStageBusy(false);
                  }
                }}>Update stage</button>
              </div>
            </section>
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
  initialDeploymentId = "",
  onRefresh,
  setNotice
}: {
  deployments: Deployment[];
  models: ModelArtifact[];
  initialDeploymentId?: string;
  onRefresh: () => Promise<void>;
  setNotice: NoticeSetter;
}) {
  type ServingTab = "overview" | "test" | "traffic" | "access";
  type ServingModal = "create" | "revision" | "history" | "lifecycle" | "credential" | "replay" | "inference" | null;
  const [serviceName, setServiceName] = useState("");
  const [modelId, setModelId] = useState("");
  const [deploymentId, setDeploymentId] = useState("");
  const [activeTab, setActiveTab] = useState<ServingTab>("overview");
  const [modal, setModal] = useState<ServingModal>(null);
  const [recordId, setRecordId] = useState("");
  const [featuresJson, setFeaturesJson] = useState("{\n  \"area\": 84,\n  \"rooms\": 4\n}");
  const [scoreTarget, setScoreTarget] = useState("champion");
  const [scoreResult, setScoreResult] = useState<ScoreResponse | null>(null);
  const [history, setHistory] = useState<InferenceRequest[]>([]);
  const [inferenceDetail, setInferenceDetail] = useState<Record<string, unknown> | null>(null);
  const [replays, setReplays] = useState<ChallengerReplay[]>([]);
  const [revisions, setRevisions] = useState<DeploymentRevision[]>([]);
  const [historyError, setHistoryError] = useState("");
  const [roleByModel, setRoleByModel] = useState<Record<string, DeploymentRole | "">>({});
  const [revisionReason, setRevisionReason] = useState("");
  const [lifecycleReason, setLifecycleReason] = useState("");
  const [rollbackRevisionId, setRollbackRevisionId] = useState("");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedDeployment = deployments.find((item) => item.id === deploymentId);
  const eligibleModels = models.filter((item) => item.business_case_id === selectedDeployment?.business_case_id);
  const productionModels = models.filter((item) => item.stage === "production" && item.business_case_id);

  useEffect(() => {
    if (initialDeploymentId && deployments.some((item) => item.id === initialDeploymentId)) {
      setDeploymentId(initialDeploymentId);
      setActiveTab("overview");
    }
  }, [deployments, initialDeploymentId]);

  useEffect(() => {
    const assignments = selectedDeployment?.active_revision?.assignments ?? [];
    setRoleByModel(Object.fromEntries(assignments.map((item) => [item.model_id, item.role])));
    setScoreTarget("champion");
    if (!selectedDeployment) {
      setHistory([]);
      return;
    }
    let active = true;
    setHistoryError("");
    Promise.all([
      api.inferenceLog(selectedDeployment.id, 50),
      api.listChallengerReplays(selectedDeployment.id),
      api.listDeploymentRevisions(selectedDeployment.id)
    ])
      .then(([page, replayItems, revisionItems]) => { if (active) {
        setHistory(page.items);
        setReplays(replayItems);
        setRevisions(revisionItems);
      } })
      .catch((error) => active && setHistoryError(error instanceof Error ? error.message : "Could not load inference history"));
    return () => { active = false; };
  }, [selectedDeployment?.id, selectedDeployment?.active_revision_id]);

  async function createDeployment() {
    if (!serviceName.trim() || !modelId) {
      setNotice("Choose a production model and enter a service name");
      return;
    }
    setBusy(true);
    try {
      const created = await api.createDeployment({ model_id: modelId, name: serviceName.trim(), retention_days: 365 });
      setDeploymentId(created.id);
      setActiveTab("overview");
      setModal(null);
      setServiceName("");
      setNotice("Model service created with revision v1");
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function score() {
    if (!selectedDeployment) {
      setNotice("Create a deployment first");
      return;
    }
    let features: Record<string, unknown>;
    try {
      features = JSON.parse(featuresJson) as Record<string, unknown>;
    } catch {
      setNotice("Features must be a valid JSON object");
      return;
    }
    setBusy(true);
    try {
      const challenger = scoreTarget === "champion" ? undefined : scoreTarget;
      const result = await api.score(selectedDeployment.id, [{ record_id: recordId || undefined, features }], challenger);
      setScoreResult(result);
      const page = await api.inferenceLog(selectedDeployment.id, 50);
      setHistory(page.items);
      setNotice(`Scored with ${result.served_role} model ${shortId(result.model_id)}`);
    } finally {
      setBusy(false);
    }
  }

  async function activateRevision() {
    if (!selectedDeployment) return;
    const assignments = Object.entries(roleByModel)
      .filter((entry): entry is [string, DeploymentRole] => Boolean(entry[1]))
      .map(([assignedModelId, role]) => ({ model_id: assignedModelId, role }));
    if (assignments.filter((item) => item.role === "champion").length !== 1) {
      setNotice("Choose exactly one champion");
      return;
    }
    if (assignments.filter((item) => item.role === "fallback").length > 1) {
      setNotice("Choose at most one fallback");
      return;
    }
    setBusy(true);
    try {
      await api.createDeploymentRevision(selectedDeployment.id, assignments, revisionReason);
      setRevisionReason("");
      setModal(null);
      setNotice("New immutable service revision activated");
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function changeDeploymentStatus() {
    if (!selectedDeployment || !lifecycleReason.trim()) return;
    const nextStatus = selectedDeployment.status === "running" ? "stopped" : "running";
    setBusy(true);
    try {
      await api.setDeploymentStatus(selectedDeployment.id, nextStatus, lifecycleReason.trim());
      setLifecycleReason("");
      setModal(null);
      setNotice(`Model service ${nextStatus === "running" ? "started" : "stopped"}`);
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function rollbackDeployment() {
    if (!selectedDeployment || !rollbackRevisionId || !revisionReason.trim()) return;
    setBusy(true);
    try {
      await api.rollbackDeployment(selectedDeployment.id, rollbackRevisionId, revisionReason.trim());
      setRevisionReason("");
      setRollbackRevisionId("");
      setModal(null);
      setNotice("Rollback activated as a new immutable service revision");
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function createCredential() {
    setBusy(true);
    try {
      const created = await api.createApiCredential(`${selectedDeployment?.slug ?? "serving"}-client`, null);
      setCredential(String(created.token ?? ""));
      setNotice("Credential created; copy it now because it will not be shown again");
    } finally {
      setBusy(false);
    }
  }

  async function replayChallenger() {
    if (!selectedDeployment || scoreTarget === "champion") {
      setNotice("Select a challenger as the test target first");
      return;
    }
    const job = await api.createChallengerReplay(selectedDeployment.id, scoreTarget, 1000);
    setReplays((current) => [job, ...current]);
    setModal(null);
    setNotice("Challenger replay queued over up to 1,000 historical requests");
  }

  function openDeployment(deployment: Deployment) {
    setDeploymentId(deployment.id);
    setActiveTab("overview");
    setScoreResult(null);
    setInferenceDetail(null);
  }

  const assignments = selectedDeployment?.active_revision?.assignments ?? [];
  const champion = assignments.find((item) => item.role === "champion");
  const challengers = assignments.filter((item) => item.role === "challenger");
  const shadows = assignments.filter((item) => item.role === "shadow");
  const fallback = assignments.find((item) => item.role === "fallback");

  function modelLabel(assignedModelId: string | undefined) {
    if (!assignedModelId) return "Not configured";
    const model = models.find((item) => item.id === assignedModelId);
    return model ? `${model.name} · ${model.version}` : shortId(assignedModelId);
  }

  function closeModal() {
    setModal(null);
    if (modal === "inference") setInferenceDetail(null);
  }

  if (!selectedDeployment) {
    return (
      <section className="serving-catalog">
        <div className="serving-page-header">
          <div>
            <span className="builder-kicker">Online inference</span>
            <h2>Model services</h2>
            <p>Publish stable prediction endpoints and manage the models behind them.</p>
          </div>
          <button className="primary-button" type="button" onClick={() => setModal("create")}>
            <Plus size={16} /> New service
          </button>
        </div>

        <div className="serving-guidance" role="note">
          <Rocket size={20} />
          <div><strong>Start with a production model.</strong><span>Create one service, then add challengers, shadows or a fallback from its Overview.</span></div>
        </div>

        <div className="serving-service-grid">
          {deployments.map((deployment) => {
            const activeAssignments = deployment.active_revision?.assignments ?? [];
            const activeChampion = activeAssignments.find((item) => item.role === "champion");
            return <button className="serving-service-card" type="button" key={deployment.id} onClick={() => openDeployment(deployment)}>
              <span className="serving-card-top"><span className={`status-pill ${deployment.status}`}>{deployment.status}</span><span>Revision v{deployment.active_revision?.version_number ?? "—"}</span></span>
              <strong>{deployment.name}</strong>
              <code>{deployment.slug}</code>
              <span className="serving-card-model"><Rocket size={15} /><span><small>Champion</small>{modelLabel(activeChampion?.model_id)}</span></span>
              <span className="serving-card-footer"><span>{activeAssignments.filter((item) => item.role === "challenger").length} challengers</span><span>{activeAssignments.filter((item) => item.role === "shadow").length} shadows</span><span>Open service →</span></span>
            </button>;
          })}
          {!deployments.length && <div className="panel serving-empty-state">
            <Rocket size={28} />
            <h3>No model services yet</h3>
            <p>Create a stable endpoint backed by your first production model.</p>
            <button className="primary-button" type="button" onClick={() => setModal("create")}><Plus size={16} /> Create first service</button>
          </div>}
        </div>

        {modal === "create" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}>
          <div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="create-serving-title">
            <div className="modal-header"><div><span className="builder-kicker">New endpoint</span><h2 id="create-serving-title">Create model service</h2><p>The service name and endpoint stay stable when you change model versions later.</p></div><button className="icon-button" type="button" onClick={closeModal} aria-label="Close"><X size={18} /></button></div>
            <div className="serving-modal-body form-panel">
              <label>Service name<input autoFocus value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder="Estates Sell Prices Service" /></label>
              <label>Initial champion<select value={modelId} onChange={(event) => setModelId(event.target.value)}><option value="">Choose a production model</option>{productionModels.map((model) => <option key={model.id} value={model.id}>{model.name} · {model.version}</option>)}</select><small>Only production models can receive public traffic as champion.</small></label>
              {!productionModels.length && <div className="serving-inline-warning">No production models are available. Promote a validated model from the Models section first.</div>}
            </div>
            <div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" onClick={createDeployment} type="button" disabled={busy || !serviceName.trim() || !modelId}><Plus size={16} /> Create service</button></div>
          </div>
        </div>}
      </section>
    );
  }

  return (
    <section className="serving-detail-screen">
      <button className="serving-back-button" type="button" onClick={() => setDeploymentId("")}><ArrowLeft size={16} /> All model services</button>
      <div className="serving-detail-header">
        <div><span className="builder-kicker">Online inference service</span><h2>{selectedDeployment.name}</h2><div className="serving-title-meta"><span className={`status-pill ${selectedDeployment.status}`}>{selectedDeployment.status}</span><span>Revision v{selectedDeployment.active_revision?.version_number ?? "—"}</span><span>Retention {selectedDeployment.retention_days} days</span></div></div>
        <div className="model-row-actions">
          <button className="secondary-button" type="button" onClick={() => setModal("history")}><History size={16} /> Revision history</button>
          <button className="secondary-button" type="button" onClick={() => setModal("lifecycle")}>
            {selectedDeployment.status === "running" ? <X size={16} /> : <Play size={16} />}
            {selectedDeployment.status === "running" ? "Stop service" : selectedDeployment.status === "stopped" ? "Start service" : "Validate & resume"}
          </button>
          <button className="secondary-button" type="button" onClick={() => setModal("revision")}><GitBranch size={16} /> Configure models</button>
        </div>
      </div>
      <div className="serving-endpoint-bar"><div><small>Stable production endpoint</small><code>{selectedDeployment.endpoint_url}</code></div><button className="icon-button" type="button" aria-label="Copy endpoint" title="Copy endpoint" onClick={() => navigator.clipboard.writeText(selectedDeployment.endpoint_url ?? "")}><Copy size={16} /></button></div>

      <nav className="serving-tabs" aria-label="Model service sections">
        {([
          ["overview", "Overview", Rocket], ["test", "Test endpoint", Play], ["traffic", "Traffic & audit", Activity], ["access", "API access", KeyRound]
        ] as const).map(([tab, label, Icon]) => <button key={tab} className={activeTab === tab ? "active" : ""} type="button" onClick={() => setActiveTab(tab)}><Icon size={16} />{label}{tab === "traffic" && history.length > 0 && <span>{history.length}</span>}</button>)}
      </nav>

      {activeTab === "overview" && <div className="serving-tab-content">
        <div className="serving-summary-grid">
          <article className="panel serving-role-card primary"><span><Rocket size={18} />Champion</span><strong>{modelLabel(champion?.model_id)}</strong><small>Receives all requests sent to the stable endpoint.</small></article>
          <article className="panel serving-role-card"><span><GitBranch size={18} />Challengers</span><strong>{challengers.length}</strong><small>{challengers.length ? challengers.map((item) => modelLabel(item.model_id)).join(", ") : "None configured"}</small></article>
          <article className="panel serving-role-card"><span><Activity size={18} />Shadows</span><strong>{shadows.length}</strong><small>{shadows.length ? shadows.map((item) => modelLabel(item.model_id)).join(", ") : "None configured"}</small></article>
          <article className="panel serving-role-card"><span><ShieldCheck size={18} />Fallback</span><strong>{fallback ? "Ready" : "Not set"}</strong><small>{modelLabel(fallback?.model_id)}</small></article>
        </div>
        <div className="panel serving-next-steps"><div className="panel-header"><div><span className="builder-kicker">Recommended workflow</span><h3>What would you like to do?</h3></div></div><div className="serving-action-grid">
          <button type="button" onClick={() => setActiveTab("test")}><Play size={18} /><span><strong>Test the endpoint</strong><small>Send one example and inspect the response.</small></span></button>
          <button type="button" onClick={() => setModal("revision")}><Settings2 size={18} /><span><strong>Change model roles</strong><small>Add a challenger, shadow or fallback in a new revision.</small></span></button>
          <button type="button" onClick={() => setActiveTab("traffic")}><History size={18} /><span><strong>Review traffic</strong><small>Inspect auditable requests and model executions.</small></span></button>
        </div></div>
      </div>}

      {activeTab === "test" && <div className="serving-tab-content serving-test-layout">
        <div className="panel form-panel"><div className="panel-header"><div><span className="builder-kicker">Single request</span><h3>Test endpoint</h3></div><Play size={18} /></div><p className="serving-section-intro">Use the champion endpoint or call a challenger directly without changing production traffic.</p>
          <label>Target<select value={scoreTarget} onChange={(event) => setScoreTarget(event.target.value)}><option value="champion">Champion · public endpoint</option>{challengers.map((item) => <option key={item.model_id} value={item.model_id}>Challenger · {modelLabel(item.model_id)}</option>)}</select></label>
          <label>Record ID <span className="optional-label">recommended</span><input value={recordId} onChange={(event) => setRecordId(event.target.value)} placeholder="e.g. property-1042" /><small>Needed later to join predictions with actual outcomes.</small></label>
          <label>Features JSON<textarea className="json-input" value={featuresJson} onChange={(event) => setFeaturesJson(event.target.value)} rows={10} /></label>
          <div className="button-row"><button className="primary-button" onClick={score} type="button" disabled={busy}><Play size={16} /> Send test request</button>{scoreTarget !== "champion" && <button className="secondary-button" onClick={() => setModal("replay")} type="button"><History size={16} /> Replay history</button>}</div>
        </div>
        <div className="panel serving-response-panel"><div className="panel-header"><div><span className="builder-kicker">Response</span><h3>{scoreResult ? "Prediction returned" : "Waiting for a request"}</h3></div>{scoreResult && <span className="status-pill active">{scoreResult.served_role}</span>}</div>{scoreResult ? <pre className="json-output">{JSON.stringify(scoreResult, null, 2)}</pre> : <div className="serving-response-empty"><Play size={26} /><p>Your prediction, request ID and warnings will appear here.</p></div>}</div>
      </div>}

      {activeTab === "traffic" && <div className="serving-tab-content">
        <div className="serving-section-header"><div><span className="builder-kicker">Full payload retention</span><h3>Inference log</h3><p>Every accepted request and model execution is retained for audit and future monitoring.</p></div>{challengers.length > 0 && <button className="secondary-button" type="button" onClick={() => { setScoreTarget(challengers[0].model_id); setModal("replay"); }}><History size={16} /> Replay challenger</button>}</div>
        {historyError && <div className="error-banner">{historyError}</div>}
        <div className="panel inference-log-list serving-traffic-list">{history.map((item) => <article key={item.id}><span><strong>{item.status}</strong><small>{formatDate(item.created_at)} · {item.record_count} records</small></span><span><code>{shortId(item.served_model_id || item.champion_model_id)}</code><small>{item.served_role || "champion"}{item.fallback_used ? " · fallback used" : ""}</small></span><span><strong>{item.latency_ms ?? "—"} ms</strong><small>{item.warnings[0] ?? item.error_message}</small></span><button className="secondary-button compact-button" type="button" onClick={() => api.inferenceDetail(selectedDeployment.id, item.id).then((detail) => { setInferenceDetail(detail); setModal("inference"); })}><Eye size={14} /> Details</button></article>)}{!history.length && !historyError && <div className="serving-list-empty"><History size={24} /><strong>No requests recorded yet</strong><span>Use Test endpoint or call the REST API to generate the first auditable request.</span></div>}</div>
        {replays.length > 0 && <div className="serving-replay-section"><h3>Challenger replays</h3><div className="panel inference-log-list">{replays.slice(0, 10).map((item) => <article key={item.id}><span><strong>{item.status}</strong><small>{formatDate(item.created_at)}</small></span><span><code>{shortId(item.challenger_model_id)}</code><small>revision {shortId(item.deployment_revision_id)}</small></span><span><strong>{item.processed_records} records</strong><small>{item.failed_requests} failed request(s)</small></span></article>)}</div></div>}
      </div>}

      {activeTab === "access" && <div className="serving-tab-content serving-access-layout">
        <div className="panel"><div className="panel-header"><div><span className="builder-kicker">REST API</span><h3>Call this service directly</h3></div><ShieldCheck size={18} /></div><p className="serving-section-intro">Authenticate as an existing platform account. Business Case grants still determine access.</p><div className="serving-code-block"><code>POST {selectedDeployment.endpoint_url}</code><button className="icon-button" type="button" onClick={() => navigator.clipboard.writeText(selectedDeployment.endpoint_url ?? "")}><Copy size={15} /></button></div><pre className="json-output serving-code-example">{JSON.stringify({ instances: [{ record_id: "property-1042", features: { area: 84, rooms: 4 } }] }, null, 2)}</pre></div>
        <div className="panel"><div className="panel-header"><div><span className="builder-kicker">Python client</span><h3>Create client credential</h3></div><KeyRound size={18} /></div><p className="serving-section-intro">Create a revocable credential for scripts and notebooks. The secret is displayed only once.</p><button className="primary-button" type="button" onClick={() => { setCredential(""); setModal("credential"); }}><KeyRound size={16} /> Generate credential</button></div>
      </div>}

      {modal === "revision" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog serving-revision-dialog" role="dialog" aria-modal="true" aria-labelledby="revision-title"><div className="modal-header"><div><span className="builder-kicker">Immutable configuration</span><h2 id="revision-title">Configure model roles</h2><p>Saving creates and immediately activates a new service revision. The previous revision remains auditable.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><div className="serving-role-help"><span><strong>Champion</strong> public traffic</span><span><strong>Challenger</strong> direct tests and replay</span><span><strong>Shadow</strong> copied live traffic</span><span><strong>Fallback</strong> technical failures</span></div><div className="serving-role-grid">{eligibleModels.map((model) => <label key={model.id}><span>{model.name} · {model.version}<small>{model.stage}</small></span><select value={roleByModel[model.id] ?? ""} onChange={(event) => setRoleByModel((current) => ({ ...current, [model.id]: event.target.value as DeploymentRole | "" }))}><option value="">Not assigned</option><option value="champion" disabled={model.stage !== "production"}>Champion</option><option value="challenger" disabled={!['staging', 'production'].includes(model.stage)}>Challenger</option><option value="shadow" disabled={!['staging', 'production'].includes(model.stage)}>Shadow</option><option value="fallback" disabled={model.stage !== "production"}>Fallback</option></select></label>)}</div><label>Reason for change<input value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} placeholder="e.g. Add validated challenger v6" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={activateRevision} disabled={busy || !revisionReason.trim()}><GitBranch size={15} /> Activate new revision</button></div></div></div>}

      {modal === "history" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="history-title"><div className="modal-header"><div><span className="builder-kicker">Immutable history</span><h2 id="history-title">Service revisions</h2><p>Rollback copies a historical configuration into a new auditable revision.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><div className="model-version-list">{revisions.map((revision) => <article key={revision.id}><div className="model-version-marker"><span>v{revision.version_number}</span></div><div><strong>Revision v{revision.version_number}</strong><span>{formatDate(revision.created_at)} · {revision.assignments.length} assigned model(s)</span><small>{revision.reason || "No reason recorded"}</small></div>{revision.id === selectedDeployment.active_revision_id ? <i className="pipeline-status published">active</i> : <button className="secondary-button compact-button" type="button" onClick={() => setRollbackRevisionId(revision.id)}>Select rollback</button>}</article>)}</div>{rollbackRevisionId && <label>Rollback reason<input value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} placeholder="Why is this revision being restored?" /></label>}</div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Close</button><button className="primary-button" type="button" onClick={rollbackDeployment} disabled={busy || !rollbackRevisionId || !revisionReason.trim()}><History size={15} /> Roll back</button></div></div></div>}

      {modal === "lifecycle" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="lifecycle-title"><div className="modal-header"><div><span className="builder-kicker">Service lifecycle</span><h2 id="lifecycle-title">{selectedDeployment.status === "running" ? "Stop service" : "Validate and resume service"}</h2><p>{selectedDeployment.status === "running" ? "The endpoint will reject scoring while revision history remains available." : "The active revision will be validated before traffic is accepted."}</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Reason<input value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} placeholder="Reason for this operational change" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={changeDeploymentStatus} disabled={busy || !lifecycleReason.trim()}>{selectedDeployment.status === "running" ? "Stop service" : "Validate & resume"}</button></div></div></div>}

      {modal === "replay" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="replay-title"><div className="modal-header"><div><span className="builder-kicker">Batch evaluation</span><h2 id="replay-title">Replay historical traffic</h2><p>Score up to 1,000 retained requests with a challenger. Production responses are not changed.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Challenger<select value={scoreTarget === "champion" ? "" : scoreTarget} onChange={(event) => setScoreTarget(event.target.value)}><option value="">Choose a challenger</option>{challengers.map((item) => <option key={item.model_id} value={item.model_id}>{modelLabel(item.model_id)}</option>)}</select></label><div className="serving-inline-warning">Replay uses the current immutable revision and retained historical inputs.</div></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={replayChallenger} disabled={busy || scoreTarget === "champion" || !scoreTarget}><History size={16} /> Queue replay</button></div></div></div>}

      {modal === "credential" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="credential-title"><div className="modal-header"><div><span className="builder-kicker">Python client</span><h2 id="credential-title">{credential ? "Copy your credential" : "Generate client credential"}</h2><p>{credential ? "This secret will not be shown again after you close this window." : "The credential inherits your current account and Business Case permissions."}</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body">{credential ? <div className="credential-once"><strong>Copy now — shown once</strong><code>{credential}</code><button className="secondary-button" type="button" onClick={() => navigator.clipboard.writeText(credential)}><Copy size={15} /> Copy credential</button></div> : <div className="serving-credential-explainer"><ShieldCheck size={24} /><p>You can revoke this credential later through the API. Creating it does not bypass platform permissions.</p></div>}</div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>{credential ? "Done" : "Cancel"}</button>{!credential && <button className="primary-button" type="button" onClick={createCredential} disabled={busy}><KeyRound size={16} /> Generate credential</button>}</div></div></div>}

      {modal === "inference" && inferenceDetail && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog serving-inference-dialog" role="dialog" aria-modal="true" aria-labelledby="inference-title"><div className="modal-header"><div><span className="builder-kicker">Audited request</span><h2 id="inference-title">Inference details</h2><p>Stored request, response and per-model executions.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body"><pre className="json-output">{JSON.stringify(inferenceDetail, null, 2)}</pre></div></div></div>}
    </section>
  );
}
