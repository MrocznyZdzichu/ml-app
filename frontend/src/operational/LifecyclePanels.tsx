import { Brain, Download, Play, Plus, Rocket, Share2 } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";

import { api } from "../api/client";
import type {
  DataAsset,
  Deployment,
  ModelArtifact,
  ScoreResponse
} from "../api/client";
import { AssetList } from "../components/AssetList";

type NoticeSetter = (message: string) => void;

export function ModelsPanel({
  datasets,
  models,
  onRefresh,
  setNotice
}: {
  datasets: DataAsset[];
  models: ModelArtifact[];
  onRefresh: () => Promise<void>;
  setNotice: NoticeSetter;
}) {
  const [datasetId, setDatasetId] = useState("");
  const [target, setTarget] = useState("churn");
  const [algorithm, setAlgorithm] = useState("random_forest");

  async function submit(event: FormEvent) {
    event.preventDefault();
    await api.trainModel({
      dataset_id: datasetId || datasets[0]?.id || "demo-dataset",
      target_column: target,
      algorithm,
      feature_columns: []
    });
    setNotice("Training job queued");
    await onRefresh();
  }

  return (
    <section className="two-column">
      <form className="panel form-panel" onSubmit={submit}>
        <div className="panel-header">
          <h2>Train model</h2>
          <Brain size={18} />
        </div>
        <label>
          Dataset
          <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
            <option value="">Demo dataset</option>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Target
          <input value={target} onChange={(event) => setTarget(event.target.value)} />
        </label>
        <label>
          Algorithm
          <select value={algorithm} onChange={(event) => setAlgorithm(event.target.value)}>
            <option value="random_forest">Random forest</option>
            <option value="xgboost">XGBoost</option>
            <option value="logistic_regression">Logistic regression</option>
          </select>
        </label>
        <button className="primary-button" type="submit">
          <Play size={16} />
          Train
        </button>
      </form>

      <AssetList title="Model registry" assets={models.map((item) => ({
        id: item.id,
        name: item.name,
        meta: `${item.algorithm} / ${item.version}`,
        status: item.stage
      }))} />
    </section>
  );
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
