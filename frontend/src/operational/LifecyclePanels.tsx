import { Brain, Database, Download, Eye, GitBranch, History, Play, Plus, Rocket, Search, Share2, SlidersHorizontal, X } from "lucide-react";
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
  const [tab, setTab] = useState<"overview" | "training" | "parameters" | "lineage">("overview");
  const [dataLineage, setDataLineage] = useState<DatasetLineageReference[]>([]);
  const [lineageError, setLineageError] = useState("");
  const weights = model.model_parameters.weights ?? [];
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
          {(["overview", "training", "parameters", "lineage"] as const).map((item) => (
            <button className={tab === item ? "active" : ""} type="button" key={item} onClick={() => setTab(item)}>
              {item}
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
              <KeyValueGrid values={model.metrics} empty="No evaluation metrics recorded." />
            </section>
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
            <KeyValueGrid values={model.training_config} empty="Training configuration was not recorded for this model." />
          </section>
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

export function DatasetLineageList({
  items,
  error,
  onOpenDataset
}: {
  items: DatasetLineageReference[];
  error?: string;
  onOpenDataset?: (datasetId: string) => void;
}) {
  return (
    <section className="model-detail-section">
      <h3><Database size={16} /> Related datasets</h3>
      {error && <div className="error-banner">{error}</div>}
      <div className="dataset-lineage-list">
        {items.map((item) => (
          <article key={item.artifact_id}>
            <div>
              <strong>{item.name} · v{item.version_number}</strong>
              <span>{item.role.replaceAll("_", " ")} · {item.stage} · {item.row_count?.toLocaleString() ?? "—"} rows</span>
              <small>{item.pipeline_step_id ? `step ${item.pipeline_step_id}` : "registered source"}</small>
            </div>
            {onOpenDataset && (
              <button className="secondary-button compact-button" type="button"
                onClick={() => onOpenDataset(item.dataset_id)}>
                <Eye size={14} /> Open dataset
              </button>
            )}
          </article>
        ))}
        {!items.length && !error && <div className="empty-state">No resolved dataset lineage is available.</div>}
      </div>
    </section>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
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
