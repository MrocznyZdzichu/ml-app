import {
  Brain,
  Database,
  Drill,
  ListChecks,
  Rocket,
  Table2
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type {
  BusinessCase,
  DataAsset,
  Deployment,
  ModelArtifact,
  Pipeline
} from "../api/client";

export function Overview({
  businessCases,
  datasets,
  pipelines,
  models,
  deployments
}: {
  businessCases: BusinessCase[];
  datasets: DataAsset[];
  pipelines: Pipeline[];
  models: ModelArtifact[];
  deployments: Deployment[];
}) {
  const activeDataAssets = datasets.filter((dataset) => dataset.status !== "deleted");
  const dataViews = activeDataAssets.filter((dataset) => dataset.source_type === "view");
  const sourceDatasets = activeDataAssets.filter((dataset) => dataset.source_type !== "view");
  const recentAssets = [
    ...businessCases.map((item) => ({
      id: item.id,
      name: item.name,
      kind: "business case",
      status: item.status
    })),
    ...pipelines.map((item) => ({
      id: item.id,
      name: item.name,
      kind: "pipeline",
      status: item.status
    })),
    ...sourceDatasets.map((item) => ({
      id: item.id,
      name: item.name,
      kind: "dataset",
      status: item.status
    })),
    ...dataViews.map((item) => ({
      id: item.id,
      name: item.name,
      kind: "view",
      status: item.status
    })),
    ...models.map((item) => ({
      id: item.id,
      name: item.name,
      kind: "model",
      status: item.stage
    })),
    ...deployments.map((item) => ({
      id: item.id,
      name: item.name,
      kind: "deployment",
      status: item.status
    }))
  ];

  return (
    <section className="overview-grid">
      <Metric icon={ListChecks} label="Business Cases" value={businessCases.length} tone="teal" />
      <Metric icon={Database} label="Datasets" value={sourceDatasets.length} tone="teal" />
      <Metric icon={Table2} label="Data Views" value={dataViews.length} tone="blue" />
      <Metric icon={Drill} label="Pipelines" value={pipelines.length} tone="amber" />
      <Metric icon={Brain} label="Models" value={models.length} tone="blue" />
      <Metric icon={Rocket} label="Deployments" value={deployments.length} tone="amber" />
      <div className="panel wide">
        <div className="panel-header">
          <h2>Recent assets</h2>
        </div>
        <div className="table">
          <div className="table-row table-head">
            <span>Name</span>
            <span>Kind</span>
            <span>Status</span>
          </div>
          {recentAssets.slice(0, 8).map((item) => (
            <div className="table-row" key={item.id}>
              <span>{item.name}</span>
              <span>{item.kind}</span>
              <span>{item.status}</span>
            </div>
          ))}
          {recentAssets.length === 0 && (
            <div className="empty-state">No assets yet</div>
          )}
        </div>
      </div>
    </section>
  );
}

export function Metric({
  icon: Icon,
  label,
  value,
  tone
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  tone: string;
}) {
  return (
    <div className={`metric ${tone}`}>
      <Icon size={20} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
