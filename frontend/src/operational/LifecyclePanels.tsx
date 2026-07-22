import { Activity, Archive, ArrowLeft, BarChart3, Brain, Copy, Eye, GitBranch, History, KeyRound, Play, Plus, Rocket, RotateCcw, Search, Settings2, ShieldCheck, SlidersHorizontal, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";

import { api } from "../api/client";
import type {
  DataAsset,
  DatasetLineageReference,
  BusinessCase,
  BusinessCaseDataAttachment,
  ChallengerReplay,
  Deployment,
  DeploymentModelOption,
  DeploymentRevision,
  DeploymentRole,
  InferenceRequestSummary,
  InferenceInputContract,
  ModelArtifact,
  ModelEvaluationSnapshot,
  ModelServingUsage,
  OnlineMonitoringBucketEvaluation,
  OnlineMonitoringRun,
  Pipeline,
  ScoreResponse
} from "../api/client";
import { AssetList } from "../components/AssetList";
import { ArtifactFilters, pipelineMatches } from "../components/ArtifactFilters";
import { DialogNavigationActions, useVersionedResourceNavigation } from "../components/dialogNavigation";
import { ModelPerformanceReport, ModelPerformanceSeriesReport } from "../pipelines/PipelineRunDialogs";
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
  const modelNavigation = useVersionedResourceNavigation<ModelArtifact>();
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
                  <button className="secondary-button compact-button" type="button" onClick={() => modelNavigation.openHistory(model)}>
                    <History size={14} /> Versions
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => void api.getModel(model.id).then(modelNavigation.openDirect)}>
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
      {modelNavigation.selected && (
        <ModelDetailsDialog
          model={modelNavigation.selected}
          businessCaseName={businessCaseById.get(modelNavigation.selected.business_case_id)?.name ?? "Unassigned"}
          pipelineName={pipelineById.get(modelNavigation.selected.pipeline_id)?.name ?? "Unknown pipeline"}
          onClose={modelNavigation.closeAll}
          onBack={modelNavigation.hasBack ? modelNavigation.back : undefined}
          onOpenDataset={onOpenDataset}
          onStageChanged={async (updated) => {
            modelNavigation.replaceSelected(updated);
            await onRefresh();
            setNotice(`Model ${updated.version} stage changed to ${updated.stage}`);
          }}
        />
      )}
      {modelNavigation.showHistory && modelNavigation.history && (
        <ModelVersionHistoryDialog
          model={modelNavigation.history}
          businessCaseName={businessCaseById.get(modelNavigation.history.business_case_id)?.name ?? "Unassigned"}
          pipelineName={pipelineById.get(modelNavigation.history.pipeline_id)?.name ?? "Unknown pipeline"}
          onClose={modelNavigation.closeHistory}
          onView={async (version) => {
            const fullModel = await api.getModel(version.id);
            modelNavigation.openVersion(fullModel);
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
                  <i className={`model-stage-badge ${version.stage}`}>{version.stage}</i>
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
  onBack,
  onOpenDataset,
  onStageChanged
}: {
  model: ModelArtifact;
  businessCaseName: string;
  pipelineName: string;
  onClose: () => void;
  onBack?: () => void;
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
          <DialogNavigationActions onBack={onBack} onClose={onClose} closeLabel="Close model details" />
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

function monitoringDateInput(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function monitoringMetrics(run: OnlineMonitoringRun) {
  const performance = run.report.performance as Record<string, unknown> | undefined;
  const service = performance?.service as Record<string, unknown> | undefined;
  return Array.isArray(service?.metrics)
    ? service.metrics as Array<{ id: string; label: string; value: number | null }>
    : [];
}

function monitoringHasActuals(run: OnlineMonitoringRun) {
  const actuals = run.report.actuals as Record<string, unknown> | undefined;
  return actuals?.status === "provided" || (!actuals?.status && Boolean(run.actuals_dataset_id));
}

type MonitoringBucket = {
  label: string;
  bucket_start: string;
  bucket_end: string;
  request_count: number;
  failed_request_count: number;
  fallback_request_count: number;
  p95_latency_ms: number | null;
  served_prediction_count: number;
};

function monitoringBucketDisplayLabel(bucketStart: string, bucketEnd: string, fallback: string) {
  const start = new Date(bucketStart);
  const end = new Date(bucketEnd);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return fallback;
  const date = new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(start);
  const time = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  return `${date} ${time.format(start)}–${time.format(end)}`;
}

function monitoringBuckets(run: OnlineMonitoringRun): MonitoringBucket[] {
  const aggregation = run.report.time_aggregation as Record<string, unknown> | undefined;
  if (!Array.isArray(aggregation?.buckets)) return [];
  return (aggregation.buckets as Array<Record<string, unknown>>).map((bucket) => {
    const bucketStart = String(bucket.bucket_start ?? "");
    const bucketEnd = String(bucket.bucket_end ?? "");
    return {
      label: monitoringBucketDisplayLabel(bucketStart, bucketEnd, String(bucket.label ?? "")),
      bucket_start: bucketStart,
      bucket_end: bucketEnd,
      request_count: Number(bucket.request_count ?? 0),
      failed_request_count: Number(bucket.failed_request_count ?? 0),
      fallback_request_count: Number(bucket.fallback_request_count ?? 0),
      p95_latency_ms: bucket.p95_latency_ms == null ? null : Number(bucket.p95_latency_ms),
      served_prediction_count: Number(bucket.served_prediction_count ?? 0),
    };
  });
}

type MonitoringPerformanceSeries = {
  id: string;
  label: string;
  unit: string;
  direction: string;
  points: Array<{ bucket_start: string; evaluated_row_count: number; value: number | null }>;
};

function monitoringPerformanceSeries(run: OnlineMonitoringRun): MonitoringPerformanceSeries[] {
  const aggregation = objectValue(run.report.time_aggregation);
  const performanceSeries = objectValue(aggregation.performance_series);
  return Array.isArray(performanceSeries.metrics)
    ? performanceSeries.metrics as MonitoringPerformanceSeries[]
    : [];
}

function monitoringBucketKey(value: string) {
  return value.replace(/(?:Z|\+00:00)$/, "");
}

function formatMonitoringMetric(value: number | null, unit: string) {
  if (value == null) return "—";
  return unit === "ratio"
    ? `${(value * 100).toFixed(1)}%`
    : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function MonitoringVisualizationModal({ run, onClose }: { run: OnlineMonitoringRun; onClose: () => void }) {
  const buckets = monitoringBuckets(run);
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, buckets.length - 1));
  const hasActuals = monitoringHasActuals(run);
  const performance = objectValue(run.report.performance);
  const servicePerformance = objectValue(performance.service);
  const rawFullWindowPerformance = hasActuals && servicePerformance.kind === "model_performance"
    ? servicePerformance as ModelEvaluationSnapshot
    : null;
  const hasInvalidLegacyScoreContract = Boolean(
    rawFullWindowPerformance
    && rawFullWindowPerformance.positive_class == null
    && rawFullWindowPerformance.metrics.some((metric) => metric.id === "roc_auc")
  );
  const invalidScoreMetricIds = new Set(["roc_auc", "average_precision", "brier_score", "log_loss"]);
  const fullWindowPerformance = rawFullWindowPerformance && hasInvalidLegacyScoreContract
    ? {
        ...rawFullWindowPerformance,
        metrics: rawFullWindowPerformance.metrics.filter((metric) => !invalidScoreMetricIds.has(metric.id)),
        curves: {},
        distributions: {},
        warnings: [
          "Score-based charts were omitted because this legacy report did not record a positive class. Run monitoring again to calculate them correctly.",
          ...rawFullWindowPerformance.warnings,
        ],
      }
    : rawFullWindowPerformance;
  const performanceSeries = monitoringPerformanceSeries(run);
  const evaluatedRowsByBucket = new Map(
    (performanceSeries[0]?.points ?? []).map((point) => [
      monitoringBucketKey(point.bucket_start),
      point.evaluated_row_count,
    ])
  );
  const initiallySelectedQualityBuckets = buckets
    .filter((bucket) => (evaluatedRowsByBucket.get(monitoringBucketKey(bucket.bucket_start)) ?? 0) > 0)
    .slice(-2)
    .map((bucket) => bucket.bucket_start);
  const qualityTab = run.problem_type === "regression" ? "regression" : "classification";
  type MonitoringVisualTab = "traffic" | "latency" | "reliability" | "classification" | "regression";
  const [qualityMode, setQualityMode] = useState<"full" | "aggregated">("full");
  const [activeTab, setActiveTab] = useState<MonitoringVisualTab>("traffic");
  const [selectedQualityBuckets, setSelectedQualityBuckets] = useState<string[]>(initiallySelectedQualityBuckets);
  const [bucketEvaluations, setBucketEvaluations] = useState<OnlineMonitoringBucketEvaluation[]>([]);
  const [bucketEvaluationLoading, setBucketEvaluationLoading] = useState(false);
  const [bucketEvaluationError, setBucketEvaluationError] = useState("");
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  useEffect(() => {
    if (qualityMode !== "aggregated" || selectedQualityBuckets.length === 0) {
      setBucketEvaluations([]);
      setBucketEvaluationError("");
      setBucketEvaluationLoading(false);
      return;
    }
    let active = true;
    setBucketEvaluationLoading(true);
    setBucketEvaluationError("");
    api.getOnlineMonitoringBucketEvaluations(run.id, selectedQualityBuckets)
      .then((items) => {
        if (active) setBucketEvaluations(items);
      })
      .catch((error) => {
        if (active) {
          setBucketEvaluations([]);
          setBucketEvaluationError(error instanceof Error ? error.message : "Could not load selected period charts");
        }
      })
      .finally(() => {
        if (active) setBucketEvaluationLoading(false);
      });
    return () => { active = false; };
  }, [qualityMode, run.id, selectedQualityBuckets]);
  const selected = buckets[selectedIndex] ?? buckets[0];
  const aggregation = run.report.time_aggregation as Record<string, unknown> | undefined;
  const chartWidth = 1040;
  const plotLeft = 66;
  const plotRight = 1018;
  const xAt = (index: number) => buckets.length <= 1
    ? (plotLeft + plotRight) / 2
    : plotLeft + (index / (buckets.length - 1)) * (plotRight - plotLeft);
  const pickFromPointer = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * chartWidth;
    const ratio = Math.max(0, Math.min(1, (svgX - plotLeft) / (plotRight - plotLeft)));
    setSelectedIndex(Math.round(ratio * Math.max(0, buckets.length - 1)));
  };
  const axisLabels = Array.from(new Set([0, Math.floor((buckets.length - 1) / 2), buckets.length - 1])).filter((index) => index >= 0);

  function lineChart(
    title: string,
    series: Array<{ label: string; values: Array<number | null>; className: string }>,
    valueLabel: (value: number) => string,
  ) {
    const values = series.flatMap((item) => item.values.filter((value): value is number => value != null));
    const min = Math.min(0, ...values);
    const max = Math.max(min === 0 ? 1 : 0, ...values);
    const span = max - min || 1;
    const top = 28;
    const bottom = 166;
    const yAt = (value: number) => bottom - ((value - min) / span) * (bottom - top);
    return <div className="serving-monitoring-chart"><div className="serving-monitoring-chart-title"><strong>{title}</strong><span>{series.map((item) => <span key={item.label} className={item.className}><i />{item.label}</span>)}</span></div><svg viewBox={`0 0 ${chartWidth} 210`} role="img" aria-label={`${title} over ${buckets.length} ${String(aggregation?.granularity ?? "time")} buckets`} onMouseMove={pickFromPointer}>
      {[0, 0.5, 1].map((ratio) => <g key={ratio}><line className="monitoring-chart-grid" x1={plotLeft} x2={plotRight} y1={bottom - ratio * (bottom - top)} y2={bottom - ratio * (bottom - top)} /><text className="monitoring-chart-axis" x={plotLeft - 10} y={bottom - ratio * (bottom - top) + 4} textAnchor="end">{valueLabel(min + span * ratio)}</text></g>)}
      {axisLabels.map((index) => <text key={index} className="monitoring-chart-axis" x={xAt(index)} y={194} textAnchor={index === 0 ? "start" : index === buckets.length - 1 ? "end" : "middle"}>{buckets[index]?.label ?? ""}</text>)}
      {series.map((item) => {
        let drawing = false;
        const path = item.values.map((value, index) => {
          if (value == null) {
            drawing = false;
            return "";
          }
          const command = drawing ? "L" : "M";
          drawing = true;
          return `${command}${xAt(index)},${yAt(value)}`;
        }).join(" ");
        const selectedValue = item.values[selectedIndex];
        return <g key={item.label} className={item.className}><path className="monitoring-chart-line" d={path} fill="none" />{selectedValue != null && <circle className="monitoring-chart-point" cx={xAt(selectedIndex)} cy={yAt(selectedValue)} r="5" />}</g>;
      })}
      <line className="monitoring-chart-cursor" x1={xAt(selectedIndex)} x2={xAt(selectedIndex)} y1={top} y2={bottom} />
    </svg></div>;
  }

  const tabs: Array<{ id: MonitoringVisualTab; label: string }> = [
    { id: "traffic", label: "Traffic" },
    { id: "latency", label: "Latency" },
    { id: "reliability", label: "Failures / fallbacks" },
  ];
  if (hasActuals) tabs.push({
    id: qualityTab,
    label: qualityTab === "regression" ? "Regression" : "Classification",
  });
  const isQualityTab = activeTab === "classification" || activeTab === "regression";
  const formatCountAxis = (value: number) => value.toLocaleString(undefined, {
    maximumFractionDigits: value > 0 && value < 10 ? 1 : 0,
  });
  const metricValue = (metric: MonitoringPerformanceSeries, bucketStart: string) => metric.points.find(
    (point) => monitoringBucketKey(point.bucket_start) === monitoringBucketKey(bucketStart)
  )?.value ?? null;
  const evaluatedRows = (bucketStart: string) => evaluatedRowsByBucket.get(monitoringBucketKey(bucketStart)) ?? 0;
  const toggleQualityBucket = (bucketStart: string) => {
    setSelectedQualityBuckets((current) => current.includes(bucketStart)
      ? current.filter((item) => item !== bucketStart)
      : current.length < 8 ? [...current, bucketStart] : current);
  };

  return <div className="modal-backdrop serving-monitoring-visual-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal-dialog serving-monitoring-visual-dialog" role="dialog" aria-modal="true" aria-labelledby="monitoring-visual-title"><div className="modal-header"><div><span className="builder-kicker">Full-scope monitoring · scored_at · local time</span><h2 id="monitoring-visual-title">Monitoring report visualization</h2><p>{formatDate(run.since)} — {formatDate(run.until)} · {buckets.length} {String(aggregation?.granularity ?? "time")} buckets</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close monitoring visualization"><X size={18} /></button></div><div className="serving-monitoring-visual-content">
    <div className="serving-monitoring-visual-tabs" role="tablist" aria-label="Monitoring chart category">
      {tabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={`monitoring-panel-${tab.id}`} id={`monitoring-tab-${tab.id}`} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
    </div>
    <section className="serving-monitoring-visual-panel" role="tabpanel" id={`monitoring-panel-${activeTab}`} aria-labelledby={`monitoring-tab-${activeTab}`}>
      {!isQualityTab && selected && <div className="serving-monitoring-selected-period"><strong>{selected.label}</strong>{activeTab === "traffic" && <><span>{selected.request_count} requests</span><span>{selected.served_prediction_count} served</span></>}{activeTab === "latency" && <span>{selected.p95_latency_ms == null ? "No latency data" : `${Math.round(selected.p95_latency_ms)} ms p95`}</span>}{activeTab === "reliability" && <><span>{selected.failed_request_count} failed</span><span>{selected.fallback_request_count} fallback</span></>}</div>}
      {activeTab === "traffic" && <div className="serving-monitoring-traffic-charts">{lineChart("Requests", [{ label: "Requests", values: buckets.map((item) => item.request_count), className: "series-requests" }], formatCountAxis)}{lineChart("Served predictions", [{ label: "Served predictions", values: buckets.map((item) => item.served_prediction_count), className: "series-served" }], formatCountAxis)}</div>}
      {activeTab === "latency" && lineChart("P95 request latency", [{ label: "P95 latency", values: buckets.map((item) => item.p95_latency_ms), className: "series-latency" }], (value) => `${Math.round(value)} ms`)}
      {activeTab === "reliability" && lineChart("Failed requests and fallback use", [{ label: "Failed", values: buckets.map((item) => item.failed_request_count), className: "series-failed" }, { label: "Fallback", values: buckets.map((item) => item.fallback_request_count), className: "series-fallback" }], formatCountAxis)}
      {isQualityTab && <div className="serving-monitoring-quality-view">
        <div className="serving-monitoring-view-switch" role="group" aria-label="Model quality scope">
          <button type="button" aria-pressed={qualityMode === "full"} onClick={() => setQualityMode("full")}>Full window</button>
          <button type="button" aria-pressed={qualityMode === "aggregated"} disabled={!performanceSeries.length} onClick={() => setQualityMode("aggregated")}>Per {String(aggregation?.granularity ?? "time bucket")}</button>
        </div>
        {qualityMode === "full" && fullWindowPerformance && <ModelPerformanceReport report={fullWindowPerformance} />}
        {qualityMode === "aggregated" && performanceSeries.length > 0 && <>
          <div className="serving-monitoring-metrics-table-wrap">
            <table className="serving-monitoring-metrics-table">
              <thead><tr><th>Period</th><th className="numeric">Evaluated rows</th>{performanceSeries.map((metric) => <th className="numeric" key={metric.id}>{metric.label}</th>)}</tr></thead>
              <tbody>{buckets.map((bucket) => <tr key={bucket.bucket_start}><th scope="row">{bucket.label}</th><td className="numeric">{evaluatedRows(bucket.bucket_start).toLocaleString()}</td>{performanceSeries.map((metric) => <td className="numeric" key={metric.id}>{formatMonitoringMetric(metricValue(metric, bucket.bucket_start), metric.unit)}</td>)}</tr>)}</tbody>
            </table>
          </div>
          <section className="serving-monitoring-series-selector" aria-labelledby="monitoring-series-heading">
            <div><strong id="monitoring-series-heading">Chart series</strong><span>Select up to 8 periods to compare full-bucket chart statistics.</span></div>
            <div className="serving-monitoring-series-options">{buckets.map((bucket, index) => {
              const checked = selectedQualityBuckets.includes(bucket.bucket_start);
              const hasRows = evaluatedRows(bucket.bucket_start) > 0;
              const disabled = !hasRows || (!checked && selectedQualityBuckets.length >= 8);
              const inputId = `monitoring-series-${run.id}-${index}`;
              return <label key={bucket.bucket_start} htmlFor={inputId}><input id={inputId} type="checkbox" checked={checked} disabled={disabled} onChange={() => toggleQualityBucket(bucket.bucket_start)} /><span>{bucket.label}</span><small>{hasRows ? `${evaluatedRows(bucket.bucket_start).toLocaleString()} rows` : "No evaluated rows"}</small></label>;
            })}</div>
          </section>
          {bucketEvaluationLoading && <div className="serving-monitoring-series-status">Calculating chart series for the selected full buckets…</div>}
          {bucketEvaluationError && <div className="serving-inline-warning">{bucketEvaluationError}</div>}
          {!bucketEvaluationLoading && !bucketEvaluationError && selectedQualityBuckets.length === 0 && <div className="serving-monitoring-series-status">Select at least one period to show chart statistics.</div>}
          {!bucketEvaluationLoading && !bucketEvaluationError && bucketEvaluations.length > 0 && <ModelPerformanceSeriesReport series={bucketEvaluations.map((item) => ({ label: monitoringBucketDisplayLabel(item.bucket_start, item.bucket_end, item.label), evaluation: item.evaluation }))} />}
        </>}
        {qualityMode === "aggregated" && !performanceSeries.length && <div className="serving-inline-warning">Aggregated performance series are unavailable in this immutable report. Run monitoring again after this update to calculate them.</div>}
      </div>}
    </section>
    {selected && !isQualityTab && <label className="serving-monitoring-period-slider"><span>Selected period <strong>{selected.label}</strong></span><input type="range" min={0} max={Math.max(0, buckets.length - 1)} value={selectedIndex} onChange={(event) => setSelectedIndex(Number(event.target.value))} aria-label="Select monitoring period" /></label>}
  </div></div></div>;
}

export function ServingPanel({
  deployments,
  datasets,
  models,
  initialDeploymentId = "",
  onRefresh,
  onRegisterRefresh,
  setNotice
}: {
  deployments: Deployment[];
  datasets: DataAsset[];
  models: ModelArtifact[];
  initialDeploymentId?: string;
  onRefresh: () => Promise<void>;
  onRegisterRefresh?: (handler: (() => Promise<void>) | null) => void;
  setNotice: NoticeSetter;
}) {
  type ServingTab = "overview" | "test" | "traffic" | "monitoring" | "access";
  type ServingModal = "create" | "revision" | "history" | "lifecycle" | "archive" | "credential" | "replay" | "inference" | null;
  const [serviceName, setServiceName] = useState("");
  const [modelId, setModelId] = useState("");
  const [deploymentId, setDeploymentId] = useState("");
  const [activeTab, setActiveTab] = useState<ServingTab>("overview");
  const [modal, setModal] = useState<ServingModal>(null);
  const [recordId, setRecordId] = useState("");
  const [payloadJson, setPayloadJson] = useState("{\n  \"instances\": [\n    {\n      \"record_id\": \"example-1\",\n      \"features\": {}\n    }\n  ]\n}");
  const [testInputMode, setTestInputMode] = useState<"form" | "json">("form");
  const [inputContract, setInputContract] = useState<InferenceInputContract | null>(null);
  const [featureValues, setFeatureValues] = useState<Record<string, unknown>>({});
  const [contractError, setContractError] = useState("");
  const [modelOptions, setModelOptions] = useState<DeploymentModelOption[]>([]);
  const [revisionError, setRevisionError] = useState("");
  const [scoreTarget, setScoreTarget] = useState("champion");
  const [scoreResult, setScoreResult] = useState<ScoreResponse | null>(null);
  const [scorePhase, setScorePhase] = useState<"idle" | "scoring" | "success" | "error">("idle");
  const [scoreError, setScoreError] = useState("");
  const [scoreElapsedSeconds, setScoreElapsedSeconds] = useState(0);
  const [history, setHistory] = useState<InferenceRequestSummary[]>([]);
  const [inferenceDetail, setInferenceDetail] = useState<Record<string, unknown> | null>(null);
  const [replays, setReplays] = useState<ChallengerReplay[]>([]);
  const [revisions, setRevisions] = useState<DeploymentRevision[]>([]);
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [roleByModel, setRoleByModel] = useState<Record<string, DeploymentRole | "">>({});
  const [revisionReason, setRevisionReason] = useState("");
  const [lifecycleReason, setLifecycleReason] = useState("");
  const [rollbackRevisionId, setRollbackRevisionId] = useState("");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const [catalogMode, setCatalogMode] = useState<"services" | "monitoring">("services");
  const [monitoringRuns, setMonitoringRuns] = useState<OnlineMonitoringRun[]>([]);
  const [monitoringAttachments, setMonitoringAttachments] = useState<BusinessCaseDataAttachment[]>([]);
  const [actualsDatasetId, setActualsDatasetId] = useState("");
  const [monitoringSince, setMonitoringSince] = useState(() => monitoringDateInput(new Date(Date.now() - 24 * 60 * 60 * 1000)));
  const [monitoringUntil, setMonitoringUntil] = useState(() => monitoringDateInput(new Date()));
  const [monitoringTargetColumn, setMonitoringTargetColumn] = useState("");
  const [monitoringRecordColumn, setMonitoringRecordColumn] = useState("");
  const [monitoringAggregation, setMonitoringAggregation] = useState<"none" | "hour" | "day" | "week" | "month">("none");
  const [monitoringVisualizationRunId, setMonitoringVisualizationRunId] = useState("");
  const [monitoringError, setMonitoringError] = useState("");
  const [selectedComparisonIds, setSelectedComparisonIds] = useState<string[]>([]);
  const selectedDeployment = deployments.find((item) => item.id === deploymentId);
  const eligibleModels = models.filter((item) =>
    item.business_case_id === selectedDeployment?.business_case_id
    && ["staging", "production"].includes(item.stage)
  );
  const productionModels = models.filter((item) => item.stage === "production" && item.business_case_id);
  const actualsOptions = monitoringAttachments
    .filter((item) => item.role === "monitoring_actuals")
    .map((attachment) => ({ attachment, dataset: datasets.find((item) => item.id === attachment.data_asset_id) }))
    .filter((item): item is { attachment: BusinessCaseDataAttachment; dataset: DataAsset } => Boolean(item.dataset));

  useEffect(() => {
    let active = true;
    api.listOnlineMonitoringRuns()
      .then((items) => active && setMonitoringRuns(items))
      .catch((error) => active && setMonitoringError(error instanceof Error ? error.message : "Could not load monitoring reports"));
    return () => { active = false; };
  }, [deployments.length]);

  useEffect(() => {
    if (!monitoringRuns.some((item) => item.status === "queued" || item.status === "running")) return;
    const timer = window.setInterval(() => {
      void api.listOnlineMonitoringRuns()
        .then(setMonitoringRuns)
        .catch((error) => setMonitoringError(error instanceof Error ? error.message : "Could not refresh monitoring runs"));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [monitoringRuns]);

  useEffect(() => {
    if (!selectedDeployment) {
      setMonitoringAttachments([]);
      return;
    }
    let active = true;
    api.listBusinessCaseDataAttachments(selectedDeployment.business_case_id)
      .then((items) => {
        if (!active) return;
        setMonitoringAttachments(items);
        const actuals = items.find((item) => item.role === "monitoring_actuals");
        setActualsDatasetId((current) => current || actuals?.data_asset_id || "");
        setMonitoringTargetColumn((current) => current || actuals?.target_column || "");
        setMonitoringRecordColumn((current) => current || actuals?.primary_key_column || "");
      })
      .catch((error) => active && setMonitoringError(error instanceof Error ? error.message : "Could not load actuals attachments"));
    return () => { active = false; };
  }, [selectedDeployment?.id, selectedDeployment?.business_case_id]);

  useEffect(() => {
    setSelectedComparisonIds((current) => current.length ? current : deployments.slice(0, 2).map((item) => item.id));
  }, [deployments]);

  async function refreshServingActivity(deployment: Deployment) {
    if (historyLoading) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const [page, replayItems] = await Promise.all([
        api.inferenceLogSummary(deployment.id, 50),
        api.listChallengerReplays(deployment.id)
      ]);
      setHistory(page.items);
      setReplays(replayItems);
      setNotice("Traffic & audit refreshed");
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not refresh serving activity");
    } finally {
      setHistoryLoading(false);
    }
  }

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
      api.inferenceLogSummary(selectedDeployment.id, 50),
      api.listChallengerReplays(selectedDeployment.id),
      api.listDeploymentRevisions(selectedDeployment.id),
      api.deploymentModelOptions(selectedDeployment.id)
    ])
      .then(([page, replayItems, revisionItems, options]) => { if (active) {
        setHistory(page.items);
        setReplays(replayItems);
        setRevisions(revisionItems);
        setModelOptions(options);
      } })
      .catch((error) => active && setHistoryError(error instanceof Error ? error.message : "Could not load inference history"));
    return () => { active = false; };
  }, [selectedDeployment?.id, selectedDeployment?.active_revision_id]);

  useEffect(() => {
    if (!selectedDeployment) {
      setInputContract(null);
      setFeatureValues({});
      return;
    }
    let active = true;
    setContractError("");
    const challenger = scoreTarget === "champion" ? undefined : scoreTarget;
    api.deploymentInputContract(selectedDeployment.id, challenger)
      .then((contract) => {
        if (!active) return;
        setInputContract(contract);
        setFeatureValues(contract.example_features);
      })
      .catch((error) => {
        if (!active) return;
        setInputContract(null);
        setFeatureValues({});
        setContractError(error instanceof Error ? error.message : "Could not load the model input contract");
      });
    return () => { active = false; };
  }, [selectedDeployment?.id, selectedDeployment?.active_revision_id, scoreTarget]);

  useEffect(() => {
    if (scorePhase !== "scoring") return;
    const startedAt = Date.now();
    setScoreElapsedSeconds(0);
    const interval = window.setInterval(() => {
      setScoreElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
    return () => window.clearInterval(interval);
  }, [scorePhase]);

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
    let instances: Array<{ record_id?: string; features: Record<string, unknown> }>;
    if (testInputMode === "json") {
      try {
        const payload = JSON.parse(payloadJson) as { instances?: unknown };
        if (!Array.isArray(payload.instances) || !payload.instances.length) throw new Error();
        instances = payload.instances as Array<{ record_id?: string; features: Record<string, unknown> }>;
        if (instances.some((item) => !item || typeof item.features !== "object" || Array.isArray(item.features))) throw new Error();
      } catch {
        setNotice("Payload must contain a non-empty instances array with a features object in every item");
        return;
      }
    } else {
      const missing = inputContract?.fields.filter((field) => field.required && (featureValues[field.name] === "" || featureValues[field.name] == null)) ?? [];
      if (missing.length) {
        setNotice(`Complete required fields: ${missing.map((field) => field.name).join(", ")}`);
        return;
      }
      instances = [{ record_id: recordId || undefined, features: featureValues }];
    }
    setBusy(true);
    setScoreResult(null);
    setScoreError("");
    setScorePhase("scoring");
    try {
      const challenger = scoreTarget === "champion" ? undefined : scoreTarget;
      const result = await api.score(selectedDeployment.id, instances, challenger);
      setScoreResult(result);
      setScorePhase("success");
      setNotice(`Scored with ${result.served_role} model ${shortId(result.model_id)}`);
      void api.inferenceLogSummary(selectedDeployment.id, 50)
        .then((page) => setHistory(page.items))
        .catch((error) => setHistoryError(error instanceof Error ? error.message : "Prediction returned, but inference history could not be refreshed"));
    } catch (error) {
      const message = error instanceof Error ? error.message : "The scoring request failed";
      setScoreError(message);
      setScorePhase("error");
      setNotice(message);
    } finally {
      setBusy(false);
    }
  }

  function generatePayload() {
    const payload = {
      instances: [{
        ...(recordId.trim() ? { record_id: recordId.trim() } : {}),
        features: featureValues
      }]
    };
    setPayloadJson(JSON.stringify(payload, null, 2));
    setTestInputMode("json");
    setNotice("Payload generated from the form; you can now edit or copy it as JSON");
  }

  function updateFeature(name: string, valueType: string, rawValue: string | boolean) {
    let value: unknown = rawValue;
    if ((valueType === "number" || valueType === "integer") && typeof rawValue === "string") {
      value = rawValue === "" ? "" : Number(rawValue);
    }
    setFeatureValues((current) => ({ ...current, [name]: value }));
  }

  async function activateRevision() {
    if (!selectedDeployment) return;
    const eligibleModelIds = new Set(eligibleModels.map((model) => model.id));
    const assignments = Object.entries(roleByModel)
      .filter((entry): entry is [string, DeploymentRole] => Boolean(entry[1]) && eligibleModelIds.has(entry[0]))
      .map(([assignedModelId, role]) => ({ model_id: assignedModelId, role }));
    if (assignments.filter((item) => item.role === "champion").length !== 1) {
      setNotice("Choose exactly one champion");
      return;
    }
    if (assignments.filter((item) => item.role === "fallback").length > 1) {
      setNotice("Choose at most one fallback");
      return;
    }
    const selectedChampionId = assignments.find((item) => item.role === "champion")?.model_id;
    const championSignature = modelOptions.find((item) => item.model_id === selectedChampionId)?.contract_signature;
    const incompatible = assignments.filter((item) =>
      item.model_id !== selectedChampionId
      && modelOptions.find((option) => option.model_id === item.model_id)?.contract_signature !== championSignature
    );
    if (incompatible.length) {
      const message = "All challenger, shadow and fallback models must have the same input and output contract as the selected champion.";
      setRevisionError(message);
      setNotice(message);
      return;
    }
    setBusy(true);
    setRevisionError("");
    try {
      await api.createDeploymentRevision(selectedDeployment.id, assignments, revisionReason);
      setRevisionReason("");
      setModal(null);
      setNotice("New immutable service revision activated");
      await onRefresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not activate the service revision";
      setRevisionError(message);
      setNotice(`Revision was not activated: ${message}`);
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

  async function archiveDeployment() {
    if (!selectedDeployment || !lifecycleReason.trim()) return;
    setBusy(true);
    try {
      await api.setDeploymentStatus(selectedDeployment.id, "archived", lifecycleReason.trim());
      setLifecycleReason("");
      setModal(null);
      setDeploymentId("");
      setNotice("Model service archived; its revisions and inference history were preserved");
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

  async function runOnlineMonitoring() {
    if (!selectedDeployment || !monitoringSince || !monitoringUntil) {
      setNotice("Select a complete monitoring window");
      return;
    }
    setBusy(true);
    setMonitoringError("");
    try {
      const run = await api.createOnlineMonitoringRun(selectedDeployment.id, {
        since: new Date(monitoringSince).toISOString(),
        until: new Date(monitoringUntil).toISOString(),
        aggregation_granularity: monitoringAggregation,
        ...(actualsDatasetId ? { actuals_dataset_id: actualsDatasetId } : {}),
        ...(monitoringTargetColumn.trim() ? { actuals_target_column: monitoringTargetColumn.trim() } : {}),
        join: {
          strategy: "auto",
          ...(monitoringRecordColumn.trim() ? { actuals_record_id_column: monitoringRecordColumn.trim() } : {})
        }
      });
      setMonitoringRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setNotice(actualsDatasetId
        ? "Full-scope online monitoring report with performance evaluation queued"
        : "Full-scope operational monitoring report queued without actuals");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not queue online monitoring";
      setMonitoringError(message);
      setNotice(message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshMonitoringRuns() {
    try {
      const items = selectedDeployment
        ? await api.listDeploymentMonitoringRuns(selectedDeployment.id)
        : await api.listOnlineMonitoringRuns();
      setMonitoringRuns((current) => selectedDeployment
        ? [
            ...items,
            ...current.filter((item) => item.deployment_id !== selectedDeployment.id)
          ]
        : items);
      setMonitoringError("");
      setNotice(selectedDeployment ? "Monitoring tab refreshed" : "Monitoring dashboard refreshed");
    } catch (error) {
      setMonitoringError(error instanceof Error ? error.message : "Could not refresh monitoring reports");
    }
  }

  const refreshAllServingTabs = useCallback(async () => {
    if (!selectedDeployment) {
      const [, runs] = await Promise.all([onRefresh(), api.listOnlineMonitoringRuns()]);
      setMonitoringRuns(runs);
      setMonitoringError("");
      return;
    }

    const challenger = scoreTarget === "champion" ? undefined : scoreTarget;
    const [, page, replayItems, revisionItems, options, contract, runs, attachments] = await Promise.all([
      onRefresh(),
      api.inferenceLogSummary(selectedDeployment.id, 50),
      api.listChallengerReplays(selectedDeployment.id),
      api.listDeploymentRevisions(selectedDeployment.id),
      api.deploymentModelOptions(selectedDeployment.id),
      api.deploymentInputContract(selectedDeployment.id, challenger),
      api.listDeploymentMonitoringRuns(selectedDeployment.id),
      api.listBusinessCaseDataAttachments(selectedDeployment.business_case_id)
    ]);
    setHistory(page.items);
    setReplays(replayItems);
    setRevisions(revisionItems);
    setModelOptions(options);
    setInputContract(contract);
    setFeatureValues(contract.example_features);
    setMonitoringRuns((current) => [
      ...runs,
      ...current.filter((item) => item.deployment_id !== selectedDeployment.id)
    ]);
    setMonitoringAttachments(attachments);
    setHistoryError("");
    setContractError("");
    setMonitoringError("");
  }, [onRefresh, scoreTarget, selectedDeployment]);

  useEffect(() => {
    if (!onRegisterRefresh) return;
    onRegisterRefresh(refreshAllServingTabs);
    return () => onRegisterRefresh(null);
  }, [onRegisterRefresh, refreshAllServingTabs]);

  async function archiveMonitoringRun(runId: string) {
    if (!window.confirm("Archive this monitoring run? Its immutable report and lineage will remain available through the API.")) return;
    try {
      await api.archiveOnlineMonitoringRun(runId);
      setMonitoringRuns((current) => current.filter((item) => item.id !== runId));
      setNotice("Monitoring run archived");
    } catch (error) {
      setMonitoringError(error instanceof Error ? error.message : "Could not archive monitoring run");
    }
  }

  async function archiveMonitoringHistory() {
    if (!selectedDeployment || !window.confirm("Archive all finished monitoring runs for this service? Reports and lineage will remain available through the API.")) return;
    try {
      const result = await api.archiveDeploymentMonitoringHistory(selectedDeployment.id);
      setMonitoringRuns((current) => current.filter((item) =>
        item.deployment_id !== selectedDeployment.id || !["succeeded", "failed"].includes(item.status)
      ));
      setNotice(`${result.archived_run_count} monitoring run(s) archived`);
    } catch (error) {
      setMonitoringError(error instanceof Error ? error.message : "Could not archive monitoring history");
    }
  }

  function toggleComparisonService(serviceId: string) {
    setSelectedComparisonIds((current) =>
      current.includes(serviceId)
        ? current.filter((item) => item !== serviceId)
        : [...current, serviceId]
    );
  }

  function openDeployment(deployment: Deployment) {
    setDeploymentId(deployment.id);
    setActiveTab("overview");
    setScoreResult(null);
    setScorePhase("idle");
    setScoreError("");
    setInferenceDetail(null);
    setCatalogMode("services");
  }

  const assignments = selectedDeployment?.active_revision?.assignments ?? [];
  const champion = assignments.find((item) => item.role === "champion");
  const challengers = assignments.filter((item) => item.role === "challenger");
  const shadows = assignments.filter((item) => item.role === "shadow");
  const fallback = assignments.find((item) => item.role === "fallback");
  const configuredChampionId = Object.entries(roleByModel).find(([, role]) => role === "champion")?.[0];
  const configuredChampionSignature = modelOptions.find((item) => item.model_id === configuredChampionId)?.contract_signature;

  function updateModelRole(assignedModelId: string, role: DeploymentRole | "") {
    setRevisionError("");
    setRoleByModel((current) => {
      const next = { ...current };
      if (role === "champion") {
        for (const [modelId, currentRole] of Object.entries(next)) {
          if (currentRole === "champion" && modelId !== assignedModelId) next[modelId] = "";
        }
      }
      next[assignedModelId] = role;
      return next;
    });
  }

  function modelLabel(assignedModelId: string | undefined) {
    if (!assignedModelId) return "Not configured";
    const option = modelOptions.find((item) => item.model_id === assignedModelId);
    if (option) return `${option.name} · ${option.version}`;
    const model = models.find((item) => item.id === assignedModelId);
    return model ? `${model.name} · ${model.version}` : shortId(assignedModelId);
  }

  function closeModal() {
    setModal(null);
    if (modal === "inference") setInferenceDetail(null);
  }

  const comparisonRuns = selectedComparisonIds.flatMap((serviceId) => {
    const deployment = deployments.find((item) => item.id === serviceId);
    if (!deployment) return [];
    const runs = monitoringRuns.filter((item) => item.deployment_id === serviceId);
    const run = runs.find((item) => item.status === "succeeded") ?? runs[0];
    return [{ deployment, run }];
  });
  const monitoringVisualizationRun = monitoringRuns.find((item) => item.id === monitoringVisualizationRunId) ?? null;

  if (!selectedDeployment) {
    return (
      <section className="serving-catalog">
        <div className="serving-page-header">
          <div>
            <span className="builder-kicker">Online inference</span>
            <h2>Model services</h2>
            <p>Publish stable prediction endpoints and manage the models behind them.</p>
          </div>
          <div className="catalog-toolbar-actions">
            <button className="secondary-button" type="button" onClick={() => setCatalogMode(catalogMode === "monitoring" ? "services" : "monitoring")}>
              <Activity size={16} /> {catalogMode === "monitoring" ? "Services" : "Monitoring dashboard"}
            </button>
            <button className="primary-button" type="button" onClick={() => setModal("create")}>
              <Plus size={16} /> New service
            </button>
          </div>
        </div>

        {catalogMode === "services" && <div className="serving-guidance" role="note">
          <Rocket size={20} />
          <div><strong>Start with a production model.</strong><span>Create one service, then add challengers, shadows or a fallback from its Overview.</span></div>
        </div>}

        {catalogMode === "monitoring" && <div className="serving-monitoring-dashboard">
          <div className="panel form-panel serving-monitoring-selector">
            <div className="panel-header"><div><span className="builder-kicker">Comparative read model</span><h3>Compare service reports</h3></div><button className="secondary-button compact-button" type="button" onClick={() => void refreshMonitoringRuns()}><RotateCcw size={14} /> Refresh</button></div>
            <p>Select services to compare their latest immutable manual report. Metrics remain tied to their visible window and actuals coverage.</p>
            <div className="serving-monitoring-checkboxes">{deployments.map((deployment) => {
              const selected = selectedComparisonIds.includes(deployment.id);
              return <label key={deployment.id} className={selected ? "selected" : undefined}><input type="checkbox" checked={selected} onChange={() => toggleComparisonService(deployment.id)} /><span><strong>{deployment.name}</strong><small>{deployment.status} · revision v{deployment.active_revision?.version_number ?? "—"}</small></span></label>;
            })}</div>
          </div>
          {monitoringError && <div className="error-banner">{monitoringError}</div>}
          <div className="panel serving-monitoring-comparison">
            <div className="panel-header"><div><span className="builder-kicker">Latest completed or active run</span><h3>Service monitoring</h3></div></div>
            <div className="serving-monitoring-comparison-grid">{comparisonRuns.map(({ deployment, run }) => {
              const scope = run?.report.data_scope as Record<string, unknown> | undefined;
              const health = run?.report.service_health as Record<string, unknown> | undefined;
              const metrics = run ? monitoringMetrics(run) : [];
              const hasActuals = run ? monitoringHasActuals(run) : false;
              return <article key={deployment.id}><div><strong>{deployment.name}</strong><button className="secondary-button compact-button" type="button" onClick={() => { openDeployment(deployment); setActiveTab("monitoring"); }}>Open</button></div>{run ? <><span className={`status-pill ${run.status}`}>{run.status}</span><small>{formatDate(run.since)} — {formatDate(run.until)}</small><div className="serving-monitoring-kpis"><span><strong>{Number(scope?.processed_request_count ?? run.processed_request_count)}</strong><small>requests</small></span><span><strong>{Number(health?.failed_request_count ?? 0)}</strong><small>failed requests</small></span><span><strong>{health?.p95_latency_ms == null ? "—" : `${Math.round(Number(health.p95_latency_ms))} ms`}</strong><small>p95 latency</small></span><span><strong>{Number(scope?.served_prediction_count ?? 0)}</strong><small>served predictions</small></span>{hasActuals && <span><strong>{scope ? `${Math.round(Number(scope.actuals_coverage ?? 0) * 100)}%` : "—"}</strong><small>actuals coverage</small></span>}{metrics.slice(0, 3).map((metric) => <span key={metric.id}><strong>{metric.value == null ? "—" : Number(metric.value).toFixed(3)}</strong><small>{metric.label}</small></span>)}</div>{!hasActuals && run.status === "succeeded" && <div className="serving-inline-warning">Performance not evaluated · actuals not provided</div>}{run.error_message && <p>{run.error_message}</p>}</> : <div className="serving-list-empty"><Activity size={20} /><strong>No report</strong><span>Open the service and run monitoring.</span></div>}</article>;
            })}{!comparisonRuns.length && <div className="serving-list-empty"><Activity size={22} /><strong>Select at least one service</strong><span>Checkboxes control which reports appear in the comparison.</span></div>}</div>
          </div>
        </div>}

        {catalogMode === "services" && deployments.length > 0 && <div className="serving-table-wrap">
          <table className="serving-table">
            <thead><tr><th>Service</th><th>Status</th><th>Champion</th><th>Revision</th><th>Additional roles</th><th className="action-column">Actions</th></tr></thead>
            <tbody>{deployments.map((deployment) => {
              const activeAssignments = deployment.active_revision?.assignments ?? [];
              const activeChampion = activeAssignments.find((item) => item.role === "champion");
              return <tr key={deployment.id}>
                <td><strong>{deployment.name}</strong><code>{deployment.slug}</code></td>
                <td><span className={`status-pill ${deployment.status}`}>{deployment.status}</span></td>
                <td>{modelLabel(activeChampion?.model_id)}</td>
                <td>v{deployment.active_revision?.version_number ?? "—"}</td>
                <td>{activeAssignments.filter((item) => item.role === "challenger").length} challengers · {activeAssignments.filter((item) => item.role === "shadow").length} shadows</td>
                <td className="serving-table-actions"><button className="secondary-button compact-button" type="button" onClick={() => openDeployment(deployment)}>Open</button><button className="secondary-button compact-button danger-button" type="button" onClick={() => { openDeployment(deployment); setLifecycleReason(""); setModal("archive"); }}><Archive size={14} /> Archive</button></td>
              </tr>;
            })}</tbody>
          </table>
        </div>}
          {catalogMode === "services" && !deployments.length && <div className="panel serving-empty-state">
            <Rocket size={28} />
            <h3>No model services yet</h3>
            <p>Create a stable endpoint backed by your first production model.</p>
            <button className="primary-button" type="button" onClick={() => setModal("create")}><Plus size={16} /> Create first service</button>
          </div>}

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
          <button className="secondary-button danger-button" type="button" onClick={() => { setLifecycleReason(""); setModal("archive"); }}><Archive size={16} /> Archive</button>
        </div>
      </div>
      <div className="serving-endpoint-bar"><div><small>Stable production endpoint</small><code>{selectedDeployment.endpoint_url}</code></div><button className="icon-button" type="button" aria-label="Copy endpoint" title="Copy endpoint" onClick={() => navigator.clipboard.writeText(selectedDeployment.endpoint_url ?? "")}><Copy size={16} /></button></div>

      <nav className="serving-tabs" aria-label="Model service sections">
        {([
          ["overview", "Overview", Rocket], ["test", "Test endpoint", Play], ["traffic", "Traffic & audit", Activity], ["monitoring", "Monitoring", SlidersHorizontal], ["access", "API access", KeyRound]
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
          <div className="segmented-control serving-input-mode" aria-label="Test request input mode">
            <button type="button" className={testInputMode === "form" ? "active" : ""} onClick={() => setTestInputMode("form")}>Form</button>
            <button type="button" className={testInputMode === "json" ? "active" : ""} onClick={() => setTestInputMode("json")}>JSON payload</button>
          </div>
          {testInputMode === "form" ? <>
            <label>Record ID <span className="optional-label">recommended</span><input value={recordId} onChange={(event) => setRecordId(event.target.value)} placeholder="e.g. customer-1042" /><small>Needed later to join predictions with actual outcomes.</small></label>
            {contractError && <div className="error-banner">{contractError}</div>}
            {!contractError && !inputContract && <div className="serving-contract-loading">Loading model input contract…</div>}
            {inputContract && <div className="serving-feature-form">
              <div className="serving-contract-summary"><strong>{inputContract.fields.length} required features</strong><small>Generated from model {shortId(inputContract.model_id)} in the active revision.</small></div>
              {inputContract.fields.map((field) => <label key={field.name}>
                <span className="serving-feature-label"><code>{field.name}</code><em>{field.value_type}</em>{field.required && <i>required</i>}</span>
                {field.value_type === "boolean"
                  ? <select value={String(Boolean(featureValues[field.name]))} onChange={(event) => updateFeature(field.name, field.value_type, event.target.value === "true")}><option value="false">false</option><option value="true">true</option></select>
                  : <div className="serving-feature-input-wrap"><input
                        type={field.value_type === "number" || field.value_type === "integer" ? "number" : "text"}
                        step={field.value_type === "integer" ? 1 : field.value_type === "number" ? "any" : undefined}
                        min={field.minimum ?? undefined}
                        max={field.maximum ?? undefined}
                        value={String(featureValues[field.name] ?? "")}
                        onChange={(event) => updateFeature(field.name, field.value_type, event.target.value)}
                      />{field.value_type === "string" && field.options.length > 0 && <div className="serving-category-suggest"><button type="button" className="serving-suggest-trigger">Suggest</button><div className="serving-suggest-popover" role="listbox" aria-label={`Suggested values for ${field.name}`}><small>Top categories in the full training set</small>{field.options.map((option) => <button type="button" role="option" key={String(option)} onClick={() => updateFeature(field.name, field.value_type, String(option))}>{String(option)}</button>)}</div></div>}</div>}
                <small>{field.description}</small>
              </label>)}
              <button className="secondary-button" type="button" onClick={generatePayload}><Copy size={15} /> Generate payload</button>
            </div>}
          </> : <label>Request JSON<textarea className="json-input" value={payloadJson} onChange={(event) => setPayloadJson(event.target.value)} rows={18} /><small>Exact request body. It may contain up to 1,000 instances.</small></label>}
          <div className="button-row"><button className="primary-button" onClick={score} type="button" disabled={busy}>{scorePhase === "scoring" ? <span className="serving-score-button-spinner" aria-hidden="true" /> : <Play size={16} />}{scorePhase === "scoring" ? `Scoring… ${scoreElapsedSeconds}s` : "Send test request"}</button>{scoreTarget !== "champion" && <button className="secondary-button" onClick={() => setModal("replay")} type="button"><History size={16} /> Replay history</button>}</div>
        </div>
        <div className="panel serving-response-panel">
          <div className="panel-header"><div><span className="builder-kicker">Response</span><h3>{scorePhase === "scoring" ? "Scoring request" : scorePhase === "error" ? "Request failed" : scoreResult ? "Prediction returned" : "Waiting for a request"}</h3></div>{scoreResult && <span className="status-pill active">{scoreResult.served_role}</span>}</div>
          {scorePhase === "scoring" ? <div className="serving-response-progress" role="status" aria-live="polite"><span className="serving-score-spinner" aria-hidden="true" /><strong>Running the pinned service revision</strong><p>Validating the input contract, transforming features, scoring the champion and configured shadows, then durably writing the Inference Log.</p><small>{scoreElapsedSeconds ? `${scoreElapsedSeconds}s elapsed` : "Request accepted…"}</small></div>
            : scorePhase === "error" ? <div className="serving-response-error" role="alert"><X size={26} /><strong>Prediction was not returned</strong><p>{scoreError}</p><small>No successful result is shown until the auditable inference record is safely persisted.</small></div>
            : scoreResult ? <pre className="json-output">{JSON.stringify(scoreResult, null, 2)}</pre>
              : <div className="serving-response-empty"><Play size={26} /><p>Your prediction, request ID and warnings will appear here.</p></div>}
        </div>
      </div>}

      {activeTab === "traffic" && <div className="serving-tab-content">
        <div className="serving-section-header"><div><span className="builder-kicker">Full payload retention</span><h3>Inference log</h3><p>Every accepted request and model execution is retained for audit and future monitoring.</p></div><div className="catalog-toolbar-actions"><button className="secondary-button" type="button" onClick={() => void refreshServingActivity(selectedDeployment)} disabled={historyLoading}><RotateCcw className={historyLoading ? "run-spinner" : undefined} size={16} /> {historyLoading ? "Refreshing…" : "Refresh"}</button>{challengers.length > 0 && <button className="secondary-button" type="button" onClick={() => { setScoreTarget(challengers[0].model_id); setModal("replay"); }}><History size={16} /> Replay challenger</button>}</div></div>
        {historyError && <div className="error-banner">{historyError}</div>}
        <div className="panel inference-log-list serving-traffic-list">{history.map((item) => <article key={item.id}><span><strong>{item.status}</strong><small>{formatDate(item.created_at)} · {item.record_count} records</small></span><span><code>{shortId(item.served_model_id || item.champion_model_id)}</code><small>{item.served_role || "champion"}{item.fallback_used ? " · fallback used" : ""}</small></span><span><strong>{item.latency_ms ?? "—"} ms</strong><small>{item.warnings[0] ?? item.error_message}</small></span><button className="secondary-button compact-button" type="button" onClick={() => api.inferenceDetail(selectedDeployment.id, item.id).then((detail) => { setInferenceDetail(detail); setModal("inference"); })}><Eye size={14} /> Details</button></article>)}{!history.length && !historyError && <div className="serving-list-empty"><History size={24} /><strong>No requests recorded yet</strong><span>Use Test endpoint or call the REST API to generate the first auditable request.</span></div>}</div>
        {replays.length > 0 && <div className="serving-replay-section"><h3>Challenger replays</h3><div className="panel inference-log-list">{replays.slice(0, 10).map((item) => <article key={item.id}><span><strong>{item.status}</strong><small>{formatDate(item.created_at)}</small></span><span><code>{shortId(item.challenger_model_id)}</code><small>revision {shortId(item.deployment_revision_id)}</small></span><span><strong>{item.processed_records} records</strong><small>{item.failed_requests} failed request(s)</small></span></article>)}</div></div>}
      </div>}

      {activeTab === "monitoring" && <div className="serving-tab-content serving-monitoring-layout">
        <div className="panel form-panel">
          <div className="panel-header"><div><span className="builder-kicker">Manual full-scope run</span><h3>Generate monitoring report</h3></div><Activity size={18} /></div>
          <p className="serving-section-intro">The platform snapshots every retained public-endpoint execution in the selected scoring-time window. Add immutable actuals to also calculate service and per-model effectiveness.</p>
          <label>Actuals dataset · optional<select value={actualsDatasetId} onChange={(event) => {
            const next = event.target.value;
            setActualsDatasetId(next);
            const attachment = actualsOptions.find((item) => item.dataset.id === next)?.attachment;
            setMonitoringTargetColumn(attachment?.target_column ?? "");
            setMonitoringRecordColumn(attachment?.primary_key_column ?? "");
          }}><option value="">No actuals · operational and distribution metrics only</option>{actualsOptions.map(({ attachment, dataset }) => <option key={dataset.id} value={dataset.id}>{dataset.name} · v{dataset.version_number} · {dataset.row_count ?? "?"} rows{attachment.target_column ? ` · target ${attachment.target_column}` : ""}</option>)}</select><small>Without actuals, performance metrics are explicitly marked as not evaluated. Eligible actuals must be attached to this Business Case with role monitoring_actuals.</small></label>
          {!actualsOptions.length && <div className="serving-inline-warning">No monitoring_actuals dataset is attached. You can still run operational, traffic, input and prediction monitoring.</div>}
          <div className="serving-monitoring-window"><label>Since · scoring time<input type="datetime-local" value={monitoringSince} onChange={(event) => setMonitoringSince(event.target.value)} /></label><label><span className="serving-monitoring-time-label"><span>Until · scoring time</span><button type="button" onClick={() => setMonitoringUntil(monitoringDateInput(new Date()))}>Now</button></span><input type="datetime-local" value={monitoringUntil} onChange={(event) => setMonitoringUntil(event.target.value)} /></label></div>
          <label>Time aggregation<select value={monitoringAggregation} onChange={(event) => setMonitoringAggregation(event.target.value as typeof monitoringAggregation)}><option value="none">No aggregation · one summary for the full window</option><option value="hour">Per hour</option><option value="day">Per day</option><option value="week">Per week</option><option value="month">Per month</option></select><small>Calendar buckets use scored_at and include empty intervals, so the report has one row per selected period.</small></label>
          {actualsDatasetId && <details><summary>Join overrides</summary><label>Actuals record ID column<input value={monitoringRecordColumn} onChange={(event) => setMonitoringRecordColumn(event.target.value)} placeholder="Inferred from attachment" /></label><label>Actuals target column<input value={monitoringTargetColumn} onChange={(event) => setMonitoringTargetColumn(event.target.value)} placeholder="Inferred from attachment or model" /></label><small>Auto join prefers prediction_id, then request_id + record ID, then a unique record ID in this window.</small></details>}
          {monitoringError && <div className="error-banner">{monitoringError}</div>}
          <button className="primary-button" type="button" onClick={() => void runOnlineMonitoring()} disabled={busy || !monitoringSince || !monitoringUntil}><Play size={16} /> {busy ? "Queuing…" : "Run monitoring report"}</button>
        </div>
        <div className="panel serving-monitoring-runs">
          <div className="panel-header"><div><span className="builder-kicker">Immutable history</span><h3>Monitoring reports</h3></div><div className="catalog-toolbar-actions"><button className="secondary-button compact-button" type="button" onClick={() => void archiveMonitoringHistory()} disabled={!monitoringRuns.some((item) => item.deployment_id === selectedDeployment.id && ["succeeded", "failed"].includes(item.status))}><Archive size={14} /> Archive history</button><button className="secondary-button compact-button" type="button" onClick={() => void refreshMonitoringRuns()}><RotateCcw size={14} /> Refresh</button></div></div>
          {monitoringRuns.filter((item) => item.deployment_id === selectedDeployment.id).map((run) => {
            const scope = run.report.data_scope as Record<string, unknown> | undefined;
            const health = run.report.service_health as Record<string, unknown> | undefined;
            const metrics = monitoringMetrics(run);
            const hasActuals = monitoringHasActuals(run);
            const performance = run.report.performance as Record<string, unknown> | undefined;
            const modelsReport = Array.isArray(performance?.models) ? performance.models as Array<Record<string, unknown>> : [];
            const aggregation = run.report.time_aggregation as Record<string, unknown> | undefined;
            const buckets = Array.isArray(aggregation?.buckets) ? aggregation.buckets as Array<Record<string, unknown>> : [];
            return <article key={run.id} className="serving-monitoring-run"><div className="serving-monitoring-run-head"><span><strong>{formatDate(run.since)} — {formatDate(run.until)}</strong><small>run {shortId(run.id)} · scored_at · {run.processed_request_count} requests</small></span><span className="serving-monitoring-run-actions"><span className={`status-pill ${run.status}`}>{run.status}</span>{run.status === "succeeded" && <button className="secondary-button compact-button" type="button" onClick={() => setMonitoringVisualizationRunId(run.id)}><BarChart3 size={14} /> Visualize</button>}{["succeeded", "failed"].includes(run.status) && <button className="secondary-button compact-button" type="button" onClick={() => void archiveMonitoringRun(run.id)}><Archive size={13} /> Archive</button>}</span></div>{run.status === "failed" ? <div className="error-banner">{run.error_message}</div> : run.status !== "succeeded" ? <div className="serving-response-progress"><span className="serving-score-spinner" aria-hidden="true" /><strong>Processing retained inference history</strong><small>Full-scope snapshot and bounded aggregates run asynchronously.</small></div> : <><div className="serving-monitoring-kpis"><span><strong>{Number(scope?.processed_request_count ?? run.processed_request_count)}</strong><small>requests</small></span><span><strong>{Number(health?.record_count ?? 0)}</strong><small>records</small></span><span><strong>{Number(health?.failed_request_count ?? 0)}</strong><small>failed requests</small></span><span><strong>{Number(health?.fallback_request_count ?? 0)}</strong><small>fallback requests</small></span><span><strong>{health?.p95_latency_ms == null ? "—" : `${Math.round(Number(health.p95_latency_ms))} ms`}</strong><small>p95 latency</small></span><span><strong>{Number(scope?.served_prediction_count ?? 0)}</strong><small>served predictions</small></span>{hasActuals && <span><strong>{Math.round(Number(scope?.actuals_coverage ?? 0) * 100)}%</strong><small>actuals coverage</small></span>}{metrics.slice(0, 4).map((metric) => <span key={metric.id}><strong>{metric.value == null ? "—" : Number(metric.value).toFixed(3)}</strong><small>{metric.label}</small></span>)}</div>{buckets.length > 0 && <div className="serving-monitoring-buckets"><div className="serving-monitoring-bucket-toolbar"><strong>{String(aggregation?.granularity)} aggregation · scored_at · UTC</strong></div><div className="serving-monitoring-bucket-table"><div className="serving-monitoring-bucket-head"><span>Period</span><span>Requests</span><span>Failed</span><span>Fallback</span><span>P95 latency</span><span>Served</span></div>{buckets.map((bucket) => <div key={String(bucket.bucket_start)}><span>{String(bucket.label)}</span><span>{Number(bucket.request_count ?? 0)}</span><span>{Number(bucket.failed_request_count ?? 0)}</span><span>{Number(bucket.fallback_request_count ?? 0)}</span><span>{bucket.p95_latency_ms == null ? "—" : `${Math.round(Number(bucket.p95_latency_ms))} ms`}</span><span>{Number(bucket.served_prediction_count ?? 0)}</span></div>)}</div></div>}{!hasActuals && <div className="serving-inline-warning">Performance not evaluated · actuals not provided. Operational, input and prediction monitoring cover the full selected window.</div>}{hasActuals && <div className="serving-monitoring-models"><strong>Model and role results</strong>{modelsReport.map((item) => {
              const evaluation = item.evaluation as Record<string, unknown> | undefined;
              const modelMetrics = Array.isArray(evaluation?.metrics) ? evaluation.metrics as Array<{ id: string; label: string; value: number | null }> : [];
              return <span key={`${item.deployment_revision_id}:${item.model_id}:${item.role}`}><code>{shortId(String(item.model_id))}</code><small>{String(item.role)} · revision {shortId(String(item.deployment_revision_id))} · {Number(item.scored_row_count ?? 0)} rows</small>{modelMetrics[0] && <strong>{modelMetrics[0].label}: {modelMetrics[0].value == null ? "—" : Number(modelMetrics[0].value).toFixed(3)}</strong>}</span>;
            })}</div>}{run.warnings.length > 0 && hasActuals && <div className="serving-inline-warning">{run.warnings[0]}</div>}</>}</article>;
          })}
          {!monitoringRuns.some((item) => item.deployment_id === selectedDeployment.id) && <div className="serving-list-empty"><Activity size={24} /><strong>No monitoring report yet</strong><span>Select a retained scoring-time window to create the first immutable report. Actuals are optional.</span></div>}
        </div>
      </div>}

      {activeTab === "access" && <div className="serving-tab-content serving-access-layout">
        <div className="panel"><div className="panel-header"><div><span className="builder-kicker">REST API</span><h3>Call this service directly</h3></div><ShieldCheck size={18} /></div><p className="serving-section-intro">Authenticate as an existing platform account. Business Case grants still determine access.</p><div className="serving-code-block"><code>POST {selectedDeployment.endpoint_url}</code><button className="icon-button" type="button" onClick={() => navigator.clipboard.writeText(selectedDeployment.endpoint_url ?? "")}><Copy size={15} /></button></div><pre className="json-output serving-code-example">{JSON.stringify({ instances: [{ record_id: "property-1042", features: { area: 84, rooms: 4 } }] }, null, 2)}</pre></div>
        <div className="panel"><div className="panel-header"><div><span className="builder-kicker">Python client</span><h3>Create client credential</h3></div><KeyRound size={18} /></div><p className="serving-section-intro">Create a revocable credential for scripts and notebooks. The secret is displayed only once.</p><button className="primary-button" type="button" onClick={() => { setCredential(""); setModal("credential"); }}><KeyRound size={16} /> Generate credential</button></div>
      </div>}

      {monitoringVisualizationRun && <MonitoringVisualizationModal key={monitoringVisualizationRun.id} run={monitoringVisualizationRun} onClose={() => setMonitoringVisualizationRunId("")} />}

      {modal === "revision" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog serving-revision-dialog" role="dialog" aria-modal="true" aria-labelledby="revision-title"><div className="modal-header"><div><span className="builder-kicker">Immutable configuration</span><h2 id="revision-title">Configure model roles</h2><p>Saving creates and immediately activates a new service revision. Only staging and production models with a compatible inference contract can share traffic.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><div className="serving-role-help"><span><strong>Champion</strong> public traffic</span><span><strong>Challenger</strong> direct tests and replay</span><span><strong>Shadow</strong> copied live traffic</span><span><strong>Fallback</strong> technical failures</span></div>{revisionError && <div className="error-banner" role="alert">{revisionError}</div>}<div className="serving-role-grid">{eligibleModels.map((model) => {
          const option = modelOptions.find((item) => item.model_id === model.id);
          const compatible = !configuredChampionSignature || option?.contract_signature === configuredChampionSignature;
          return <label key={model.id} className={!compatible && roleByModel[model.id] !== "champion" ? "serving-model-incompatible" : ""}><span>{model.name} · {model.version}<small>{model.stage}{!compatible && roleByModel[model.id] !== "champion" ? " · incompatible with selected champion" : ""}</small></span><select value={roleByModel[model.id] ?? ""} onChange={(event) => updateModelRole(model.id, event.target.value as DeploymentRole | "")}><option value="">Not assigned</option><option value="champion" disabled={!option?.allowed_roles.includes("champion")}>Champion</option><option value="challenger" disabled={!compatible || !option?.allowed_roles.includes("challenger")}>Challenger</option><option value="shadow" disabled={!compatible || !option?.allowed_roles.includes("shadow")}>Shadow</option><option value="fallback" disabled={!compatible || !option?.allowed_roles.includes("fallback")}>Fallback</option></select></label>;
        })}</div>{!eligibleModels.length && <div className="serving-inline-warning">No staging or production models are available in this Business Case.</div>}<label>Reason for change<input value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} placeholder="e.g. Add validated challenger v6" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={activateRevision} disabled={busy || !revisionReason.trim()}><GitBranch size={15} /> Activate new revision</button></div></div></div>}

      {modal === "history" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="history-title"><div className="modal-header"><div><span className="builder-kicker">Immutable history</span><h2 id="history-title">Service revisions</h2><p>Rollback copies a historical configuration into a new auditable revision.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><div className="model-version-list">{revisions.map((revision) => <article key={revision.id}><div className="model-version-marker"><span>v{revision.version_number}</span></div><div><strong>Revision v{revision.version_number}</strong><span>{formatDate(revision.created_at)} · {revision.assignments.length} assigned model(s)</span><small>{revision.reason || "No reason recorded"}</small></div>{revision.id === selectedDeployment.active_revision_id ? <i className="pipeline-status published">active</i> : <button className="secondary-button compact-button" type="button" onClick={() => setRollbackRevisionId(revision.id)}>Select rollback</button>}</article>)}</div>{rollbackRevisionId && <label>Rollback reason<input value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} placeholder="Why is this revision being restored?" /></label>}</div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Close</button><button className="primary-button" type="button" onClick={rollbackDeployment} disabled={busy || !rollbackRevisionId || !revisionReason.trim()}><History size={15} /> Roll back</button></div></div></div>}

      {modal === "lifecycle" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="lifecycle-title"><div className="modal-header"><div><span className="builder-kicker">Service lifecycle</span><h2 id="lifecycle-title">{selectedDeployment.status === "running" ? "Stop service" : "Validate and resume service"}</h2><p>{selectedDeployment.status === "running" ? "The endpoint will reject scoring while revision history remains available." : "The active revision will be validated before traffic is accepted."}</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Reason<input value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} placeholder="Reason for this operational change" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={changeDeploymentStatus} disabled={busy || !lifecycleReason.trim()}>{selectedDeployment.status === "running" ? "Stop service" : "Validate & resume"}</button></div></div></div>}

      {modal === "archive" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-title"><div className="modal-header"><div><span className="builder-kicker">Service lifecycle</span><h2 id="archive-title">Archive {selectedDeployment.name}?</h2><p>The endpoint will be permanently disabled and removed from the active list. Revision and inference history will be preserved for audit.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Reason<input autoFocus value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} placeholder="Why is this service being archived?" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button danger-button" type="button" onClick={archiveDeployment} disabled={busy || !lifecycleReason.trim()}><Archive size={16} /> Archive service</button></div></div></div>}

      {modal === "replay" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="replay-title"><div className="modal-header"><div><span className="builder-kicker">Batch evaluation</span><h2 id="replay-title">Replay historical traffic</h2><p>Score up to 1,000 retained requests with a challenger. Production responses are not changed.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Challenger<select value={scoreTarget === "champion" ? "" : scoreTarget} onChange={(event) => setScoreTarget(event.target.value)}><option value="">Choose a challenger</option>{challengers.map((item) => <option key={item.model_id} value={item.model_id}>{modelLabel(item.model_id)}</option>)}</select></label><div className="serving-inline-warning">Replay uses the current immutable revision and retained historical inputs.</div></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={replayChallenger} disabled={busy || scoreTarget === "champion" || !scoreTarget}><History size={16} /> Queue replay</button></div></div></div>}

      {modal === "credential" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="credential-title"><div className="modal-header"><div><span className="builder-kicker">Python client</span><h2 id="credential-title">{credential ? "Copy your credential" : "Generate client credential"}</h2><p>{credential ? "This secret will not be shown again after you close this window." : "The credential inherits your current account and Business Case permissions."}</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body">{credential ? <div className="credential-once"><strong>Copy now — shown once</strong><code>{credential}</code><button className="secondary-button" type="button" onClick={() => navigator.clipboard.writeText(credential)}><Copy size={15} /> Copy credential</button></div> : <div className="serving-credential-explainer"><ShieldCheck size={24} /><p>You can revoke this credential later through the API. Creating it does not bypass platform permissions.</p></div>}</div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>{credential ? "Done" : "Cancel"}</button>{!credential && <button className="primary-button" type="button" onClick={createCredential} disabled={busy}><KeyRound size={16} /> Generate credential</button>}</div></div></div>}

      {modal === "inference" && inferenceDetail && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog serving-inference-dialog" role="dialog" aria-modal="true" aria-labelledby="inference-title"><div className="modal-header"><div><span className="builder-kicker">Audited request</span><h2 id="inference-title">Inference details</h2><p>Stored request, response and per-model executions.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body"><pre className="json-output">{JSON.stringify(inferenceDetail, null, 2)}</pre></div></div></div>}
    </section>
  );
}
