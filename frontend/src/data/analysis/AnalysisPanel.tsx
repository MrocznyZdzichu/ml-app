import { Activity, BarChart3, ListChecks, Table2 } from "lucide-react";
import { lazy, useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import type { BusinessCase, DataAsset, Pipeline } from "../../api/client";
import {
  ArtifactFilters,
  datasetPipelineId,
  isUploadedDataset,
  pipelineMatches
} from "../../components/ArtifactFilters";
import { DeferredPanel } from "../../components/DeferredPanel";
import { PagedCatalogSelect } from "../../components/PagedCatalogSelect";
import type { VisualizationDrillRequest } from "../../analysis/drillContext";
import { datasetVersionGroups } from "../catalog/DatasetCatalogPanel";
import type { DescriptiveProfileCacheEntry } from "../profile/contracts";
import { DataRolesPanel } from "../roles/DataRolesPanel";

const DataBrowsingPanel = lazy(() =>
  import("../browser/DataBrowsingPanel").then((module) => ({
    default: module.DataBrowsingPanel
  }))
);
const DescriptiveAnalysisPanel = lazy(() =>
  import("../profile/DescriptiveAnalysisPanel").then((module) => ({
    default: module.DescriptiveAnalysisPanel
  }))
);
const VisualizationDashboard = lazy(() =>
  import("../../analysis/VisualizationDashboard").then((module) => ({
    default: module.VisualizationDashboard
  }))
);


export function AnalysisPanel({
  datasets,
  businessCases = [],
  pipelines = [],
  descriptiveProfileCache,
  onRefresh,
  setNotice,
  initialDatasetId = "",
  initialTab = "roles",
  onInitialDatasetConsumed,
  showDataRoles = true,
  allowPersistence = true
}: {
  datasets: DataAsset[];
  businessCases?: BusinessCase[];
  pipelines?: Pipeline[];
  descriptiveProfileCache: Map<string, DescriptiveProfileCacheEntry>;
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
  initialDatasetId?: string;
  initialTab?: "roles" | "browse" | "descriptive" | "visualization";
  onInitialDatasetConsumed?: () => void;
  showDataRoles?: boolean;
  allowPersistence?: boolean;
}) {
  const [activeAnalysisTab, setActiveAnalysisTab] = useState<"roles" | "browse" | "descriptive" | "visualization">(initialTab);
  const [datasetId, setDatasetId] = useState(initialDatasetId);
  const [businessCaseFilter, setBusinessCaseFilter] = useState("");
  const [showOnlyLatest, setShowOnlyLatest] = useState(true);
  const [purposeFilter, setPurposeFilter] = useState("");
  const [pipelineFilter, setPipelineFilter] = useState("");
  const [uploadedOnly, setUploadedOnly] = useState(false);
  const [pagedAnalysisDatasets, setPagedAnalysisDatasets] = useState<DataAsset[]>([]);
  const [analysisDatasetTotal, setAnalysisDatasetTotal] = useState(0);
  const [selectedAnalysisDataset, setSelectedAnalysisDataset] = useState<DataAsset | undefined>(
    datasets.find((item) => item.id === initialDatasetId)
  );
  const [visualizationDrill, setVisualizationDrill] = useState<VisualizationDrillRequest | null>(null);
  const legacyAvailableDatasets = useMemo(() => {
    const active = datasets.filter((dataset) => dataset.status !== "deleted");
    const scoped = active.filter((dataset) => {
      if (uploadedOnly) return isUploadedDataset(dataset);
      return pipelineMatches(datasetPipelineId(dataset), pipelines, purposeFilter, pipelineFilter);
    });
    return showOnlyLatest
      ? datasetVersionGroups(scoped).map((group) => group.latest)
      : scoped.sort((left, right) =>
          left.name.localeCompare(right.name) || right.version_number - left.version_number
        );
  }, [
    datasets,
    pipelineFilter,
    pipelines,
    purposeFilter,
    showOnlyLatest,
    uploadedOnly
  ]);
  const availableDatasets = useMemo(() => {
    if (!allowPersistence) return legacyAvailableDatasets;
    const selected = selectedAnalysisDataset
      ?? datasets.find((item) => item.id === datasetId);
    return selected && !pagedAnalysisDatasets.some((item) => item.id === selected.id)
      ? [selected, ...pagedAnalysisDatasets]
      : pagedAnalysisDatasets;
  }, [
    allowPersistence,
    datasetId,
    datasets,
    legacyAvailableDatasets,
    pagedAnalysisDatasets,
    selectedAnalysisDataset
  ]);
  const analysisPipelines = businessCaseFilter
    ? pipelines.filter((pipeline) => pipeline.business_case_id === businessCaseFilter)
    : pipelines;

  useEffect(() => {
    const nextDatasetId = availableDatasets.some((dataset) => dataset.id === datasetId)
      ? datasetId
      : availableDatasets[0]?.id ?? "";
    if (nextDatasetId !== datasetId) {
      setDatasetId(nextDatasetId);
      setSelectedAnalysisDataset(
        availableDatasets.find((dataset) => dataset.id === nextDatasetId)
      );
    }
  }, [availableDatasets, datasetId]);

  useEffect(() => {
    if (!initialDatasetId || !availableDatasets.some((dataset) => dataset.id === initialDatasetId)) {
      return;
    }
    if (initialDatasetId !== datasetId) {
      setDatasetId(initialDatasetId);
      setVisualizationDrill(null);
    }
    onInitialDatasetConsumed?.();
  }, [availableDatasets, datasetId, initialDatasetId, onInitialDatasetConsumed]);

  return (
    <section className="analysis-workspace">
      {allowPersistence && (
        <div className="panel analysis-dataset-filters">
          <label>
            <span>Dataset</span>
            <PagedCatalogSelect
              value={datasetId}
              selectedItem={selectedAnalysisDataset}
              onChange={(value, item) => {
                setDatasetId(value);
                setSelectedAnalysisDataset(item);
                setVisualizationDrill(null);
              }}
              loadPage={(query) => api.pageDatasets({
                ...query,
                business_case_id: businessCaseFilter,
                families: showOnlyLatest,
                include_deleted: false,
                summary: true,
                pipeline_id: pipelineFilter,
                pipeline_type: purposeFilter,
                uploaded_only: uploadedOnly
              })}
              onPageLoaded={(page) => {
                setPagedAnalysisDatasets(page.items);
                setAnalysisDatasetTotal(page.total);
              }}
              getId={(item) => item.id}
              getLabel={(item) => `${item.name} · v${item.version_number}`}
              emptyLabel="Choose dataset"
              searchPlaceholder="Search datasets"
              reloadKey={[
                businessCaseFilter,
                showOnlyLatest,
                pipelineFilter,
                purposeFilter,
                uploadedOnly
              ].join(":")}
            />
          </label>
          <label>
            <span>Business Case</span>
            <PagedCatalogSelect
              value={businessCaseFilter}
              onChange={(value) => {
                setBusinessCaseFilter(value);
                setPipelineFilter("");
              }}
              loadPage={api.pageBusinessCases}
              getId={(item) => item.id}
              getLabel={(item) => item.name}
              emptyLabel="All Business Cases"
              searchPlaceholder="Search Business Cases"
            />
          </label>
          <label className="analysis-latest-toggle">
            <input type="checkbox" checked={showOnlyLatest}
              onChange={(event) => setShowOnlyLatest(event.target.checked)} />
            <span><strong>Show only latest versions</strong>
              <small>Collapse each logical dataset family to its newest version.</small></span>
          </label>
          <ArtifactFilters
            pipelines={analysisPipelines}
            purpose={purposeFilter}
            pipelineId={pipelineFilter}
            onPurposeChange={setPurposeFilter}
            onPipelineChange={setPipelineFilter}
            businessCaseId={businessCaseFilter}
            uploadedOnly={uploadedOnly}
            onUploadedOnlyChange={(value) => {
              setUploadedOnly(value);
              if (value) {
                setPurposeFilter("");
                setPipelineFilter("");
              }
            }}
          />
          <span>{analysisDatasetTotal} datasets available</span>
        </div>
      )}
      <div className="analysis-tabs" role="tablist" aria-label="Analysis sections">
        {showDataRoles && (
          <button
            className={activeAnalysisTab === "roles" ? "active" : ""}
            onClick={() => setActiveAnalysisTab("roles")}
            type="button"
          >
            <ListChecks size={16} />
            Data Roles
          </button>
        )}
        <button
          className={activeAnalysisTab === "browse" ? "active" : ""}
          onClick={() => setActiveAnalysisTab("browse")}
          type="button"
        >
          <Table2 size={16} />
          Data Browsing
        </button>
        <button
          className={activeAnalysisTab === "descriptive" ? "active" : ""}
          onClick={() => setActiveAnalysisTab("descriptive")}
          type="button"
        >
          <BarChart3 size={16} />
          Descriptive Analysis
        </button>
        <button
          className={activeAnalysisTab === "visualization" ? "active" : ""}
          onClick={() => setActiveAnalysisTab("visualization")}
          type="button"
        >
          <Activity size={16} />
          Visualization and Trends
        </button>
      </div>

      {activeAnalysisTab === "roles" && (
        <DataRolesPanel
          datasets={availableDatasets}
          datasetId={datasetId}
          setDatasetId={setDatasetId}
          onRefresh={onRefresh}
          setNotice={setNotice}
        />
      )}
      {activeAnalysisTab === "browse" && (
        <DeferredPanel>
          <DataBrowsingPanel
            datasets={availableDatasets}
            datasetId={datasetId}
            setDatasetId={setDatasetId}
            onRefresh={onRefresh}
            setNotice={setNotice}
            visualizationDrill={visualizationDrill}
            onVisualizationDrillConsumed={(requestId) => {
              setVisualizationDrill((current) => current?.id === requestId ? null : current);
            }}
            allowPersistence={allowPersistence}
          />
        </DeferredPanel>
      )}
      {activeAnalysisTab === "descriptive" && (
        <DeferredPanel>
          <DescriptiveAnalysisPanel
            datasets={availableDatasets}
            datasetId={datasetId}
            profileCache={descriptiveProfileCache}
            setDatasetId={setDatasetId}
            setNotice={setNotice}
          />
        </DeferredPanel>
      )}
      {activeAnalysisTab === "visualization" && (
        <DeferredPanel>
          <VisualizationDashboard
            datasets={availableDatasets}
            datasetId={datasetId}
            setDatasetId={setDatasetId}
            setNotice={setNotice}
            onDrill={(request) => {
              setDatasetId(request.datasetId);
              setVisualizationDrill(request);
              setActiveAnalysisTab("browse");
            }}
          />
        </DeferredPanel>
      )}
    </section>
  );
}
