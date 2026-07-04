import {
  Activity,
  BarChart3,
  Brain,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Copy,
  Database,
  Drill,
  Filter,
  History,
  ListChecks,
  LogOut,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Rocket,
  Search,
  Share2,
  Save,
  Table2,
  Trash2,
  Upload,
  X
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ChangeEvent, FormEvent, KeyboardEvent } from "react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { api, getAccessToken, setAccessToken, temporaryPipelineOutputId } from "./api/client";
import type {
  BusinessCase,
  BusinessCaseDataAttachment,
  DataAsset,
  DatasetPreview,
  Deployment,
  ModelArtifact,
  Pipeline,
  PipelineRun,
  PipelineStepRun,
  PipelineVersion,
  ScoringReport,
  UserProfile
} from "./api/client";
import { AssetList } from "./components/AssetList";
import { AuthScreen } from "./workspace/AuthScreen";
import { Metric, Overview } from "./workspace/Overview";
import {
  columnRoleOptions,
  datasetRoleOptions,
  defaultColumnRole,
  emptyRolesMetadata,
  normalizeRolesMetadata,
  readRolesMetadata
} from "./analysis/dataRoles";
import type { DataRolesMetadata } from "./analysis/dataRoles";
import {
  browserFiltersFromVisualizationDrill,
  type BrowserFilterConfig,
  type VisualizationDrillRequest,
} from "./analysis/drillContext";
import {
  canonicalizeWorkflowDatasetIds,
  emptyWorkflowDefinition,
  normalizeWorkflowDefinition
} from "./pipelines/workflowContract";
import type { WorkflowDefinition } from "./pipelines/workflowContract";
import {
  browsableDryRunOutputs,
  DryRunPreview,
  PipelineVersionHistoryDialog,
  PipelineRunDetailsDialog,
  PipelineRunHistoryDialog
} from "./pipelines/PipelineRunDialogs";
import {
  clearPipelineWorkingDraft,
  readPipelineWorkingDraft,
  writePipelineWorkingDraft
} from "./pipelines/pipelineDraftStorage";

type TabId = "overview" | "business-cases" | "data" | "analysis" | "pipelines" | "models" | "scoring-reports" | "serving" | "share";

type NavItem = {
  id: TabId;
  label: string;
  icon: LucideIcon;
};

const navItems: NavItem[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "business-cases", label: "Business Cases", icon: ListChecks },
  { id: "data", label: "Data", icon: Database },
  { id: "analysis", label: "Analysis", icon: BarChart3 },
  { id: "pipelines", label: "Pipelines", icon: Drill },
  { id: "models", label: "Models", icon: Brain },
  { id: "scoring-reports", label: "Scoring Reports", icon: BarChart3 },
  { id: "serving", label: "Serving", icon: Rocket },
  { id: "share", label: "Share", icon: Share2 }
];

const ModelsPanel = lazy(() =>
  import("./operational/LifecyclePanels").then((module) => ({ default: module.ModelsPanel }))
);
const ModelDetailsDialog = lazy(() =>
  import("./operational/LifecyclePanels").then((module) => ({ default: module.ModelDetailsDialog }))
);
const ModelVersionHistoryDialog = lazy(() =>
  import("./operational/LifecyclePanels").then((module) => ({ default: module.ModelVersionHistoryDialog }))
);
const ScoringReportsPanel = lazy(() =>
  import("./operational/ScoringReportsPanel").then((module) => ({ default: module.ScoringReportsPanel }))
);
const ScoringReportDialog = lazy(() =>
  import("./operational/ScoringReportsPanel").then((module) => ({ default: module.ScoringReportDialog }))
);
const ScoringReportHistoryDialog = lazy(() =>
  import("./operational/ScoringReportsPanel").then((module) => ({ default: module.ScoringReportHistoryDialog }))
);
const ServingPanel = lazy(() =>
  import("./operational/LifecyclePanels").then((module) => ({ default: module.ServingPanel }))
);
const SharePanel = lazy(() =>
  import("./operational/LifecyclePanels").then((module) => ({ default: module.SharePanel }))
);
const VisualizationDashboard = lazy(() =>
  import("./analysis/VisualizationDashboard").then((module) => ({
    default: module.VisualizationDashboard
  }))
);
const TimeSeriesWorkbench = lazy(() =>
  import("./analysis/TimeSeriesWorkbench").then((module) => ({
    default: module.TimeSeriesWorkbench
  }))
);
const WorkflowEditor = lazy(() =>
  import("./pipelines/WorkflowEditor").then((module) => ({
    default: module.WorkflowEditor
  }))
);

function DeferredPanel({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="panel"><div className="empty-state">Loading workspace</div></div>}>
      {children}
    </Suspense>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [pipelineOpenRequest, setPipelineOpenRequest] = useState<{
    pipelineId: string;
    requestId: number;
  } | null>(null);
  const [analysisOpenRequest, setAnalysisOpenRequest] = useState<{
    datasetId: string;
    requestId: number;
  } | null>(null);
  const [modelBusinessCaseFilter, setModelBusinessCaseFilter] = useState("");
  const [reportBusinessCaseFilter, setReportBusinessCaseFilter] = useState("");
  const [apiStatus, setApiStatus] = useState("checking");
  const [authStatus, setAuthStatus] = useState(getAccessToken() ? "checking" : "anonymous");
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [businessCases, setBusinessCases] = useState<BusinessCase[]>([]);
  const [datasets, setDatasets] = useState<DataAsset[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [models, setModels] = useState<ModelArtifact[]>([]);
  const [scoringReports, setScoringReports] = useState<ScoringReport[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [notice, setNotice] = useState("Workspace ready");
  const descriptiveProfileCache = useRef<Map<string, DescriptiveProfileCacheEntry>>(new Map());

  const activeConfig = useMemo(
    () => navItems.find((item) => item.id === activeTab) ?? navItems[0],
    [activeTab]
  );

  async function refreshWorkspace() {
    try {
      const [businessCaseItems, datasetItems, pipelineItems, modelItems, reportItems, deploymentItems] = await Promise.all([
        api.listBusinessCases(),
        api.listDatasets(),
        api.listPipelines(),
        api.listModels(),
        api.listScoringReports(),
        api.listDeployments()
      ]);
      setBusinessCases(businessCaseItems);
      setDatasets(datasetItems);
      setPipelines(pipelineItems);
      setModels(modelItems);
      setScoringReports(reportItems);
      setDeployments(deploymentItems);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "API request failed");
    }
  }

  useEffect(() => {
    api
      .health()
      .then(() => setApiStatus("online"))
      .catch(() => setApiStatus("offline"));
  }, []);

  useEffect(() => {
    if (!getAccessToken()) {
      setAuthStatus("anonymous");
      return;
    }

    api
      .me()
      .then((profile) => {
        setCurrentUser(profile);
        setAuthStatus("authenticated");
      })
      .catch(() => {
        setAccessToken(null);
        setCurrentUser(null);
        setAuthStatus("anonymous");
      });
  }, []);

  useEffect(() => {
    if (authStatus === "authenticated") {
      void refreshWorkspace();
    }
  }, [authStatus]);

  async function authenticate(token: string) {
    descriptiveProfileCache.current.clear();
    setAccessToken(token);
    const profile = await api.me();
    setCurrentUser(profile);
    setAuthStatus("authenticated");
    setNotice(`Signed in as ${profile.display_name}`);
  }

  function logout() {
    descriptiveProfileCache.current.clear();
    setAccessToken(null);
    setCurrentUser(null);
    setBusinessCases([]);
    setDatasets([]);
    setPipelines([]);
    setModels([]);
    setScoringReports([]);
    setDeployments([]);
    setAuthStatus("anonymous");
    setNotice("Signed out");
  }

  function openPipelineEditor(pipelineId: string) {
    setPipelineOpenRequest({ pipelineId, requestId: Date.now() });
    setActiveTab("pipelines");
  }

  function openDatasetAnalysis(datasetId: string) {
    setAnalysisOpenRequest({ datasetId, requestId: Date.now() });
    setActiveTab("analysis");
  }

  function openBusinessCaseModels(businessCaseId: string) {
    setModelBusinessCaseFilter(businessCaseId);
    setActiveTab("models");
  }

  function openBusinessCaseScoringReports(businessCaseId: string) {
    setReportBusinessCaseFilter(businessCaseId);
    setActiveTab("scoring-reports");
  }

  if (authStatus !== "authenticated" || !currentUser) {
    return (
      <AuthScreen
        apiStatus={apiStatus}
        isChecking={authStatus === "checking"}
        onAuthenticated={authenticate}
      />
    );
  }

  const ActiveIcon = activeConfig.icon;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">ML</div>
          <div>
            <strong>ML App</strong>
            <span>Analytics platform</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={item.id === activeTab ? "nav-item active" : "nav-item"}
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                type="button"
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Workspace</p>
            <h1>
              <ActiveIcon size={24} />
              {activeConfig.label}
            </h1>
          </div>
          <div className={`status-pill ${apiStatus}`}>
            {apiStatus === "online" ? <CheckCircle2 size={16} /> : <Activity size={16} />}
            <span>API {apiStatus}</span>
          </div>
          <div className="user-menu">
            <div>
              <strong>{currentUser.display_name}</strong>
              <span>{currentUser.email}</span>
            </div>
            <button className="icon-button" onClick={logout} type="button" aria-label="Sign out">
              <LogOut size={18} />
            </button>
          </div>
        </header>

        <div className="notice">{notice}</div>

        {activeTab === "overview" && (
          <Overview
            businessCases={businessCases}
            datasets={datasets}
            pipelines={pipelines}
            models={models}
            deployments={deployments}
          />
        )}
        {activeTab === "business-cases" && (
          <BusinessCasesPanel
            businessCases={businessCases}
            datasets={datasets}
            pipelines={pipelines}
            models={models}
            scoringReports={scoringReports}
            onRefresh={refreshWorkspace}
            onEditPipeline={openPipelineEditor}
            onOpenModels={openBusinessCaseModels}
            onOpenScoringReports={openBusinessCaseScoringReports}
            onOpenDataset={openDatasetAnalysis}
            setNotice={setNotice}
          />
        )}
        {activeTab === "data" && (
          <DataPanel
            datasets={datasets}
            onAnalyze={openDatasetAnalysis}
            onRefresh={refreshWorkspace}
            setNotice={setNotice}
          />
        )}
        {activeTab === "analysis" && (
          <AnalysisPanel
            datasets={datasets}
            businessCases={businessCases}
            descriptiveProfileCache={descriptiveProfileCache.current}
            initialDatasetId={analysisOpenRequest?.datasetId}
            initialTab={analysisOpenRequest ? "browse" : "roles"}
            onInitialDatasetConsumed={() => setAnalysisOpenRequest(null)}
            onRefresh={refreshWorkspace}
            setNotice={setNotice}
          />
        )}
        {activeTab === "pipelines" && (
          <PipelinesPanel
            businessCases={businessCases}
            datasets={datasets}
            pipelines={pipelines}
            openRequest={pipelineOpenRequest}
            onOpenRequestConsumed={() => setPipelineOpenRequest(null)}
            onRefresh={refreshWorkspace}
            onExamineDataset={openDatasetAnalysis}
            setNotice={setNotice}
          />
        )}
        {activeTab === "models" && (
          <DeferredPanel>
            <ModelsPanel
              models={models}
              businessCases={businessCases}
              pipelines={pipelines}
              initialBusinessCaseId={modelBusinessCaseFilter}
              onOpenDataset={openDatasetAnalysis}
            />
          </DeferredPanel>
        )}
        {activeTab === "scoring-reports" && (
          <DeferredPanel>
            <ScoringReportsPanel
              reports={scoringReports}
              businessCases={businessCases}
              pipelines={pipelines}
              initialBusinessCaseId={reportBusinessCaseFilter}
              onOpenDataset={openDatasetAnalysis}
            />
          </DeferredPanel>
        )}
        {activeTab === "serving" && (
          <DeferredPanel>
            <ServingPanel
              deployments={deployments}
              models={models}
              onRefresh={refreshWorkspace}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
        {activeTab === "share" && (
          <DeferredPanel>
            <SharePanel
              datasets={datasets}
              models={models}
              deployments={deployments}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
      </main>
    </div>
  );
}

function BusinessCasesPanel({
  businessCases,
  datasets,
  pipelines,
  models,
  scoringReports,
  onRefresh,
  onEditPipeline,
  onOpenModels,
  onOpenScoringReports,
  onOpenDataset,
  setNotice
}: {
  businessCases: BusinessCase[];
  datasets: DataAsset[];
  pipelines: Pipeline[];
  models: ModelArtifact[];
  scoringReports: ScoringReport[];
  onRefresh: () => Promise<void>;
  onEditPipeline: (pipelineId: string) => void;
  onOpenModels: (businessCaseId: string) => void;
  onOpenScoringReports: (businessCaseId: string) => void;
  onOpenDataset: (datasetId: string) => void;
  setNotice: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [problemType, setProblemType] = useState("binary_classification");
  const [targetColumn, setTargetColumn] = useState("");
  const [primaryMetric, setPrimaryMetric] = useState("f1");
  const [businessGoal, setBusinessGoal] = useState("");
  const [successCriteria, setSuccessCriteria] = useState("");
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editProblemType, setEditProblemType] = useState("custom");
  const [editStatus, setEditStatus] = useState("draft");
  const [editBusinessOwner, setEditBusinessOwner] = useState("");
  const [editTargetColumn, setEditTargetColumn] = useState("");
  const [editPrimaryMetric, setEditPrimaryMetric] = useState("");
  const [editBusinessGoal, setEditBusinessGoal] = useState("");
  const [editSuccessCriteria, setEditSuccessCriteria] = useState("");
  const [selectedBusinessCaseId, setSelectedBusinessCaseId] = useState("");
  const [selectedDataAssetId, setSelectedDataAssetId] = useState("");
  const [selectedRole, setSelectedRole] = useState("training");
  const [contextNote, setContextNote] = useState("");
  const [primaryKeyColumn, setPrimaryKeyColumn] = useState("");
  const [mappingTargetColumn, setMappingTargetColumn] = useState("");
  const [attachments, setAttachments] = useState<BusinessCaseDataAttachment[]>([]);
  const [businessCaseSearch, setBusinessCaseSearch] = useState("");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isMappingFormOpen, setIsMappingFormOpen] = useState(false);
  const [editingAttachmentId, setEditingAttachmentId] = useState("");
  const [activeWorkspace, setActiveWorkspace] = useState<"details" | "data" | "pipelines" | "models" | "reports" | null>(null);
  const [selectedBcModel, setSelectedBcModel] = useState<ModelArtifact | null>(null);
  const [selectedBcReport, setSelectedBcReport] = useState<ScoringReport | null>(null);
  const [bcModelHistory, setBcModelHistory] = useState<ModelArtifact | null>(null);
  const [bcReportHistory, setBcReportHistory] = useState<ScoringReport | null>(null);
  const [bcDatasetHistory, setBcDatasetHistory] = useState<DataAsset | null>(null);
  const [bcPipelineHistory, setBcPipelineHistory] = useState<Pipeline | null>(null);
  const [bcRunDialog, setBcRunDialog] = useState<{
    pipeline: Pipeline;
    version: PipelineVersion;
    inputs: Array<{
      key: string;
      name: string;
      logicalId: string;
      policy: "latest" | "select_at_run";
    }>;
  } | null>(null);
  const [bcRunSelections, setBcRunSelections] = useState<Record<string, string>>({});
  const [bcRunResult, setBcRunResult] = useState<PipelineRun | null>(null);
  const [bcRunSubmitting, setBcRunSubmitting] = useState(false);

  const selectedBusinessCase = businessCases.find((item) => item.id === selectedBusinessCaseId);
  const datasetById = new Map(datasets.map((dataset) => [dataset.id, dataset]));
  const availableDataAssets = datasetVersionGroups(
    datasets.filter((dataset) => dataset.status !== "deleted")
  ).map((group) => group.latest);
  const attachedDataset = (dataAssetId: string) => {
    const attachedVersion = datasetById.get(dataAssetId);
    if (!attachedVersion) return undefined;
    return datasetVersionGroups(
      datasets.filter(
        (dataset) => dataset.logical_id === attachedVersion.logical_id && dataset.status !== "deleted"
      )
    )[0]?.latest ?? attachedVersion;
  };
  const activeAttachments = attachments.filter((attachment) => attachedDataset(attachment.data_asset_id)?.status !== "deleted");
  const deletedAttachments = attachments.filter((attachment) => attachedDataset(attachment.data_asset_id)?.status === "deleted");
  const selectedBusinessCasePipelines = selectedBusinessCase
    ? pipelines.filter((pipeline) => pipeline.business_case_id === selectedBusinessCase.id)
    : [];
  const selectedBusinessCaseModels = latestModelFamilies(
    models.filter((model) => model.business_case_id === selectedBusinessCase?.id)
  );
  const selectedBusinessCaseReports = latestReportFamilies(
    scoringReports.filter((report) => report.business_case_id === selectedBusinessCase?.id)
  );
  const filteredBusinessCases = useMemo(() => {
    const query = businessCaseSearch.trim().toLowerCase();
    if (!query) {
      return businessCases;
    }
    return businessCases.filter((item) => [
      item.name,
      item.description,
      item.problem_type,
      item.status,
      item.primary_metric,
      item.target_column
    ].some((value) => String(value ?? "").toLowerCase().includes(query)));
  }, [businessCases, businessCaseSearch]);

  useEffect(() => {
    if (!selectedBusinessCase) {
      setAttachments([]);
      return;
    }
    resetBusinessCaseEditForm(selectedBusinessCase);
    resetDataMappingForm();
    api
      .listBusinessCaseDataAttachments(selectedBusinessCase.id)
      .then(setAttachments)
      .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load BC data attachments"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBusinessCase, setNotice]);

  async function submitBusinessCase(event: FormEvent) {
    event.preventDefault();
    const created = await api.createBusinessCase({
      name,
      description,
      problem_type: problemType,
      target_column: targetColumn,
      primary_metric: primaryMetric,
      business_goal: businessGoal,
      success_criteria: successCriteria
    });
    setNotice(`Business case created: ${created.name}`);
    setSelectedBusinessCaseId(created.id);
    setName("");
    setDescription("");
    setTargetColumn("");
    setBusinessGoal("");
    setSuccessCriteria("");
    setIsCreateOpen(false);
    setActiveWorkspace("details");
    await onRefresh();
  }

  async function submitBusinessCaseUpdate(event: FormEvent) {
    event.preventDefault();
    if (!selectedBusinessCase) {
      setNotice("Select a business case first");
      return;
    }
    const updated = await api.updateBusinessCase(selectedBusinessCase.id, {
      name: editName,
      description: editDescription,
      problem_type: editProblemType,
      status: editStatus,
      business_owner: editBusinessOwner,
      target_column: editTargetColumn,
      primary_metric: editPrimaryMetric,
      business_goal: editBusinessGoal,
      success_criteria: editSuccessCriteria
    });
    setNotice(`Business case updated: ${updated.name}`);
    await onRefresh();
  }

  async function attachData(event: FormEvent) {
    event.preventDefault();
    if (!selectedBusinessCase) {
      setNotice("Create or select a business case first");
      return;
    }
    if (editingAttachmentId) {
      const updated = await api.updateBusinessCaseDataAttachment(selectedBusinessCase.id, editingAttachmentId, {
        role: selectedRole,
        context_note: contextNote,
        primary_key_column: primaryKeyColumn,
        target_column: mappingTargetColumn
      });
      setNotice(`Updated mapping for ${attachedDataset(updated.data_asset_id)?.name ?? updated.data_asset_id}`);
      resetDataMappingForm();
      setAttachments(await api.listBusinessCaseDataAttachments(selectedBusinessCase.id));
      return;
    }
    const dataAsset = availableDataAssets.find((item) => item.id === selectedDataAssetId) ?? availableDataAssets[0];
    if (!dataAsset) {
      setNotice("Upload or create a dataset first");
      return;
    }
    await api.attachBusinessCaseData(selectedBusinessCase.id, {
      data_asset_id: dataAsset.id,
      data_asset_kind: isDataView(dataAsset) ? "data_view" : "dataset",
      role: selectedRole,
      context_note: contextNote,
      primary_key_column: primaryKeyColumn,
      target_column: mappingTargetColumn,
      origin: "uploaded",
      metadata: {
        source_name: dataAsset.name,
        row_count: dataAsset.row_count
      }
    });
    setNotice(`Attached ${dataAsset.name} as ${selectedRole}`);
    resetDataMappingForm();
    setAttachments(await api.listBusinessCaseDataAttachments(selectedBusinessCase.id));
  }

  function startAddingAttachment() {
    resetDataMappingForm();
    setIsMappingFormOpen(true);
  }

  function startEditingAttachment(attachment: BusinessCaseDataAttachment) {
    setSelectedDataAssetId(attachment.data_asset_id);
    setSelectedRole(attachment.role);
    setPrimaryKeyColumn(attachment.primary_key_column);
    setContextNote(attachment.context_note);
    setMappingTargetColumn(attachment.target_column);
    setEditingAttachmentId(attachment.id);
    setIsMappingFormOpen(true);
    setActiveWorkspace("data");
  }

  function resetDataMappingForm() {
    setSelectedDataAssetId("");
    setSelectedRole("training");
    setPrimaryKeyColumn("");
    setContextNote("");
    setMappingTargetColumn("");
    setEditingAttachmentId("");
    setIsMappingFormOpen(false);
  }

  function resetBusinessCaseEditForm(businessCase: BusinessCase) {
    setEditName(businessCase.name);
    setEditDescription(businessCase.description);
    setEditProblemType(businessCase.problem_type);
    setEditStatus(businessCase.status);
    setEditBusinessOwner(businessCase.business_owner);
    setEditTargetColumn(businessCase.target_column);
    setEditPrimaryMetric(businessCase.primary_metric);
    setEditBusinessGoal(businessCase.business_goal);
    setEditSuccessCriteria(businessCase.success_criteria);
  }

  async function deleteAttachment(attachment: BusinessCaseDataAttachment) {
    if (!selectedBusinessCase) {
      return;
    }
    const label = attachedDataset(attachment.data_asset_id)?.name ?? attachment.data_asset_id;
    const confirmed = window.confirm(`Delete mapping for ${label}? The dataset itself will not be deleted.`);
    if (!confirmed) {
      return;
    }
    await api.deleteBusinessCaseDataAttachment(selectedBusinessCase.id, attachment.id);
    if (editingAttachmentId === attachment.id) {
      resetDataMappingForm();
    }
    setNotice(`Deleted mapping for ${label}`);
    setAttachments(await api.listBusinessCaseDataAttachments(selectedBusinessCase.id));
  }

  async function openBcPipelineRun(pipeline: Pipeline) {
    try {
      const versions = await api.listPipelineVersions(pipeline.id);
      const published = versions.filter((item) => item.status === "published").at(-1);
      if (!published) {
        setNotice("This pipeline has no published version");
        return;
      }
      const normalized = canonicalizeWorkflowDatasetIds(
        normalizeWorkflowDefinition(published.definition),
        datasets
      );
      const inputs = normalized.steps.flatMap((step) => {
        const nested = asRecord(asRecord(step.config).definition);
        return (Array.isArray(nested.inputs) ? nested.inputs : []).flatMap((value) => {
          const input = asRecord(value);
          const logicalId = asString(input.dataset_id);
          if (!logicalId) return [];
          const dataset = datasets.find((item) =>
            item.logical_id === logicalId || item.id === logicalId
          );
          return [{
            key: `${step.step_id}:${asString(input.input_id)}`,
            name: dataset?.name ?? (asString(input.input_id) || "Dataset input"),
            logicalId,
            policy: input.version_policy === "select_at_run"
              ? "select_at_run" as const
              : "latest" as const
          }];
        });
      });
      setBcRunSelections({});
      setBcRunResult(null);
      setBcRunDialog({ pipeline, version: published, inputs });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not prepare pipeline run");
    }
  }

  async function submitBcPipelineRun(event: FormEvent) {
    event.preventDefault();
    if (!bcRunDialog) return;
    const missing = bcRunDialog.inputs.find(
      (input) => input.policy === "select_at_run" && !bcRunSelections[input.key]
    );
    if (missing) {
      setNotice(`Select a version for ${missing.name}`);
      return;
    }
    setBcRunSubmitting(true);
    try {
      let run = await api.runPipeline(bcRunDialog.pipeline.id, {
        pipeline_version_id: bcRunDialog.version.id,
        trigger_type: "manual",
        is_dry_run: false,
        runtime_parameters: {},
        input_versions: bcRunSelections
      });
      setBcRunResult(run);
      setNotice(`Pipeline run ${shortId(run.id)} queued`);
      while (["queued", "running"].includes(run.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        run = await api.getPipelineRun(bcRunDialog.pipeline.id, run.id);
        setBcRunResult(run);
      }
      await onRefresh();
      setNotice(
        run.status === "succeeded"
          ? `Pipeline run ${shortId(run.id)} completed`
          : `Pipeline run ${shortId(run.id)} failed: ${run.error_message || "unknown error"}`
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not start pipeline run");
    } finally {
      setBcRunSubmitting(false);
    }
  }

  return (
    <section className="business-case-screen">
      <div className="panel business-case-catalog">
        <div className="catalog-toolbar">
          <div>
            <h2>Business cases</h2>
            <p>{filteredBusinessCases.length} of {businessCases.length} cases shown</p>
          </div>
          <button className="primary-button" type="button" onClick={() => setIsCreateOpen(true)}>
            <Plus size={16} />
            Create BC
          </button>
        </div>

        <label className="search-field">
          <Search size={16} />
          <input
            aria-label="Search business cases"
            placeholder="Search by name, problem, target, metric or status"
            value={businessCaseSearch}
            onChange={(event) => setBusinessCaseSearch(event.target.value)}
          />
        </label>

        <div className="bc-table">
          <div className="bc-table-row head">
            <span>Business case</span>
            <span>Problem</span>
            <span>Target</span>
            <span>Metric</span>
            <span>Status</span>
            <span>Actions</span>
          </div>
          {filteredBusinessCases.map((item) => (
            <div className={`bc-table-row${selectedBusinessCase?.id === item.id ? " selected" : ""}`} key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <small>{item.description || "No description"}</small>
              </div>
              <span>{item.problem_type}</span>
              <span>{item.target_column || "not set"}</span>
              <span>{item.primary_metric || "not set"}</span>
              <em>{item.status}</em>
              <div className="bc-row-actions">
                <button
                  className="secondary-button compact-button"
                  type="button"
                  onClick={() => {
                    setSelectedBusinessCaseId(item.id);
                    setActiveWorkspace("details");
                  }}
                >
                  <ListChecks size={14} />
                  Details
                </button>
                <button
                  className="secondary-button compact-button"
                  type="button"
                  onClick={() => {
                    setSelectedBusinessCaseId(item.id);
                    setActiveWorkspace("data");
                  }}
                >
                  <Database size={14} />
                  Data
                </button>
                <button
                  className="secondary-button compact-button"
                  type="button"
                  onClick={() => {
                    setSelectedBusinessCaseId(item.id);
                    setActiveWorkspace("pipelines");
                  }}
                >
                  <Share2 size={14} />
                  Pipelines
                </button>
                <button
                  className="secondary-button compact-button"
                  type="button"
                  onClick={() => {
                    setSelectedBusinessCaseId(item.id);
                    setActiveWorkspace("models");
                  }}
                >
                  <Brain size={14} />
                  Models
                </button>
                <button
                  className="secondary-button compact-button"
                  type="button"
                  onClick={() => {
                    setSelectedBusinessCaseId(item.id);
                    setActiveWorkspace("reports");
                  }}
                >
                  <BarChart3 size={14} />
                  Reports
                </button>
              </div>
            </div>
          ))}
          {filteredBusinessCases.length === 0 && <div className="catalog-empty">No business cases match this search.</div>}
        </div>
      </div>

      {selectedBusinessCase && activeWorkspace && (
      <div className="bc-workspace">
        <div className="panel">
          <div className="bc-workspace-header">
            <div>
              <span className="eyebrow">Selected business case</span>
              <h2>{selectedBusinessCase?.name ?? "No business case selected"}</h2>
              {selectedBusinessCase && (
                <p>{selectedBusinessCase.problem_type} / target: {selectedBusinessCase.target_column || "not set"} / metric: {selectedBusinessCase.primary_metric || "not set"}</p>
              )}
            </div>
            <div className="button-row">
              <button className={`secondary-button compact-button${activeWorkspace === "details" ? " active" : ""}`} type="button" onClick={() => setActiveWorkspace("details")}>
                <ListChecks size={14} />
                Details
              </button>
              <button className={`secondary-button compact-button${activeWorkspace === "data" ? " active" : ""}`} type="button" onClick={() => setActiveWorkspace("data")}>
                <Database size={14} />
                Data
              </button>
              <button className={`secondary-button compact-button${activeWorkspace === "pipelines" ? " active" : ""}`} type="button" onClick={() => setActiveWorkspace("pipelines")}>
                <Share2 size={14} />
                Pipelines
              </button>
              <button className={`secondary-button compact-button${activeWorkspace === "models" ? " active" : ""}`} type="button" onClick={() => setActiveWorkspace("models")}>
                <Brain size={14} />
                Models
              </button>
              <button className={`secondary-button compact-button${activeWorkspace === "reports" ? " active" : ""}`} type="button" onClick={() => setActiveWorkspace("reports")}>
                <BarChart3 size={14} />
                Reports
              </button>
            </div>
          </div>
        </div>

        {selectedBusinessCase && activeWorkspace === "details" && (
          <form className="panel form-panel bc-detail-panel" onSubmit={submitBusinessCaseUpdate}>
            <div className="panel-header">
              <h2>Edit business case</h2>
              <ListChecks size={18} />
            </div>
            <div className="bc-edit-grid">
              <label>
                Name
                <input value={editName} onChange={(event) => setEditName(event.target.value)} required />
              </label>
              <label>
                Problem type
                <select value={editProblemType} onChange={(event) => setEditProblemType(event.target.value)}>
                  <option value="binary_classification">Binary classification</option>
                  <option value="multiclass_classification">Multiclass classification</option>
                  <option value="regression">Regression</option>
                  <option value="forecasting">Forecasting</option>
                  <option value="clustering">Clustering</option>
                  <option value="anomaly_detection">Anomaly detection</option>
                  <option value="custom">Custom</option>
                </select>
              </label>
              <label>
                Status
                <select value={editStatus} onChange={(event) => setEditStatus(event.target.value)}>
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="production">Production</option>
                  <option value="archived">Archived</option>
                </select>
              </label>
              <label>
                Business owner
                <input value={editBusinessOwner} onChange={(event) => setEditBusinessOwner(event.target.value)} />
              </label>
              <label>
                Target column
                <input value={editTargetColumn} onChange={(event) => setEditTargetColumn(event.target.value)} />
              </label>
              <label>
                Primary metric
                <input value={editPrimaryMetric} onChange={(event) => setEditPrimaryMetric(event.target.value)} />
              </label>
              <label className="wide-field">
                Description
                <textarea className="compact-textarea" value={editDescription} onChange={(event) => setEditDescription(event.target.value)} />
              </label>
              <label className="wide-field">
                Business goal
                <input value={editBusinessGoal} onChange={(event) => setEditBusinessGoal(event.target.value)} />
              </label>
              <label className="wide-field">
                Success criteria
                <input value={editSuccessCriteria} onChange={(event) => setEditSuccessCriteria(event.target.value)} />
              </label>
            </div>
            <div className="button-row">
              <button className="primary-button" type="submit">
                <Save size={16} />
                Save BC
              </button>
              <button className="secondary-button" type="button" onClick={() => resetBusinessCaseEditForm(selectedBusinessCase)}>
                <RotateCcw size={16} />
                Reset
              </button>
            </div>
          </form>
        )}

        {selectedBusinessCase && activeWorkspace === "data" && (
          <>
            <div className="panel bc-mapped-data-panel">
              <div className="panel-header bc-mapped-data-header">
                <div>
                  <h2>Mapped data</h2>
                  <p>{activeAttachments.length} active mapping{activeAttachments.length === 1 ? "" : "s"}</p>
                </div>
                <button
                  className="primary-button"
                  type="button"
                  onClick={startAddingAttachment}
                  disabled={availableDataAssets.length === 0}
                >
                  <Plus size={16} />
                  Add mapping
                </button>
              </div>
              <div className="asset-list">
                {activeAttachments.map((item) => {
                  const assetName = attachedDataset(item.data_asset_id)?.name ?? item.data_asset_id;
                  return (
                    <div className={`asset-row${editingAttachmentId === item.id ? " selected" : ""}`} key={item.id}>
                      <div>
                        <strong>{assetName}</strong>
                        <span>{item.data_asset_kind} / key: {item.primary_key_column || "not set"} / target: {item.target_column || "not set"} / {item.context_note || "no note"}</span>
                      </div>
                      <div className="asset-actions">
                        <em>{item.role}</em>
                        {attachedDataset(item.data_asset_id) && (
                          <button className="secondary-button compact-button" type="button"
                            onClick={() => setBcDatasetHistory(attachedDataset(item.data_asset_id)!)}>
                            <History size={14} /> Versions
                          </button>
                        )}
                        <button
                          className="secondary-button compact-button"
                          type="button"
                          onClick={() => startEditingAttachment(item)}
                        >
                          <ListChecks size={14} />
                          Edit
                        </button>
                        <button
                          aria-label={`Delete mapping for ${assetName}`}
                          className="icon-button danger-icon"
                          type="button"
                          onClick={() => void deleteAttachment(item)}
                          title="Delete mapping"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })}
                {activeAttachments.length === 0 && <div className="empty-state">No data mapped to this business case yet</div>}
              </div>
            </div>

            {isMappingFormOpen && (
              <form className="panel form-panel bc-mapping-form" onSubmit={attachData}>
                <div className="panel-header">
                  <div>
                    <h2>{editingAttachmentId ? "Edit data mapping" : "Add data mapping"}</h2>
                    <p>
                      {editingAttachmentId
                        ? "Update the role and context of this mapping."
                        : "Connect a dataset or Data View to this business case."}
                    </p>
                  </div>
                  <Database size={18} />
                </div>
                <label>
                  Dataset/Data View
                  <select
                    value={selectedDataAssetId}
                    onChange={(event) => setSelectedDataAssetId(event.target.value)}
                    disabled={Boolean(editingAttachmentId)}
                  >
                    <option value="">First available</option>
                    {availableDataAssets.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Role
                  <select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>
                    <option value="source">Source</option>
                    <option value="training">Training</option>
                    <option value="validation">Validation</option>
                    <option value="test">Test</option>
                    <option value="scoring_input">Scoring input</option>
                    <option value="scoring_output">Scoring output</option>
                    <option value="monitoring_actuals">Monitoring actuals</option>
                    <option value="reference">Reference</option>
                  </select>
                </label>
                <label>
                  Primary key column
                  <input value={primaryKeyColumn} onChange={(event) => setPrimaryKeyColumn(event.target.value)} />
                </label>
                <label>
                  Target column
                  <input value={mappingTargetColumn} onChange={(event) => setMappingTargetColumn(event.target.value)} />
                </label>
                <label>
                  Context note
                  <input value={contextNote} onChange={(event) => setContextNote(event.target.value)} />
                </label>
                <div className="button-row">
                  <button className="primary-button" type="submit">
                    <Save size={16} />
                    {editingAttachmentId ? "Save mapping" : "Add mapping"}
                  </button>
                  <button className="secondary-button" type="button" onClick={resetDataMappingForm}>
                    <X size={16} />
                    Cancel
                  </button>
                </div>
              </form>
            )}

            {deletedAttachments.length > 0 && (
              <details className="panel editor-details deleted-assets-panel">
                <summary>Deleted BC mappings <span>{deletedAttachments.length}</span></summary>
                <AssetList title="" assets={deletedAttachments.map((item) => ({
                  id: item.id,
                  name: attachedDataset(item.data_asset_id)?.name ?? item.data_asset_id,
                  meta: `${item.data_asset_kind} / key: ${item.primary_key_column || "not set"} / ${item.context_note || "no note"}`,
                  status: item.role
                }))} />
              </details>
            )}
          </>
        )}

        {selectedBusinessCase && activeWorkspace === "pipelines" && (
          <AssetList title="Mapped pipelines" assets={selectedBusinessCasePipelines.map((item) => ({
            id: item.id,
            name: item.name,
            meta: `${item.type} / ${businessCaseName(businessCases, item.business_case_id)}`,
            status: item.status,
            actions: [
              {
                label: "Versions",
                icon: "versions",
                onClick: () => setBcPipelineHistory(item)
              },
              {
                label: "Run",
                icon: "run",
                disabled: !item.latest_published_version_number,
                onClick: () => void openBcPipelineRun(item)
              },
              {
                label: "Edit",
                icon: "edit",
                onClick: () => onEditPipeline(item.id)
              }
            ]
          }))} />
        )}
        {selectedBusinessCase && activeWorkspace === "models" && (
          <div className="panel">
            <div className="panel-header">
              <div><h2>Models</h2><p>{selectedBusinessCaseModels.length} model families in this Business Case</p></div>
              <button className="secondary-button compact-button" type="button"
                onClick={() => onOpenModels(selectedBusinessCase.id)}>Open model registry</button>
            </div>
            <AssetList title="" assets={selectedBusinessCaseModels.map((item) => ({
              id: item.id,
              name: `${item.name} · ${item.version}`,
              meta: `${item.algorithm} · ${item.problem_type} · ${businessCaseName(businessCases, item.business_case_id)}`,
              status: item.stage,
              actions: [
                { label: "Versions", icon: "versions", onClick: () => setBcModelHistory(item) },
                { label: "View", icon: "view", onClick: () => setSelectedBcModel(item) }
              ]
            }))} />
          </div>
        )}
        {selectedBusinessCase && activeWorkspace === "reports" && (
          <div className="panel">
            <div className="panel-header">
              <div><h2>Scoring reports</h2><p>{selectedBusinessCaseReports.length} report families in this Business Case</p></div>
              <button className="secondary-button compact-button" type="button"
                onClick={() => onOpenScoringReports(selectedBusinessCase.id)}>Open report registry</button>
            </div>
            <AssetList title="" assets={selectedBusinessCaseReports.map((item) => ({
              id: item.id,
              name: `${item.name} · v${item.version_number}`,
              meta: `${pipelineName(pipelines, item.pipeline_id)} · ${item.problem_type} · ${item.evaluated_row_count.toLocaleString()} rows`,
              status: "ready",
              actions: [
                { label: "Versions", icon: "versions", onClick: () => setBcReportHistory(item) },
                { label: "View", icon: "view", onClick: () => setSelectedBcReport(item) }
              ]
            }))} />
          </div>
        )}
      </div>
      )}
      {selectedBcModel && (
        <DeferredPanel>
          <ModelDetailsDialog
            model={selectedBcModel}
            businessCaseName={businessCaseName(businessCases, selectedBcModel.business_case_id)}
            pipelineName={pipelineName(pipelines, selectedBcModel.pipeline_id)}
            onOpenDataset={onOpenDataset}
            onClose={() => setSelectedBcModel(null)}
          />
        </DeferredPanel>
      )}
      {selectedBcReport && (
        <DeferredPanel>
          <ScoringReportDialog
            report={selectedBcReport}
            onOpenDataset={onOpenDataset}
            onClose={() => setSelectedBcReport(null)}
          />
        </DeferredPanel>
      )}
      {bcDatasetHistory && (
        <DatasetVersionHistoryDialog
          dataset={bcDatasetHistory}
          versions={datasets.filter((item) => item.logical_id === bcDatasetHistory.logical_id)}
          onClose={() => setBcDatasetHistory(null)}
          onOpen={(datasetId) => {
            setBcDatasetHistory(null);
            onOpenDataset(datasetId);
          }}
        />
      )}
      {bcModelHistory && (
        <DeferredPanel>
          <ModelVersionHistoryDialog
            model={bcModelHistory}
            businessCaseName={businessCaseName(businessCases, bcModelHistory.business_case_id)}
            pipelineName={pipelineName(pipelines, bcModelHistory.pipeline_id)}
            onClose={() => setBcModelHistory(null)}
            onView={(model) => {
              setBcModelHistory(null);
              setSelectedBcModel(model);
            }}
          />
        </DeferredPanel>
      )}
      {bcReportHistory && (
        <DeferredPanel>
          <ScoringReportHistoryDialog
            report={bcReportHistory}
            onClose={() => setBcReportHistory(null)}
            onView={(report) => {
              setBcReportHistory(null);
              setSelectedBcReport(report);
            }}
          />
        </DeferredPanel>
      )}
      {bcPipelineHistory && (
        <PipelineVersionHistoryDialog
          pipeline={bcPipelineHistory}
          businessCaseName={businessCaseName(businessCases, bcPipelineHistory.business_case_id)}
          onClose={() => setBcPipelineHistory(null)}
        />
      )}
      {bcRunDialog && (
        <div className="modal-backdrop" role="presentation"
          onMouseDown={(event) => event.target === event.currentTarget && !bcRunSubmitting && setBcRunDialog(null)}>
          <form className="modal-dialog form-panel" onSubmit={submitBcPipelineRun}>
            <div className="modal-header">
              <div><span className="builder-kicker">Business Case manual run</span>
                <h2>{bcRunDialog.pipeline.name}</h2></div>
              <button className="icon-button" type="button" disabled={bcRunSubmitting}
                onClick={() => setBcRunDialog(null)} aria-label="Close run dialog"><X size={17} /></button>
            </div>
            {bcRunDialog.inputs.map((input) => {
              const inputVersions = datasets
                .filter((dataset) => dataset.logical_id === input.logicalId && dataset.status !== "deleted")
                .sort((left, right) => right.version_number - left.version_number);
              return (
                <label key={input.key}>{input.name}
                  {input.policy === "select_at_run" ? (
                    <select value={bcRunSelections[input.key] ?? ""}
                      onChange={(event) => setBcRunSelections((current) => ({
                        ...current,
                        [input.key]: event.target.value
                      }))} required>
                      <option value="">Select immutable version…</option>
                      {inputVersions.map((version) => (
                        <option key={version.id} value={version.id}>
                          v{version.version_number} · {version.row_count ?? "?"} rows
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input readOnly value={inputVersions[0]
                      ? `Latest → v${inputVersions[0].version_number}`
                      : "No active version"} />
                  )}
                </label>
              );
            })}
            {bcRunResult && (
              <div className={`catalog-run-monitor ${bcRunResult.status}`}>
                <div><strong>{bcRunResult.status}</strong>
                  <span>Run {shortId(bcRunResult.id)} · {bcRunResult.processed_row_count ?? 0} processed rows</span></div>
              </div>
            )}
            <div className="modal-actions">
              <button className="secondary-button" type="button" disabled={bcRunSubmitting}
                onClick={() => setBcRunDialog(null)}>Close</button>
              {!bcRunResult && (
                <button className="primary-button" type="submit" disabled={bcRunSubmitting}>
                  <Play size={15} /> {bcRunSubmitting ? "Running…" : "Run published version"}
                </button>
              )}
            </div>
          </form>
        </div>
      )}

      {isCreateOpen && (
        <div className="modal-backdrop">
          <form className="modal-dialog form-panel" onSubmit={submitBusinessCase}>
            <div className="modal-header">
              <h2>New business case</h2>
              <button className="icon-button" type="button" aria-label="Close" onClick={() => setIsCreateOpen(false)}>
                <X size={16} />
              </button>
            </div>
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Problem type
              <select value={problemType} onChange={(event) => setProblemType(event.target.value)}>
                <option value="binary_classification">Binary classification</option>
                <option value="multiclass_classification">Multiclass classification</option>
                <option value="regression">Regression</option>
                <option value="forecasting">Forecasting</option>
                <option value="clustering">Clustering</option>
                <option value="anomaly_detection">Anomaly detection</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label>
              Description
              <textarea className="compact-textarea" value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label>
              Target column
              <input value={targetColumn} onChange={(event) => setTargetColumn(event.target.value)} />
            </label>
            <label>
              Primary metric
              <input value={primaryMetric} onChange={(event) => setPrimaryMetric(event.target.value)} />
            </label>
            <label>
              Business goal
              <input value={businessGoal} onChange={(event) => setBusinessGoal(event.target.value)} />
            </label>
            <label>
              Success criteria
              <input value={successCriteria} onChange={(event) => setSuccessCriteria(event.target.value)} />
            </label>
            <div className="modal-actions">
              <button className="secondary-button" type="button" onClick={() => setIsCreateOpen(false)}>Cancel</button>
              <button className="primary-button" type="submit">
                <Plus size={16} />
                Create BC
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

function PipelinesPanel({
  businessCases,
  datasets,
  pipelines,
  openRequest,
  onOpenRequestConsumed,
  onRefresh,
  onExamineDataset,
  setNotice
}: {
  businessCases: BusinessCase[];
  datasets: DataAsset[];
  pipelines: Pipeline[];
  openRequest: { pipelineId: string; requestId: number } | null;
  onOpenRequestConsumed: () => void;
  onRefresh: () => Promise<void>;
  onExamineDataset: (datasetId: string) => void;
  setNotice: (message: string) => void;
}) {
  const [businessCaseId, setBusinessCaseId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [pipelineType, setPipelineType] = useState("custom");
  const [selectedPipelineId, setSelectedPipelineId] = useState("");
  const [isCreatePipelineOpen, setIsCreatePipelineOpen] = useState(false);
  const [copyPipelineTarget, setCopyPipelineTarget] = useState<Pipeline | null>(null);
  const [copyPipelineName, setCopyPipelineName] = useState("");
  const [deletePipelineTarget, setDeletePipelineTarget] = useState<Pipeline | null>(null);
  const [isPipelineMutationSubmitting, setIsPipelineMutationSubmitting] = useState(false);
  const [isPipelineEditorOpen, setIsPipelineEditorOpen] = useState(false);
  const [catalogRunDialog, setCatalogRunDialog] = useState<{
    pipeline: Pipeline;
    version: PipelineVersion;
    inputs: Array<{
      key: string;
      name: string;
      logicalId: string;
      policy: "latest" | "select_at_run";
    }>;
  } | null>(null);
  const [catalogRunSelections, setCatalogRunSelections] = useState<Record<string, string>>({});
  const [isCatalogRunSubmitting, setIsCatalogRunSubmitting] = useState(false);
  const [catalogRunResult, setCatalogRunResult] = useState<PipelineRun | null>(null);
  const [isRenamingPipeline, setIsRenamingPipeline] = useState(false);
  const [isSavingPipelineName, setIsSavingPipelineName] = useState(false);
  const [pipelineNameDraft, setPipelineNameDraft] = useState("");
  const [pipelineDescriptionDraft, setPipelineDescriptionDraft] = useState("");
  const [pipelineTypeDraft, setPipelineTypeDraft] = useState("custom");
  const [runFeedback, setRunFeedback] = useState<{
    status: "queued" | "running" | "succeeded" | "failed";
    title: string;
    detail: string;
  } | null>(null);
  const [dryRunResult, setDryRunResult] = useState<PipelineRun | null>(null);
  const [examinedDryRun, setExaminedDryRun] = useState<{
    run: PipelineRun;
    outputId: string;
    pipelineStepId: string;
  } | null>(null);
  const [isDefinitionDirty, setIsDefinitionDirty] = useState(false);
  const [workflowDefinition, setWorkflowDefinition] = useState<WorkflowDefinition>(emptyWorkflowDefinition());
  const [definitionText, setDefinitionText] = useState(JSON.stringify(emptyWorkflowDefinition(), null, 2));
  const [versions, setVersions] = useState<PipelineVersion[]>([]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [activeStepRuns, setActiveStepRuns] = useState<PipelineStepRun[]>([]);
  const [selectedRunDetails, setSelectedRunDetails] = useState<PipelineRun | null>(null);
  const [isRunHistoryOpen, setIsRunHistoryOpen] = useState(false);
  const [versionHistoryPipeline, setVersionHistoryPipeline] = useState<Pipeline | null>(null);
  const [runHistoryRefreshKey, setRunHistoryRefreshKey] = useState(0);
  const [pipelineDataAttachments, setPipelineDataAttachments] = useState<BusinessCaseDataAttachment[]>([]);
  const activePipelines = pipelines.filter((item) => item.status !== "deprecated");
  const deprecatedPipelines = pipelines.filter((item) => item.status === "deprecated");
  const selectedPipeline = activePipelines.find((item) => item.id === selectedPipelineId) ?? activePipelines[0];
  const selectedPipelineIdValue = selectedPipeline?.id ?? "";
  const selectedBusinessCaseIdValue = selectedPipeline?.business_case_id ?? "";

  useEffect(() => {
    if (!businessCaseId && businessCases[0]) {
      setBusinessCaseId(businessCases[0].id);
    }
  }, [businessCaseId, businessCases]);

  useEffect(() => {
    if (!selectedPipelineId && pipelines[0]) {
      setSelectedPipelineId(pipelines[0].id);
    }
  }, [pipelines, selectedPipelineId]);

  useEffect(() => {
    if (!openRequest) return;
    const requestedPipeline = pipelines.find((item) => item.id === openRequest.pipelineId);
    if (!requestedPipeline) {
      setNotice("The requested pipeline is no longer available");
      onOpenRequestConsumed();
      return;
    }
    setSelectedPipelineId(requestedPipeline.id);
    setRunFeedback(null);
    setIsPipelineEditorOpen(true);
    onOpenRequestConsumed();
  }, [openRequest, onOpenRequestConsumed, pipelines, setNotice]);

  useEffect(() => {
    setPipelineNameDraft(selectedPipeline?.name ?? "");
    setPipelineDescriptionDraft(selectedPipeline?.description ?? "");
    setPipelineTypeDraft(selectedPipeline?.type ?? "custom");
    setIsRenamingPipeline(false);
  }, [selectedPipeline?.description, selectedPipeline?.id, selectedPipeline?.name, selectedPipeline?.type]);

  useEffect(() => {
    if (!selectedPipelineIdValue) {
      setVersions([]);
      setRuns([]);
      setActiveStepRuns([]);
      setPipelineDataAttachments([]);
      return;
    }
    let active = true;
    Promise.all([
      api.listPipelineVersions(selectedPipelineIdValue),
      api.listPipelineRuns(selectedPipelineIdValue),
      api.listBusinessCaseDataAttachments(selectedBusinessCaseIdValue)
    ])
      .then(([versionItems, runItems, attachmentItems]) => {
        if (!active) return;
        setVersions(versionItems);
        setRuns(runItems);
        setPipelineDataAttachments(attachmentItems);
        const draftVersion = versionItems.find((item) => item.status === "draft");
        const selectedVersion = draftVersion ?? versionItems.at(-1);
        if (selectedVersion) {
          // A cached definition is only valid while its editable server-side
          // draft exists. Otherwise stale browser state makes a published
          // version look dirty and points dry-run at a draft that is gone.
          const workingDraft = draftVersion
            ? readPipelineWorkingDraft(selectedPipelineIdValue)
            : null;
          if (!draftVersion) clearPipelineWorkingDraft(selectedPipelineIdValue);
          const normalized = canonicalizeWorkflowDatasetIds(
            normalizeWorkflowDefinition(workingDraft ?? selectedVersion.definition),
            datasets
          );
          setWorkflowDefinition(normalized);
          setDefinitionText(JSON.stringify(normalized, null, 2));
          setIsDefinitionDirty(Boolean(workingDraft));
          if (workingDraft) setNotice("Recovered unsaved pipeline changes from this browser tab");
        }
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load pipeline details"));
    return () => { active = false; };
  }, [selectedBusinessCaseIdValue, selectedPipelineIdValue, setNotice]);

  useEffect(() => {
    if (!isDefinitionDirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isDefinitionDirty]);

  async function createPipeline(event: FormEvent) {
    event.preventDefault();
    if (!businessCaseId) {
      setNotice("Create or select a business case first");
      return;
    }
    const created = await api.createPipeline({
      business_case_id: businessCaseId,
      name,
      description,
      type: pipelineType,
      definition: emptyWorkflowDefinition()
    });
    setNotice(`Pipeline created: ${created.name}`);
    setSelectedPipelineId(created.id);
    setIsCreatePipelineOpen(false);
    setIsPipelineEditorOpen(true);
    setName("");
    setDescription("");
    await onRefresh();
  }

  async function renamePipeline(event: FormEvent) {
    event.preventDefault();
    if (!selectedPipeline) return;
    const nextName = pipelineNameDraft.trim();
    if (!nextName) {
      setNotice("Pipeline name cannot be empty");
      return;
    }
    if (
      nextName === selectedPipeline.name
      && pipelineDescriptionDraft.trim() === selectedPipeline.description
      && pipelineTypeDraft === selectedPipeline.type
    ) {
      setIsRenamingPipeline(false);
      return;
    }
    setIsSavingPipelineName(true);
    try {
      await api.updatePipeline(selectedPipeline.id, {
        name: nextName,
        description: pipelineDescriptionDraft.trim(),
        type: pipelineTypeDraft
      });
      await onRefresh();
      setIsRenamingPipeline(false);
      setNotice(`Pipeline metadata updated: “${nextName}”`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not rename pipeline");
    } finally {
      setIsSavingPipelineName(false);
    }
  }

  async function copyExistingPipeline(event: FormEvent) {
    event.preventDefault();
    if (!copyPipelineTarget) return;
    const nextName = copyPipelineName.trim();
    if (!nextName) {
      setNotice("Pipeline name cannot be empty");
      return;
    }
    setIsPipelineMutationSubmitting(true);
    try {
      const copied = await api.copyPipeline(copyPipelineTarget.id, { name: nextName });
      setCopyPipelineTarget(null);
      setCopyPipelineName("");
      setSelectedPipelineId(copied.id);
      await onRefresh();
      setIsPipelineEditorOpen(true);
      setNotice(`Pipeline copied as “${copied.name}”. Draft v1 is ready to edit.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not copy pipeline");
    } finally {
      setIsPipelineMutationSubmitting(false);
    }
  }

  async function deleteExistingPipeline() {
    if (!deletePipelineTarget) return;
    setIsPipelineMutationSubmitting(true);
    try {
      const result = await api.deletePipeline(deletePipelineTarget.id);
      clearPipelineWorkingDraft(deletePipelineTarget.id);
      if (selectedPipelineId === deletePipelineTarget.id) setSelectedPipelineId("");
      const removedName = deletePipelineTarget.name;
      setDeletePipelineTarget(null);
      await onRefresh();
      setNotice(
        result.action === "deprecated"
          ? `Pipeline “${removedName}” has run history, so it was deprecated and moved out of the active registry`
          : `Pipeline “${removedName}” permanently deleted`
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not delete pipeline");
    } finally {
      setIsPipelineMutationSubmitting(false);
    }
  }

  async function persistDraft(showNotice = true) {
    if (!selectedPipeline) {
      setNotice("Select a pipeline first");
      return null;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(definitionText) as Record<string, unknown>;
    } catch {
      setNotice("Pipeline definition is not valid JSON");
      return null;
    }
    const saved = await api.updateDraftPipelineVersion(selectedPipeline.id, parsed);
    clearPipelineWorkingDraft(selectedPipeline.id);
    setIsDefinitionDirty(false);
    if (showNotice) setNotice("Draft version saved");
    setVersions(await api.listPipelineVersions(selectedPipeline.id));
    await onRefresh();
    return saved;
  }

  async function saveDraft() {
    await persistDraft();
  }

  async function publishDraft() {
    if (!selectedPipeline) {
      setNotice("Select a pipeline first");
      return;
    }
    if (isDefinitionDirty && !await persistDraft(false)) return;
    await api.publishDraftPipelineVersion(selectedPipeline.id);
    setNotice("Draft version published");
    setVersions(await api.listPipelineVersions(selectedPipeline.id));
    await onRefresh();
  }

  async function createNextDraft() {
    if (!selectedPipeline) {
      setNotice("Select a pipeline first");
      return;
    }
    const draft = await api.createNextDraftPipelineVersion(selectedPipeline.id);
    const normalized = canonicalizeWorkflowDatasetIds(
      normalizeWorkflowDefinition(draft.definition),
      datasets
    );
    setWorkflowDefinition(normalized);
    setDefinitionText(JSON.stringify(normalized, null, 2));
    clearPipelineWorkingDraft(selectedPipeline.id);
    setIsDefinitionDirty(false);
    setVersions(await api.listPipelineVersions(selectedPipeline.id));
    setNotice(`Draft v${draft.version_number} created`);
    await onRefresh();
  }

  async function runSelectedPipeline(isDryRun: boolean, stepId?: string) {
    if (!selectedPipeline) {
      setNotice("Select a pipeline first");
      return;
    }
    const target = stepId ? "DE step" : "pipeline";
    const action = isDryRun ? "Dry-run" : "Run";
    if (isDryRun && !hasDraft) {
      const detail = "Create a draft before running a dry-run. The published version remains available through Run.";
      setRunFeedback({ status: "failed", title: `${action} blocked`, detail });
      setNotice(detail);
      return;
    }
    setRunFeedback({ status: "queued", title: `${action} queued`, detail: `Preparing ${target} execution…` });
    if (isDryRun) setDryRunResult(null);
    try {
      if (!isDryRun && (isDefinitionDirty || hasDraft)) {
        const detail = "Publish the current draft before a full run. Full runs use immutable published versions; dry-run is available for drafts.";
        setRunFeedback({ status: "failed", title: `${action} blocked`, detail });
        setNotice(detail);
        return;
      }
      const wasDirty = isDefinitionDirty;
      const savedDraft = isDryRun && wasDirty ? await persistDraft(false) : null;
      if (isDryRun && wasDirty && !savedDraft) {
        setRunFeedback({ status: "failed", title: `${action} failed`, detail: "Save a valid draft definition before execution." });
        return;
      }
      let run = await api.runPipeline(selectedPipeline.id, {
        pipeline_version_id: isDryRun
          ? savedDraft?.id ?? versions.find((item) => item.status === "draft")?.id
          : undefined,
        step_id: stepId,
        trigger_type: "manual",
        is_dry_run: isDryRun,
        runtime_parameters: {}
      });
      setRunFeedback({ status: "running", title: `${action} in progress`, detail: `Worker accepted ${target} run ${shortId(run.id)}.` });
      while (run.status === "queued" || run.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        run = await api.getPipelineRun(selectedPipeline.id, run.id);
      }
      setRuns(await api.listPipelineRuns(selectedPipeline.id));
      setActiveStepRuns(await api.listPipelineStepRuns(selectedPipeline.id, run.id));
      const scope = run.output_manifest[0]?.data_scope ?? "unknown";
      const counts = `${run.input_row_count ?? 0} input rows → ${run.output_row_count ?? 0} output rows`;
      const failed = run.status === "failed";
      const title = failed ? `${action} failed` : `${action} completed`;
      const fittedTransform = run.output_manifest.find((item) => item.artifact_type === "feature_transform");
      const fittedDetail = fittedTransform?.artifact_id
        ? ` · fitted transform ${fittedTransform.artifact_id}`
        : "";
      const detail = failed
        ? run.error_message
        : `${target} finished successfully · ${scope} scope · ${counts}${fittedDetail}`;
      setRunFeedback({ status: failed ? "failed" : "succeeded", title, detail });
      setNotice(`${title}: ${detail}`);
      if (!failed && isDryRun) setDryRunResult(run);
      if (!failed && !isDryRun) {
        await onRefresh();
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Pipeline execution could not be started";
      setRunFeedback({ status: "failed", title: `${action} failed`, detail });
    }
  }

  async function openCatalogRunDialog(pipeline: Pipeline) {
    try {
      const versionItems = await api.listPipelineVersions(pipeline.id);
      const published = versionItems.filter((item) => item.status === "published").at(-1);
      if (!published) {
        setNotice("This pipeline has no published version");
        return;
      }
      const normalized = canonicalizeWorkflowDatasetIds(
        normalizeWorkflowDefinition(published.definition),
        datasets
      );
      const inputs = normalized.steps.flatMap((step) => {
        const nested = asRecord(asRecord(step.config).definition);
        const rawInputs = Array.isArray(nested.inputs) ? nested.inputs : [];
        return rawInputs.flatMap((value) => {
          const input = asRecord(value);
          const logicalId = asString(input.dataset_id);
          if (!logicalId) return [];
          const dataset = datasets.find((item) => item.logical_id === logicalId || item.id === logicalId);
          return [{
            key: `${step.step_id}:${asString(input.input_id)}`,
            name: dataset?.name ?? (asString(input.input_id) || "Dataset input"),
            logicalId,
            policy: input.version_policy === "select_at_run" ? "select_at_run" as const : "latest" as const
          }];
        });
      });
      setCatalogRunSelections({});
      setCatalogRunResult(null);
      setCatalogRunDialog({ pipeline, version: published, inputs });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not prepare pipeline run");
    }
  }

  async function submitCatalogRun(event: FormEvent) {
    event.preventDefault();
    if (!catalogRunDialog) return;
    const missing = catalogRunDialog.inputs.find(
      (input) => input.policy === "select_at_run" && !catalogRunSelections[input.key]
    );
    if (missing) {
      setNotice(`Select a version for ${missing.name}`);
      return;
    }
    setIsCatalogRunSubmitting(true);
    try {
      let run = await api.runPipeline(catalogRunDialog.pipeline.id, {
        pipeline_version_id: catalogRunDialog.version.id,
        trigger_type: "manual",
        is_dry_run: false,
        runtime_parameters: {},
        input_versions: catalogRunSelections
      });
      setNotice(`Pipeline run ${shortId(run.id)} queued`);
      setCatalogRunResult(run);
      setSelectedPipelineId(catalogRunDialog.pipeline.id);
      while (run.status === "queued" || run.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        run = await api.getPipelineRun(catalogRunDialog.pipeline.id, run.id);
        setCatalogRunResult(run);
      }
      await onRefresh();
      if (run.status === "succeeded") {
        const datasetsCreated = run.output_manifest.filter((item) => item.dataset_id).length;
        setNotice(`Pipeline run ${shortId(run.id)} completed · ${datasetsCreated} datasets created`);
      } else {
        setNotice(`Pipeline run ${shortId(run.id)} failed: ${run.error_message || "unknown error"}`);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not start pipeline run");
    } finally {
      setIsCatalogRunSubmitting(false);
    }
  }

  function updateWorkflowDefinition(definition: WorkflowDefinition) {
    setWorkflowDefinition(definition);
    setDefinitionText(JSON.stringify(definition, null, 2));
    setIsDefinitionDirty(true);
    if (selectedPipeline) writePipelineWorkingDraft(selectedPipeline.id, definition);
  }

  function updateDefinitionText(value: string) {
    setDefinitionText(value);
    setIsDefinitionDirty(true);
    try {
      const parsed = JSON.parse(value);
      setWorkflowDefinition(canonicalizeWorkflowDatasetIds(
        normalizeWorkflowDefinition(parsed),
        datasets
      ));
      if (selectedPipeline) writePipelineWorkingDraft(selectedPipeline.id, parsed);
    } catch {
      // Keep the last valid visual definition while the advanced JSON is incomplete.
    }
  }

  const hasDraft = versions.some((item) => item.status === "draft");
  const hasPublished = versions.some((item) => item.status === "published");
  const isRunActive = runFeedback?.status === "queued" || runFeedback?.status === "running";
  const canRunPublishedVersion = hasPublished && !hasDraft;

  function renderPipelineRow(item: Pipeline, isDeprecated = false) {
    return (
      <div className="pipeline-table-row" role="row" key={item.id}>
        <span><strong>{item.name}</strong><small>{item.description || "No description"}</small></span>
        <span>{businessCaseName(businessCases, item.business_case_id)}</span>
        <span>{item.type.replaceAll("_", " ")}</span>
        <span>
          <strong>{item.latest_published_version_number ? `v${item.latest_published_version_number}` : "—"}</strong>
          <small>
            {item.published_version_count} published
            {item.draft_version_number ? ` · v${item.draft_version_number} draft` : ""}
          </small>
        </span>
        <span><i className={`pipeline-status ${item.status}`}>{item.status}</i></span>
        <span>{formatDateTime(item.updated_at)}</span>
        <span>
          <button
            className="secondary-button compact-button"
            type="button"
            disabled={item.published_version_count === 0}
            onClick={() => setVersionHistoryPipeline(item)}
          >
            <History size={14} /> Versions
          </button>
          {!isDeprecated && (
            <button
              className="primary-button compact-button"
              type="button"
              disabled={item.status !== "published"}
              onClick={() => openCatalogRunDialog(item)}
            >
              <Play size={14} /> Run
            </button>
          )}
          <button
            className="secondary-button compact-button"
            type="button"
            onClick={() => {
              setCopyPipelineTarget(item);
              setCopyPipelineName(`${item.name} — copy`);
            }}
          >
            <Copy size={14} /> Copy
          </button>
          {!isDeprecated && (
            <>
              <button
                className="secondary-button compact-button danger-action"
                type="button"
                onClick={() => setDeletePipelineTarget(item)}
              >
                <Trash2 size={14} /> Delete
              </button>
              <button
                className="secondary-button compact-button"
                type="button"
                onClick={() => {
                  setSelectedPipelineId(item.id);
                  setRunFeedback(null);
                  setIsPipelineEditorOpen(true);
                }}
              >
                Edit
              </button>
            </>
          )}
        </span>
      </div>
    );
  }

  if (!isPipelineEditorOpen) {
    return (
      <>
        <section className="panel pipeline-catalog">
          <div className="catalog-toolbar">
            <div>
              <span className="builder-kicker">Pipeline registry</span>
              <h2>Pipeline workflows</h2>
              <p>Create, inspect and open versioned workflows assigned to your Business Cases.</p>
            </div>
            <div className="catalog-toolbar-actions">
              <button className="secondary-button" type="button" onClick={() => setIsRunHistoryOpen(true)}>
                <History size={16} /> Runs history
              </button>
              <button className="primary-button" type="button" onClick={() => setIsCreatePipelineOpen(true)}>
                <Plus size={16} /> New pipeline
              </button>
            </div>
          </div>
          <div className="pipeline-table" role="table" aria-label="Pipelines">
            <div className="pipeline-table-row head" role="row">
              <span>Name</span><span>Business case</span><span>Purpose</span><span>Version</span><span>Status</span><span>Updated</span><span />
            </div>
            {activePipelines.map((item) => renderPipelineRow(item))}
            {!activePipelines.length && <div className="catalog-empty">No active pipelines. Create a workflow or copy one from the deprecated section.</div>}
          </div>
        </section>
        {deprecatedPipelines.length > 0 && (
          <details className="panel deprecated-pipelines-panel">
            <summary>
              <span>
                <strong>Deprecated pipelines</strong>
                <small>Preserved for audit and lineage. They cannot be edited or run.</small>
              </span>
              <i>{deprecatedPipelines.length}</i>
            </summary>
            <div className="pipeline-table" role="table" aria-label="Deprecated pipelines">
              <div className="pipeline-table-row head" role="row">
                <span>Name</span><span>Business case</span><span>Purpose</span><span>Version</span><span>Status</span><span>Updated</span><span />
              </div>
              {deprecatedPipelines.map((item) => renderPipelineRow(item, true))}
            </div>
          </details>
        )}
        {isCreatePipelineOpen && (
          <div className="modal-backdrop" role="presentation" onMouseDown={() => setIsCreatePipelineOpen(false)}>
            <form className="modal-dialog form-panel" onSubmit={createPipeline} onMouseDown={(event) => event.stopPropagation()}>
              <div className="modal-header">
                <div><span className="builder-kicker">Create workflow</span><h2>New pipeline</h2></div>
                <button className="icon-button" type="button" onClick={() => setIsCreatePipelineOpen(false)} aria-label="Close"><X size={17} /></button>
              </div>
              <label>Business case
                <select value={businessCaseId} onChange={(event) => setBusinessCaseId(event.target.value)} required>
                  <option value="">Choose BC</option>
                  {businessCases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <label>Name<input value={name} onChange={(event) => setName(event.target.value)} autoFocus required /></label>
              <label>Purpose
                <select value={pipelineType} onChange={(event) => setPipelineType(event.target.value)}>
                  <option value="custom">Custom workflow</option>
                  <option value="training">Training workflow</option>
                  <option value="batch_scoring">Scoring workflow</option>
                  <option value="monitoring">Monitoring workflow</option>
                </select>
              </label>
              <label>Description<textarea className="compact-textarea" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
              <div className="modal-actions">
                <button className="secondary-button" type="button" onClick={() => setIsCreatePipelineOpen(false)}>Cancel</button>
                <button className="primary-button" type="submit"><Plus size={16} /> Create pipeline</button>
              </div>
            </form>
          </div>
        )}
        {copyPipelineTarget && (
          <div className="modal-backdrop" role="presentation" onMouseDown={() => !isPipelineMutationSubmitting && setCopyPipelineTarget(null)}>
            <form className="modal-dialog form-panel" onSubmit={copyExistingPipeline} onMouseDown={(event) => event.stopPropagation()}>
              <div className="modal-header">
                <div><span className="builder-kicker">Reuse workflow</span><h2>Copy pipeline</h2></div>
                <button className="icon-button" type="button" disabled={isPipelineMutationSubmitting}
                  onClick={() => setCopyPipelineTarget(null)} aria-label="Close"><X size={17} /></button>
              </div>
              <p className="modal-copy-note">
                The current draft is copied when available; otherwise the latest published version is used.
                The copy stays in the same Business Case and starts as an editable draft v1.
              </p>
              <label>Name
                <input value={copyPipelineName} onChange={(event) => setCopyPipelineName(event.target.value)}
                  autoFocus required maxLength={200} />
              </label>
              <div className="modal-actions">
                <button className="secondary-button" type="button" disabled={isPipelineMutationSubmitting}
                  onClick={() => setCopyPipelineTarget(null)}>Cancel</button>
                <button className="primary-button" type="submit" disabled={isPipelineMutationSubmitting || !copyPipelineName.trim()}>
                  <Copy size={16} /> {isPipelineMutationSubmitting ? "Copying…" : "Copy pipeline"}
                </button>
              </div>
            </form>
          </div>
        )}
        {deletePipelineTarget && (
          <div className="modal-backdrop" role="presentation" onMouseDown={() => !isPipelineMutationSubmitting && setDeletePipelineTarget(null)}>
            <section className="modal-dialog form-panel" role="dialog" aria-modal="true"
              aria-label={`Delete pipeline ${deletePipelineTarget.name}`} onMouseDown={(event) => event.stopPropagation()}>
              <div className="modal-header">
                <div><span className="builder-kicker">Remove from registry</span><h2>Remove pipeline?</h2></div>
                <button className="icon-button" type="button" disabled={isPipelineMutationSubmitting}
                  onClick={() => setDeletePipelineTarget(null)} aria-label="Close"><X size={17} /></button>
              </div>
              <p className="modal-copy-note">
                If “{deletePipelineTarget.name}” has never run, it and its versions will be permanently deleted.
                If it has run history, it will be deprecated instead and moved to the collapsed historical section.
              </p>
              <div className="modal-actions">
                <button className="secondary-button" type="button" disabled={isPipelineMutationSubmitting}
                  onClick={() => setDeletePipelineTarget(null)}>Cancel</button>
                <button className="secondary-button danger-action" type="button" disabled={isPipelineMutationSubmitting}
                  onClick={deleteExistingPipeline}>
                  <Trash2 size={16} /> {isPipelineMutationSubmitting ? "Removing…" : "Remove pipeline"}
                </button>
              </div>
            </section>
          </div>
        )}
        {isRunHistoryOpen && (
          <PipelineRunHistoryDialog
            pipelines={pipelines}
            businessCases={businessCases}
            refreshKey={runHistoryRefreshKey}
            onClose={() => setIsRunHistoryOpen(false)}
            onDetails={setSelectedRunDetails}
            onExamineDataset={onExamineDataset}
          />
        )}
        {versionHistoryPipeline && (
          <PipelineVersionHistoryDialog
            pipeline={versionHistoryPipeline}
            businessCaseName={businessCaseName(businessCases, versionHistoryPipeline.business_case_id)}
            onClose={() => setVersionHistoryPipeline(null)}
          />
        )}
        {selectedRunDetails && (
          <PipelineRunDetailsDialog
            run={selectedRunDetails}
            onClose={() => setSelectedRunDetails(null)}
            onChanged={async () => {
              setRunHistoryRefreshKey((current) => current + 1);
            }}
          />
        )}
        {catalogRunDialog && (
          <div className="modal-backdrop" role="presentation" onMouseDown={() => {
            setCatalogRunDialog(null);
            if (!isCatalogRunSubmitting) setCatalogRunResult(null);
          }}>
            <form className="modal-dialog form-panel" onSubmit={submitCatalogRun} onMouseDown={(event) => event.stopPropagation()}>
              <div className="modal-header">
                <div>
                  <span className="builder-kicker">Run published pipeline</span>
                  <h2>{catalogRunDialog.pipeline.name}</h2>
                </div>
                <button className="icon-button" type="button"
                  onClick={() => { setCatalogRunDialog(null); if (!isCatalogRunSubmitting) setCatalogRunResult(null); }} aria-label="Close"><X size={17} /></button>
              </div>
              {catalogRunResult && (
                <div className={`catalog-run-monitor ${catalogRunResult.status}`}>
                  <span className={["queued", "running"].includes(catalogRunResult.status) ? "run-spinner" : "run-result-icon"}>
                    {catalogRunResult.status === "succeeded" ? "✓" : catalogRunResult.status === "failed" ? "!" : ""}
                  </span>
                  <div>
                    <strong>
                      {catalogRunResult.status === "queued" ? "Run queued" :
                        catalogRunResult.status === "running" ? "Pipeline is running" :
                          catalogRunResult.status === "succeeded" ? "Pipeline completed" : "Pipeline failed"}
                    </strong>
                    <span>Run {shortId(catalogRunResult.id)} · {catalogRunResult.processed_row_count ?? 0} processed rows</span>
                  </div>
                </div>
              )}
              {!catalogRunResult && catalogRunDialog.inputs.map((input) => {
                const versionsForInput = datasets
                  .filter((dataset) => dataset.logical_id === input.logicalId && dataset.status !== "deleted")
                  .sort((left, right) => right.version_number - left.version_number);
                const latest = versionsForInput[0];
                return (
                  <label key={input.key}>{input.name}
                    {input.policy === "latest" ? (
                      <input value={latest ? `Latest → v${latest.version_number}` : "No active version"} readOnly />
                    ) : (
                      <select
                        value={catalogRunSelections[input.key] ?? ""}
                        onChange={(event) => setCatalogRunSelections((current) => ({
                          ...current,
                          [input.key]: event.target.value
                        }))}
                        required
                      >
                        <option value="">Select version…</option>
                        {versionsForInput.map((dataset) => (
                          <option key={dataset.id} value={dataset.id}>
                            v{dataset.version_number} · {dataset.row_count ?? "?"} rows · {formatDateTime(dataset.created_at)}
                          </option>
                        ))}
                      </select>
                    )}
                    <small>{input.policy === "latest" ? "Resolved and recorded when the run is created." : "This run requires an explicit immutable version."}</small>
                  </label>
                );
              })}
              {!catalogRunResult && !catalogRunDialog.inputs.length && <p>This pipeline has no external dataset inputs.</p>}
              {catalogRunResult && !["queued", "running"].includes(catalogRunResult.status) && (
                <div className="catalog-run-outputs">
                  <strong>Created datasets</strong>
                  {catalogRunResult.output_manifest.filter((item) => item.dataset_id).map((item) => (
                    <div className="catalog-run-output" key={`${item.pipeline_step_id}:${item.output_id}`}>
                      <span>
                        <strong>{item.dataset_name || item.output_id}</strong>
                        <small>{item.pipeline_step_id} · {item.output_stage} · {item.row_count ?? 0} rows</small>
                      </span>
                      <i>v{item.version_number ?? 1}</i>
                    </div>
                  ))}
                  {catalogRunResult.status === "failed" && <p>{catalogRunResult.error_message}</p>}
                </div>
              )}
              <div className="modal-actions">
                <button className="secondary-button" type="button"
                  onClick={() => { setCatalogRunDialog(null); if (!isCatalogRunSubmitting) setCatalogRunResult(null); }}>
                  {isCatalogRunSubmitting ? "Run in background" : catalogRunResult ? "Close" : "Cancel"}
                </button>
                {!catalogRunResult && (
                  <button className="primary-button" type="submit" disabled={isCatalogRunSubmitting}>
                    <Play size={16} /> {isCatalogRunSubmitting ? "Starting…" : "Run pipeline"}
                  </button>
                )}
              </div>
            </form>
          </div>
        )}
      </>
    );
  }

  return (
    <section className="pipeline-editor-screen">
      <div className="pipeline-editor-toolbar">
        <button className="secondary-button" type="button" onClick={() => setIsPipelineEditorOpen(false)}>← Pipelines</button>
        <div className="pipeline-editor-title">
          <span className="builder-kicker">Pipeline editor</span>
          <div className="pipeline-name-display">
            <h2>{selectedPipeline?.name ?? "Pipeline"}</h2>
            {selectedPipeline && (
              <button
                className="icon-button"
                type="button"
                onClick={() => {
                  setPipelineNameDraft(selectedPipeline.name);
                  setPipelineDescriptionDraft(selectedPipeline.description);
                  setPipelineTypeDraft(selectedPipeline.type);
                  setIsRenamingPipeline(true);
                }}
                aria-label="Edit pipeline metadata"
                title="Edit pipeline metadata"
              >
                <Pencil size={15} />
              </button>
            )}
          </div>
          <small>{selectedPipeline ? businessCaseName(businessCases, selectedPipeline.business_case_id) : ""}</small>
        </div>
        <div className="editor-toolbar-actions">
          <button className="secondary-button" onClick={saveDraft} type="button" disabled={!hasDraft}><Save size={16} /> Save{isDefinitionDirty ? " *" : ""}</button>
          <button className="secondary-button" onClick={publishDraft} type="button" disabled={!hasDraft}><CheckCircle2 size={16} /> Publish</button>
          <button className="secondary-button" onClick={createNextDraft} type="button" disabled={hasDraft}><Plus size={16} /> New draft</button>
          <button className="secondary-button" onClick={() => runSelectedPipeline(true)} type="button" disabled={isRunActive || !hasDraft}><Play size={16} /> Dry-run</button>
          <button className="primary-button" onClick={() => selectedPipeline && openCatalogRunDialog(selectedPipeline)} type="button" disabled={isRunActive || !canRunPublishedVersion}><Play size={16} /> Run</button>
        </div>
      </div>
      {isRenamingPipeline && selectedPipeline && (
        <div className="modal-backdrop" role="presentation"
          onMouseDown={(event) => event.target === event.currentTarget && setIsRenamingPipeline(false)}>
          <form className="modal-dialog form-panel pipeline-metadata-dialog" onSubmit={renamePipeline}>
            <div className="modal-header">
              <div><span className="builder-kicker">Pipeline metadata</span><h2>Edit pipeline</h2></div>
              <button className="icon-button" type="button" onClick={() => setIsRenamingPipeline(false)}
                aria-label="Close pipeline metadata"><X size={17} /></button>
            </div>
            <label>Name<input value={pipelineNameDraft}
              onChange={(event) => setPipelineNameDraft(event.target.value)}
              maxLength={200} autoFocus required /></label>
            <label>Description<textarea className="compact-textarea"
              value={pipelineDescriptionDraft}
              onChange={(event) => setPipelineDescriptionDraft(event.target.value)}
              maxLength={4000} /></label>
            <label>Purpose<select value={pipelineTypeDraft}
              onChange={(event) => setPipelineTypeDraft(event.target.value)}>
              <option value="data_preparation">Data preparation</option>
              <option value="feature_engineering">Feature engineering</option>
              <option value="training">Training</option>
              <option value="batch_scoring">Batch scoring</option>
              <option value="monitoring">Monitoring</option>
              <option value="custom">Custom</option>
            </select></label>
            <div className="modal-actions">
              <button className="secondary-button" type="button" onClick={() => setIsRenamingPipeline(false)}
                disabled={isSavingPipelineName}>Cancel</button>
              <button className="primary-button" type="submit"
                disabled={isSavingPipelineName || !pipelineNameDraft.trim()}>
                <Save size={14} /> {isSavingPipelineName ? "Saving…" : "Save metadata"}
              </button>
            </div>
          </form>
        </div>
      )}

      {runFeedback && (
        <div className={`inline-run-feedback ${runFeedback.status}`} role="status" aria-live="polite">
          <span className={isRunActive ? "run-spinner" : "run-result-icon"}>
            {runFeedback.status === "succeeded" ? "✓" : runFeedback.status === "failed" ? "!" : ""}
          </span>
          <div><strong>{runFeedback.title}</strong><span>{runFeedback.detail}</span></div>
          {!isRunActive && <button className="icon-button" type="button" onClick={() => setRunFeedback(null)} aria-label="Dismiss"><X size={15} /></button>}
        </div>
      )}
      {activeStepRuns.length > 0 && (
        <div className="run-profile-summary" aria-label="Pipeline step run results">
          {activeStepRuns.map((stepRun) => (
            <span key={stepRun.id}>
              {stepRun.pipeline_step_id} · {stepRun.status} · {stepRun.processed_row_count ?? 0} rows
            </span>
          ))}
        </div>
      )}

      {hasDraft && hasPublished && (
        <div className="inline-run-feedback queued" role="note">
          <span className="run-result-icon">i</span>
          <div>
            <strong>Draft differs from the runnable published version</strong>
            <span>Use Dry-run for draft validation, then Publish before a full Run creates a persistent dataset.</span>
          </div>
        </div>
      )}

      {dryRunResult && (
        <DryRunPreview
          run={dryRunResult}
          onClose={() => setDryRunResult(null)}
          onExamine={(outputId, pipelineStepId) => setExaminedDryRun({
            run: dryRunResult,
            outputId,
            pipelineStepId
          })}
        />
      )}
      {examinedDryRun && (
        <DryRunExamination
          run={examinedDryRun.run}
          initialOutputId={examinedDryRun.outputId}
          initialPipelineStepId={examinedDryRun.pipelineStepId}
          onClose={() => setExaminedDryRun(null)}
          setNotice={setNotice}
        />
      )}
      {selectedRunDetails && selectedPipeline && (
        <PipelineRunDetailsDialog
          run={selectedRunDetails}
          onClose={() => setSelectedRunDetails(null)}
          onChanged={async () => {
            setRuns(await api.listPipelineRuns(selectedPipeline.id));
            setRunHistoryRefreshKey((current) => current + 1);
          }}
        />
      )}

      <div className="panel pipeline-canvas-panel">
        <DeferredPanel>
          <WorkflowEditor
            definition={workflowDefinition}
            businessCase={businessCases.find((item) => item.id === selectedBusinessCaseIdValue)}
            datasets={latestLogicalDatasetAliases(datasets)}
            dataAttachments={pipelineDataAttachments.map((attachment) => {
              const dataset = datasets.find((item) => item.id === attachment.data_asset_id);
              return dataset ? { ...attachment, data_asset_id: dataset.logical_id } : attachment;
            })}
            outputNameSuggestion={selectedPipeline?.name ?? "result"}
            onChange={updateWorkflowDefinition}
            disabled={!hasDraft}
          />
        </DeferredPanel>
      </div>

      <div className="editor-lower-grid">
        <details className="panel editor-details">
          <summary>Versions <span>{versions.length}</span></summary>
          <AssetList title="" assets={versions.map((item) => ({
            id: item.id,
            name: `v${item.version_number}`,
            meta: `hash ${item.definition_hash.slice(0, 12)} · ${item.published_at ? formatDateTime(item.published_at) : "not published"}`,
            status: item.status
          }))} />
        </details>
        <details className="panel editor-details" open>
          <summary>Recent runs <span>{runs.length}</span></summary>
          <AssetList title="" assets={runs.slice(0, 8).map((item) => ({
            id: item.id,
            name: `${item.is_dry_run ? "dry-run" : "run"} ${item.requested_step_id ? `step ${item.requested_step_id}` : "pipeline"} ${shortId(item.id)}`,
            meta: `${item.processed_row_count ?? 0} processed · ${item.output_row_count ?? 0} output rows`,
            status: item.status,
            actionLabel: "Details",
            onAction: () => setSelectedRunDetails(item)
          }))} />
        </details>
      </div>

      {workflowDefinition.steps.length > 0 && (
        <div className="step-run-dock">
          {workflowDefinition.steps.map((step) => (
            <span key={step.step_id}>
              <strong>{step.name}</strong>
              <small>Runs required ancestors and stops after this step</small>
              <button className="secondary-button" onClick={() => runSelectedPipeline(true, step.step_id)}
                type="button" disabled={isRunActive || !hasDraft}>
                <Play size={16} /> Dry-run
              </button>
              <button className="secondary-button" onClick={() => runSelectedPipeline(false, step.step_id)}
                type="button" disabled={isRunActive || !canRunPublishedVersion}>
                <Play size={16} /> Run
              </button>
            </span>
          ))}
        </div>
      )}

      <details className="advanced-json editor-json">
        <summary>Advanced JSON definition</summary>
        <p>The diagram and JSON use the same DAG contract.</p>
        <textarea className="json-input" value={definitionText} onChange={(event) => updateDefinitionText(event.target.value)} disabled={!hasDraft} />
      </details>
      {catalogRunDialog && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => {
          setCatalogRunDialog(null);
          if (!isCatalogRunSubmitting) setCatalogRunResult(null);
        }}>
          <form className="modal-dialog form-panel" onSubmit={submitCatalogRun} onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div><span className="builder-kicker">Run published pipeline</span><h2>{catalogRunDialog.pipeline.name}</h2></div>
              <button className="icon-button" type="button"
                onClick={() => { setCatalogRunDialog(null); if (!isCatalogRunSubmitting) setCatalogRunResult(null); }} aria-label="Close"><X size={17} /></button>
            </div>
            {catalogRunResult && (
              <div className={`catalog-run-monitor ${catalogRunResult.status}`}>
                <span className={["queued", "running"].includes(catalogRunResult.status) ? "run-spinner" : "run-result-icon"}>
                  {catalogRunResult.status === "succeeded" ? "✓" : catalogRunResult.status === "failed" ? "!" : ""}
                </span>
                <div>
                  <strong>
                    {catalogRunResult.status === "queued" ? "Run queued" :
                      catalogRunResult.status === "running" ? "Pipeline is running" :
                        catalogRunResult.status === "succeeded" ? "Pipeline completed" : "Pipeline failed"}
                  </strong>
                  <span>Run {shortId(catalogRunResult.id)} · {catalogRunResult.processed_row_count ?? 0} processed rows</span>
                </div>
              </div>
            )}
            {!catalogRunResult && catalogRunDialog.inputs.map((input) => {
              const versionsForInput = datasets
                .filter((dataset) => dataset.logical_id === input.logicalId && dataset.status !== "deleted")
                .sort((left, right) => right.version_number - left.version_number);
              const latest = versionsForInput[0];
              return (
                <label key={input.key}>{input.name}
                  {input.policy === "latest" ? (
                    <input value={latest ? `Latest → v${latest.version_number}` : "No active version"} readOnly />
                  ) : (
                    <select value={catalogRunSelections[input.key] ?? ""}
                      onChange={(event) => setCatalogRunSelections((current) => ({ ...current, [input.key]: event.target.value }))}
                      required>
                      <option value="">Select version…</option>
                      {versionsForInput.map((dataset) => (
                        <option key={dataset.id} value={dataset.id}>
                          v{dataset.version_number} · {dataset.row_count ?? "?"} rows · {formatDateTime(dataset.created_at)}
                        </option>
                      ))}
                    </select>
                  )}
                  <small>{input.policy === "latest" ? "Resolved and recorded when the run is created." : "This run requires an explicit immutable version."}</small>
                </label>
              );
            })}
            {catalogRunResult && !["queued", "running"].includes(catalogRunResult.status) && (
              <div className="catalog-run-outputs">
                <strong>Created datasets</strong>
                {catalogRunResult.output_manifest.filter((item) => item.dataset_id).map((item) => (
                  <div className="catalog-run-output" key={`${item.pipeline_step_id}:${item.output_id}`}>
                    <span><strong>{item.dataset_name || item.output_id}</strong>
                      <small>{item.pipeline_step_id} · {item.output_stage} · {item.row_count ?? 0} rows</small></span>
                    <i>v{item.version_number ?? 1}</i>
                  </div>
                ))}
                {catalogRunResult.status === "failed" && <p>{catalogRunResult.error_message}</p>}
              </div>
            )}
            <div className="modal-actions">
              <button className="secondary-button" type="button"
                onClick={() => { setCatalogRunDialog(null); if (!isCatalogRunSubmitting) setCatalogRunResult(null); }}>
                {isCatalogRunSubmitting ? "Run in background" : catalogRunResult ? "Close" : "Cancel"}
              </button>
              {!catalogRunResult && (
                <button className="primary-button" type="submit" disabled={isCatalogRunSubmitting}>
                  <Play size={16} /> {isCatalogRunSubmitting ? "Starting…" : "Run pipeline"}
                </button>
              )}
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

function DryRunExamination({
  run,
  initialOutputId,
  initialPipelineStepId,
  onClose,
  setNotice
}: {
  run: PipelineRun;
  initialOutputId: string;
  initialPipelineStepId: string;
  onClose: () => void;
  setNotice: (message: string) => void;
}) {
  const timestamp = run.finished_at ?? run.created_at;
  const profileCache = useRef(new Map<string, DescriptiveProfileCacheEntry>());
  const outputs = useMemo(() => browsableDryRunOutputs(run), [run]);
  const temporaryDatasets = useMemo<DataAsset[]>(() => outputs.map((output) => {
    const outputId = output.output_id;
    const pipelineStepId = output.pipeline_step_id ?? "";
    const assetId = temporaryPipelineOutputId(run.id, outputId, pipelineStepId);
    return {
      id: assetId,
      owner_id: "",
      name: `${pipelineStepId || "Pipeline"} · ${output.dataset_name || outputId}`,
      source_type: "file",
      format: "parquet",
      logical_id: assetId,
      version_number: 1,
      version_stage: output.output_stage ?? "intermediate",
      description: "Read-only temporary pipeline output",
      original_filename: null,
      location_uri: null,
      file_size_bytes: output.file_size_bytes ?? null,
      row_count: output.row_count ?? 0,
      has_header: null,
      uploaded_by: null,
      uploaded_at: timestamp,
      deleted_by: null,
      deleted_at: null,
      status: "ready",
      tags: ["temporary", "dry-run"],
      metadata: {
        temporary: true,
        pipeline_id: run.pipeline_id,
        pipeline_run_id: run.id,
        pipeline_step_id: pipelineStepId,
        output_id: outputId,
        scope: "full"
      },
      created_at: run.created_at,
      updated_at: timestamp
    };
  }), [outputs, run.created_at, run.id, run.pipeline_id, timestamp]);
  const initialDatasetId = temporaryPipelineOutputId(
    run.id,
    initialOutputId,
    initialPipelineStepId
  );
  const totalRows = temporaryDatasets.reduce((sum, dataset) => sum + (dataset.row_count ?? 0), 0);

  return (
    <div className="modal-backdrop dry-run-examine-backdrop" role="presentation">
      <section className="dry-run-examine-dialog" role="dialog" aria-modal="true" aria-label="Examine dry-run output">
        <header className="modal-header dry-run-examine-header">
          <div>
            <p className="eyebrow">Temporary results · full scope · {temporaryDatasets.length} objects · {totalRows} rows</p>
            <h2>Examine dry-run outputs</h2>
            <p>Switch result objects, profile them, and build visualizations without creating official datasets or artifacts.</p>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close examination">
            <X size={18} />
          </button>
        </header>
        <div className="dry-run-examine-content">
          <AnalysisPanel
            datasets={temporaryDatasets}
            descriptiveProfileCache={profileCache.current}
            onRefresh={async () => undefined}
            setNotice={setNotice}
            initialDatasetId={initialDatasetId}
            initialTab="browse"
            showDataRoles={false}
            allowPersistence={false}
          />
        </div>
        <footer className="dry-run-examine-footer">
          Temporary Parquet · access follows the pipeline run · no official dataset or artifact was created. Drag the bottom-right corner to resize.
        </footer>
        <span className="dry-run-examine-resize-hint" aria-hidden="true" title="Drag to resize" />
      </section>
    </div>
  );
}

function businessCaseName(businessCases: BusinessCase[], businessCaseId: string) {
  return businessCases.find((item) => item.id === businessCaseId)?.name ?? "unknown BC";
}

function pipelineName(pipelines: Pipeline[], pipelineId: string) {
  return pipelines.find((item) => item.id === pipelineId)?.name ?? "unknown pipeline";
}

function latestModelFamilies(models: ModelArtifact[]) {
  const latest = new Map<string, ModelArtifact>();
  for (const model of models) {
    const current = latest.get(model.logical_id);
    if (!current || model.version_number > current.version_number) {
      latest.set(model.logical_id, model);
    }
  }
  return [...latest.values()].sort((left, right) => right.created_at.localeCompare(left.created_at));
}

function latestReportFamilies(reports: ScoringReport[]) {
  const latest = new Map<string, ScoringReport>();
  for (const report of reports) {
    const current = latest.get(report.logical_id);
    if (!current || report.version_number > current.version_number) {
      latest.set(report.logical_id, report);
    }
  }
  return [...latest.values()].sort((left, right) => right.created_at.localeCompare(left.created_at));
}

function DatasetVersionHistoryDialog({
  dataset,
  versions,
  onClose,
  onOpen
}: {
  dataset: DataAsset;
  versions: DataAsset[];
  onClose: () => void;
  onOpen: (datasetId: string) => void;
}) {
  const ordered = [...versions].sort((left, right) => right.version_number - left.version_number);
  return (
    <div className="modal-backdrop" role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog model-version-dialog" role="dialog" aria-modal="true"
        aria-label={`Versions of ${dataset.name}`}>
        <div className="modal-header">
          <div><span className="builder-kicker">Dataset family</span><h2>{dataset.name}</h2>
            <p>{ordered.length} immutable versions</p></div>
          <button className="icon-button" type="button" onClick={onClose}
            aria-label="Close dataset versions"><X size={17} /></button>
        </div>
        <div className="model-version-list">
          {ordered.map((version, index) => (
            <article key={version.id}>
              <div className="model-version-marker"><span>v{version.version_number}</span></div>
              <div><strong>v{version.version_number}
                {index === 0 && <i className="pipeline-status published">latest</i>}</strong>
                <span>{formatDateTime(version.created_at)} · {version.row_count ?? "?"} rows</span>
                <small>{version.format.toUpperCase()} · {version.version_stage}</small></div>
              <button className="secondary-button compact-button" type="button"
                onClick={() => onOpen(version.id)}>
                <BarChart3 size={14} /> Analyze
              </button>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

function DataPanel({
  datasets,
  onAnalyze,
  onRefresh,
  setNotice
}: {
  datasets: DataAsset[];
  onAnalyze: (datasetId: string) => void;
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [uploadLogicalId, setUploadLogicalId] = useState("");
  const activeDatasets = datasets.filter((dataset) => dataset.status !== "deleted" && !isDataView(dataset));
  const dataViews = datasets.filter((dataset) => dataset.status !== "deleted" && isDataView(dataset));
  const deletedDatasets = datasets.filter((dataset) => dataset.status === "deleted");

  function selectDatasetFile(nextFile: File | null) {
    if (!nextFile) {
      setFile(null);
      return;
    }
    if (!/\.(csv|parquet)$/i.test(nextFile.name)) {
      setNotice("Choose a .csv or .parquet dataset file");
      return;
    }
    setFile(nextFile);
    if (!name.trim()) {
      setName(nextFile.name.replace(/\.(csv|parquet)$/i, ""));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setNotice("Choose a CSV or Parquet file first");
      return;
    }
    if (!name.trim()) {
      setNotice("Enter dataset name");
      return;
    }

    const formData = new FormData();
    formData.set("file", file);
    formData.set("name", name.trim());
    formData.set("description", description);
    formData.set("tags", tags);
    if (uploadLogicalId) formData.set("logical_id", uploadLogicalId);

    setIsUploadingFile(true);
    try {
      const uploaded = await api.uploadDataset(formData);
      setNotice(
        `Uploaded ${uploaded.name} v${uploaded.version_number}: ${uploaded.row_count ?? 0} rows · ${uploaded.format.toUpperCase()} · full dataset`
      );
      setName("");
      setDescription("");
      setTags("");
      setFile(null);
      setUploadLogicalId("");
      setFileInputKey((current) => current + 1);
      await onRefresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Dataset upload failed");
    } finally {
      setIsUploadingFile(false);
    }
  }

  async function deleteDataset(dataset: DataAsset) {
    const deleted = await api.deleteDataset(dataset.id);
    setNotice(`Deleted ${deleted.name}`);
    await onRefresh();
  }

  function addDatasetVersion(dataset: DataAsset) {
    setUploadLogicalId(dataset.logical_id);
    setName(dataset.name);
    setDescription(dataset.description);
    setTags(dataset.tags.join(", "));
    setFile(null);
    setFileInputKey((current) => current + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <section className="two-column">
      <form className="panel form-panel" onSubmit={submit}>
        <div className="panel-header">
          <div>
            <h2>{uploadLogicalId ? `Add version of ${name}` : "Upload dataset from file"}</h2>
            <p className="dataset-upload-subtitle">
              {uploadLogicalId ? "Register a new immutable version of this logical dataset." : "Register a complete CSV or Parquet dataset."}
            </p>
          </div>
          <Upload size={18} />
        </div>
        <label>
          Dataset name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Suggested from the selected filename"
            required
            disabled={Boolean(uploadLogicalId)}
          />
        </label>
        <label
          className={`dataset-file-picker ${isDraggingFile ? "dragging" : ""} ${file ? "selected" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDraggingFile(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setIsDraggingFile(false);
            }
          }}
          onDrop={(event) => {
            event.preventDefault();
            setIsDraggingFile(false);
            selectDatasetFile(event.dataTransfer.files?.[0] ?? null);
          }}
        >
          <input
            accept=".csv,.parquet,text/csv,application/vnd.apache.parquet"
            className="dataset-file-input"
            key={fileInputKey}
            onChange={(event) => selectDatasetFile(event.target.files?.[0] ?? null)}
            required
            type="file"
          />
          <span className="dataset-file-picker-icon"><Upload size={22} /></span>
          {file ? (
            <span className="dataset-file-selection">
              <strong>{file.name}</strong>
              <small>
                <em>{file.name.toLowerCase().endsWith(".parquet") ? "PARQUET" : "CSV"}</em>
                {formatBytes(file.size)}
              </small>
            </span>
          ) : (
            <span className="dataset-file-selection">
              <strong>Drop a dataset file here</strong>
              <small>or click to browse · CSV and Parquet</small>
            </span>
          )}
        </label>
        <div className="dataset-format-guidance">
          <span><strong>CSV</strong><small>UTF-8 tabular data; converted to a reusable columnar cache for analytics.</small></span>
          <span><strong>Parquet</strong><small>Used natively with schema and column types preserved.</small></span>
        </div>
        <label>
          Description
          <textarea
            className="compact-textarea"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label>
          Tags
          <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Comma-separated, optional" />
        </label>
        <div className="dataset-upload-scope">
          <CheckCircle2 size={15} />
          Full file will be registered. Upload does not silently sample rows.
        </div>
        <button className="primary-button" type="submit" disabled={isUploadingFile}>
          <Upload size={16} />
          {isUploadingFile ? "Uploading and validating…" : "Upload dataset"}
        </button>
        {uploadLogicalId && (
          <button className="secondary-button" type="button" onClick={() => {
            setUploadLogicalId("");
            setName("");
            setDescription("");
            setTags("");
            setFile(null);
            setFileInputKey((current) => current + 1);
          }}>
            Cancel new version
          </button>
        )}
      </form>

      <div className="repository-column">
        <VersionedDatasetList
          datasets={activeDatasets}
          onAddVersion={addDatasetVersion}
          onAnalyze={onAnalyze}
          onDelete={deleteDataset}
        />
        <AssetList
          title="Data views"
          assets={dataViews.map((item) => ({
            id: item.id,
            name: item.name,
            meta: dataViewMeta(item),
            status: item.status,
            canDelete: true,
            onDelete: () => deleteDataset(item)
          }))}
        />
        {deletedDatasets.length > 0 && (
          <details className="panel editor-details deleted-assets-panel">
            <summary>Deleted datasets <span>{deletedDatasets.length}</span></summary>
            <AssetList
              title=""
              assets={deletedDatasets.map((item) => ({
                id: item.id,
                name: item.name,
                meta: datasetMeta(item),
                status: item.status
              }))}
            />
          </details>
        )}
      </div>
    </section>
  );
}

function datasetMeta(item: DataAsset) {
  return [
    item.original_filename ?? `${item.source_type}.${item.format}`,
    `${item.row_count ?? 0} rows`,
    item.file_size_bytes == null ? null : formatBytes(item.file_size_bytes),
    headerLabel(item.has_header),
    item.deleted_at ? `deleted ${formatDateTime(item.deleted_at)}` : null,
    item.deleted_by ? `by ${shortId(item.deleted_by)}` : null
  ].filter(Boolean).join(" / ");
}

function VersionedDatasetList({
  datasets,
  onAddVersion,
  onAnalyze,
  onDelete
}: {
  datasets: DataAsset[];
  onAddVersion: (dataset: DataAsset) => void;
  onAnalyze: (datasetId: string) => void;
  onDelete: (dataset: DataAsset) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const groups = datasetVersionGroups(datasets);
  return (
    <div className="panel">
      <div className="panel-header"><h2>Active datasets</h2></div>
      <div className="asset-list">
        {groups.map(({ logicalId, latest, versions }) => {
          const isExpanded = expanded.has(logicalId);
          return (
            <div className="dataset-version-group" key={logicalId}>
              <div className="asset-row">
                <div>
                  <strong>{latest.name} <i className="version-badge">v{latest.version_number}</i></strong>
                  <span>{datasetMeta(latest)} / {versions.length} version{versions.length === 1 ? "" : "s"} / {latest.version_stage}</span>
                </div>
                <div className="asset-actions">
                  <em>{latest.status}</em>
                  <button className="secondary-button compact-button" type="button"
                    onClick={() => onAnalyze(latest.id)}>
                    <BarChart3 size={14} /> Analyze latest
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => {
                    setExpanded((current) => {
                      const next = new Set(current);
                      if (next.has(logicalId)) next.delete(logicalId); else next.add(logicalId);
                      return next;
                    });
                  }}>
                    Versions ({versions.length})
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => onAddVersion(latest)}>
                    <Plus size={14} /> Add version
                  </button>
                </div>
              </div>
              {isExpanded && (
                <div className="dataset-version-history">
                  {[...versions].sort((a, b) => b.version_number - a.version_number).map((version) => (
                    <div className="asset-row version-row" key={version.id}>
                      <div>
                        <strong>v{version.version_number} {version.id === latest.id ? "· latest" : ""}</strong>
                        <span>{datasetMeta(version)} / created {formatDateTime(version.created_at)}</span>
                      </div>
                      <div className="asset-actions">
                        <em>{version.version_stage}</em>
                        <button className="secondary-button compact-button" type="button"
                          onClick={() => onAnalyze(version.id)}>
                          <BarChart3 size={14} /> Analyze
                        </button>
                        <button
                          aria-label={`Delete ${version.name} v${version.version_number}`}
                          className="icon-button danger-icon"
                          onClick={() => onDelete(version)}
                          title="Delete this dataset version"
                          type="button"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {!groups.length && <div className="empty-state">Nothing registered yet</div>}
      </div>
    </div>
  );
}

function datasetVersionGroups(datasets: DataAsset[]) {
  const grouped = new Map<string, DataAsset[]>();
  for (const dataset of datasets) {
    const logicalId = dataset.logical_id || dataset.id;
    grouped.set(logicalId, [...(grouped.get(logicalId) ?? []), dataset]);
  }
  return [...grouped.entries()]
    .map(([logicalId, versions]) => ({
      logicalId,
      versions,
      latest: [...versions].sort((a, b) => b.version_number - a.version_number)[0]
    }))
    .sort((left, right) => right.latest.created_at.localeCompare(left.latest.created_at));
}

function latestLogicalDatasetAliases(datasets: DataAsset[]) {
  return datasetVersionGroups(
    datasets.filter((dataset) => dataset.status !== "deleted")
  ).map(({ logicalId, latest }) => ({ ...latest, id: logicalId }));
}

function datasetVersionLabel(dataset: DataAsset, datasets: DataAsset[]) {
  const versions = datasets.filter(
    (item) => item.logical_id === dataset.logical_id && item.status !== "deleted"
  );
  const latest = Math.max(...versions.map((item) => item.version_number), dataset.version_number);
  return `${dataset.name} · v${dataset.version_number}${dataset.version_number === latest ? " (latest)" : ""}`;
}

function isDataView(item: DataAsset) {
  return item.source_type === "view" || item.format === "view" || Boolean(asRecord(item.metadata.data_view).source_dataset_id);
}

function dataViewMeta(item: DataAsset) {
  const metadata = asRecord(item.metadata.data_view);
  const sourceName = asString(metadata.source_dataset_name) || "unknown source";
  const rowCount = typeof metadata.row_count === "number" ? metadata.row_count : item.row_count ?? 0;
  const columnCount = typeof metadata.column_count === "number" ? metadata.column_count : 0;
  const createdBy = asString(metadata.created_by) || item.uploaded_by || item.owner_id;
  const createdAt = asString(metadata.created_at) || item.created_at;
  return [
    `source: ${sourceName}`,
    `${rowCount} rows`,
    `${columnCount} columns`,
    `created by ${shortId(createdBy)}`,
    `created ${formatDateTime(createdAt)}`
  ].join(" / ");
}

function headerLabel(hasHeader: boolean | null) {
  if (hasHeader === null) {
    return "headers unknown";
  }
  return hasHeader ? "headers detected" : "no headers detected";
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}

function durationLabel(startedAt: string | null | undefined, finishedAt: string | null | undefined) {
  if (!startedAt) return "not started";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function shortId(value: string) {
  return value.slice(0, 8);
}

function AnalysisPanel({
  datasets,
  businessCases = [],
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
  const [analysisAttachments, setAnalysisAttachments] = useState<BusinessCaseDataAttachment[]>([]);
  const [visualizationDrill, setVisualizationDrill] = useState<VisualizationDrillRequest | null>(null);
  useEffect(() => {
    if (!businessCaseFilter) {
      setAnalysisAttachments([]);
      return;
    }
    let active = true;
    api.listBusinessCaseDataAttachments(businessCaseFilter)
      .then((items) => active && setAnalysisAttachments(items))
      .catch((error) => active && setNotice(
        error instanceof Error ? error.message : "Could not load Business Case datasets"
      ));
    return () => { active = false; };
  }, [businessCaseFilter, setNotice]);
  const availableDatasets = useMemo(() => {
    const active = datasets.filter((dataset) => dataset.status !== "deleted");
    const byId = new Map(active.map((dataset) => [dataset.id, dataset]));
    const logicalIds = new Set(
      analysisAttachments
        .map((attachment) => byId.get(attachment.data_asset_id)?.logical_id)
        .filter((value): value is string => Boolean(value))
    );
    const scoped = businessCaseFilter
      ? active.filter((dataset) => logicalIds.has(dataset.logical_id))
      : active;
    return showOnlyLatest
      ? datasetVersionGroups(scoped).map((group) => group.latest)
      : scoped.sort((left, right) =>
          left.name.localeCompare(right.name) || right.version_number - left.version_number
        );
  }, [analysisAttachments, businessCaseFilter, datasets, showOnlyLatest]);

  useEffect(() => {
    const nextDatasetId = availableDatasets.some((dataset) => dataset.id === datasetId)
      ? datasetId
      : availableDatasets[0]?.id ?? "";
    if (nextDatasetId !== datasetId) {
      setDatasetId(nextDatasetId);
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
            <span>Business Case</span>
            <select value={businessCaseFilter} onChange={(event) => setBusinessCaseFilter(event.target.value)}>
              <option value="">All Business Cases</option>
              {businessCases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="analysis-latest-toggle">
            <input type="checkbox" checked={showOnlyLatest}
              onChange={(event) => setShowOnlyLatest(event.target.checked)} />
            <span><strong>Show only latest versions</strong>
              <small>Collapse each logical dataset family to its newest version.</small></span>
          </label>
          <span>{availableDatasets.length} datasets available</span>
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
      )}
      {activeAnalysisTab === "descriptive" && (
        <DescriptiveAnalysisPanel
          datasets={availableDatasets}
          datasetId={datasetId}
          profileCache={descriptiveProfileCache}
          setDatasetId={setDatasetId}
          setNotice={setNotice}
        />
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

function DataRolesPanel({
  datasets,
  datasetId,
  setDatasetId,
  onRefresh,
  setNotice
}: {
  datasets: DataAsset[];
  datasetId: string;
  setDatasetId: (datasetId: string) => void;
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
}) {
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [metadata, setMetadata] = useState<DataRolesMetadata>(emptyRolesMetadata);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const selectedDataset = datasets.find((dataset) => dataset.id === datasetId) ?? null;
  const columns = preview?.columns ?? [];

  useEffect(() => {
    setMetadata(readRolesMetadata(selectedDataset, datasets, columns.map((column) => column.name)));
  }, [columns, datasets, selectedDataset]);

  useEffect(() => {
    if (!datasetId) {
      setPreview(null);
      return;
    }

    let isCurrent = true;
    setIsLoading(true);
    api
      .previewDataset(datasetId)
      .then((result) => {
        if (isCurrent) {
          setPreview(result);
        }
      })
      .catch((error) => {
        if (!isCurrent) {
          return;
        }
        const message = error instanceof Error ? error.message : "Dataset preview failed";
        setPreview(null);
        setNotice(message);
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [datasetId]);

  function toggleDatasetRole(role: string) {
    setMetadata((current) => ({
      ...current,
      dataset_roles: current.dataset_roles.includes(role)
        ? current.dataset_roles.filter((item) => item !== role)
        : [...current.dataset_roles, role]
    }));
  }

  function updateColumnRole(column: string, role: string) {
    setMetadata((current) => ({
      ...current,
      column_roles: {
        ...current.column_roles,
        [column]: role
      },
      entity_id_column: role === "identifier" ? column : current.entity_id_column,
      timestamp_column: role === "timestamp" ? column : current.timestamp_column,
      period_column: role === "period_id" ? column : current.period_column,
      target_column: role === "target" ? column : current.target_column
    }));
  }

  async function saveMetadata() {
    if (!selectedDataset) {
      setNotice("Choose a dataset first");
      return;
    }
    setIsSaving(true);
    try {
      await api.updateDatasetMetadata(selectedDataset.id, {
        ...selectedDataset.metadata,
        data_roles: normalizeRolesMetadata(metadata, columns.map((column) => column.name))
      });
      await onRefresh();
      setNotice(`Saved Data Roles for ${selectedDataset.name}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Saving Data Roles failed");
    } finally {
      setIsSaving(false);
    }
  }

  if (datasets.length === 0) {
    return (
      <div className="panel">
        <div className="empty-state">No datasets available</div>
      </div>
    );
  }

  return (
    <div className="panel data-roles-panel">
      <div className="roles-toolbar">
        <label>
          Dataset
          <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {datasetVersionLabel(dataset, datasets)}
              </option>
            ))}
          </select>
        </label>
        <button className="primary-button toolbar-button" disabled={isSaving} onClick={saveMetadata} type="button">
          <Save size={16} />
          {isSaving ? "Saving" : "Save roles"}
        </button>
      </div>

      <section className="roles-section">
        <div className="panel-header compact-header">
          <h2>Dataset role</h2>
        </div>
        <div className="role-choice-grid">
          {datasetRoleOptions.map((option) => (
            <label className="check-tile" key={option.value}>
              <input
                checked={metadata.dataset_roles.includes(option.value)}
                onChange={() => toggleDatasetRole(option.value)}
                type="checkbox"
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="roles-section role-shortcuts">
        <label>
          Entity ID
          <ColumnSelect
            columns={columns}
            value={metadata.entity_id_column}
            onChange={(value) => setMetadata((current) => ({ ...current, entity_id_column: value }))}
          />
        </label>
        <label>
          Timestamp
          <ColumnSelect
            columns={columns}
            value={metadata.timestamp_column}
            onChange={(value) => setMetadata((current) => ({ ...current, timestamp_column: value }))}
          />
        </label>
        <label>
          Period/batch
          <ColumnSelect
            columns={columns}
            value={metadata.period_column}
            onChange={(value) => setMetadata((current) => ({ ...current, period_column: value }))}
          />
        </label>
        <label>
          Target
          <ColumnSelect
            columns={columns}
            value={metadata.target_column}
            onChange={(value) => setMetadata((current) => ({ ...current, target_column: value }))}
          />
        </label>
      </section>

      <section className="roles-section">
        <div className="panel-header compact-header">
          <h2>Column roles</h2>
          {isLoading && <span className="muted-text">Loading columns</span>}
        </div>
        <div className="column-role-list">
          {columns.map((column) => (
            <div className="column-role-row" key={column.name}>
              <div>
                <strong>{column.name}</strong>
                <span>{column.type}</span>
              </div>
              <select
                value={metadata.column_roles[column.name] ?? defaultColumnRole(column.type)}
                onChange={(event) => updateColumnRole(column.name, event.target.value)}
              >
                {columnRoleOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
          {!isLoading && columns.length === 0 && (
            <div className="empty-state">No columns detected for this dataset</div>
          )}
        </div>
      </section>

      <label>
        Notes
        <textarea
          className="compact-textarea"
          value={metadata.notes}
          onChange={(event) => setMetadata((current) => ({ ...current, notes: event.target.value }))}
        />
      </label>
    </div>
  );
}

function ColumnSelect({
  columns,
  value,
  onChange
}: {
  columns: DatasetPreview["columns"];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">Not set</option>
      {columns.map((column) => (
        <option key={column.name} value={column.name}>
          {column.name}
        </option>
      ))}
    </select>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

type SortDirection = "asc" | "desc";
type SortRule = {
  column: string;
  direction: SortDirection;
};
type FilterOperator = BrowserFilterConfig["operator"];
type ColumnFilterConfig = BrowserFilterConfig;
const DATA_BROWSER_DRILL_PREVIEW_LIMIT = 5_000;
type DatasetCellValue = string | number | boolean | null;
type GroupingRole = "none" | "group" | "aggregate";
type AggregationFunction =
  | "count"
  | "count_non_empty"
  | "unique_count"
  | "sum"
  | "average"
  | "min"
  | "max"
  | "median"
  | "mode"
  | "first"
  | "last";

type GroupingColumnConfig = {
  role: GroupingRole;
  aggregate: AggregationFunction;
};

type AggregatedColumn = {
  name: string;
  type: DatasetPreview["columns"][number]["type"];
  sourceColumn?: string;
};

const groupingRoleOptions: Array<{ value: GroupingRole; label: string }> = [
  { value: "none", label: "Not used" },
  { value: "group", label: "Group column" },
  { value: "aggregate", label: "Aggregate column" }
];

const aggregationFunctionLabels: Record<AggregationFunction, string> = {
  count: "Count rows",
  count_non_empty: "Count values",
  unique_count: "Unique count",
  sum: "Sum",
  average: "Average",
  min: "Minimum",
  max: "Maximum",
  median: "Median",
  mode: "Most frequent",
  first: "First value",
  last: "Last value"
};

const filterOperatorLabels: Record<FilterOperator, string> = {
  contains: "Contains",
  equals: "Equals",
  not_equals: "Not equals",
  in: "In",
  regex: "Regex",
  starts_with: "Starts with",
  ends_with: "Ends with",
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
  between: "Between",
  empty: "Is empty",
  not_empty: "Is not empty"
};

type ColumnProfile = {
  name: string;
  type: DatasetPreview["columns"][number]["type"];
  role: string;
  count: number;
  missing: number;
  missingRate: number;
  unique: number;
  uniqueRate: number;
  mean: number | null;
  median: number | null;
  minimum: DatasetCellValue;
  maximum: DatasetCellValue;
  stdDev: number | null;
  mode: DatasetCellValue;
  topValues: Array<{ value: DatasetCellValue; count: number; share: number }>;
  histogram: Array<{ label: string; count: number; share: number }>;
  examples: DatasetCellValue[];
  notes: string[];
};

type TargetRelationProfile = {
  feature: string;
  role: string;
  type: DatasetPreview["columns"][number]["type"];
  kind: string;
  score: number;
  signal: string;
  detail: string;
  comparisonColumn: string;
  groupStats: NumericGroupStats[];
  densityPlot: DensityPlot | null;
  numericStats: NumericRelationStats | null;
  scatterPlot: ScatterPlot | null;
  categoricalStats: CategoricalRelationStats | null;
};

type CategoricalRelationStats = {
  comparisonValues: string[];
  rows: Array<{
    featureValue: string;
    count: number;
    cells: Array<{
      comparisonValue: string;
      count: number;
      rowShare: number;
      lift: number;
      residual: number;
    }>;
  }>;
  chiSquare: number;
  degreesFreedom: number;
  cramersV: number;
  sparseCellShare: number;
  ordinalTrend: {
    focusValue: string;
    spearman: number;
    orderBasis: string;
  } | null;
  graphicSummaries: boolean;
};

type NumericGroupStats = {
  group: string;
  count: number;
  minimum: number;
  maximum: number;
  median: number;
  mean: number;
  stdDev: number;
  color: string;
};

type DensityPlot = {
  xMin: number;
  xMax: number;
  yMax: number;
  series: DensitySeries[];
};

type DensitySeries = {
  group: string;
  color: string;
  points: Array<{
    x: number;
    y: number;
  }>;
};

type NumericRelationStats = {
  pearson: number;
  spearman: number;
  rSquared: number;
  covariance: number;
  slope: number;
  intercept: number;
};

type ScatterPlot = {
  xColumn: string;
  yColumn: string;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  points: Array<{ x: number; y: number }>;
  trendLine: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  } | null;
};

type SegmentResult = {
  columns: string[];
  segment: string;
  count: number;
  support: number;
  targetValue: string;
  baseline: number;
  segmentValue: number;
  difference: number;
  relativeLift: number | null;
  confidenceInterval: [number, number] | null;
  effectSize: number | null;
  score: number;
  format: "number" | "percent";
};

type SegmentProfile = {
  targetColumn: string;
  targetType: EffectiveTargetType;
  candidateFeatures: string[];
  pairsScanned: number;
  segmentsEvaluated: number;
  minimumSegmentSize: number;
  graphicSummaries: boolean;
  results: SegmentResult[];
};

type TargetTypeSetting = "auto" | "categorical" | "continuous";
type EffectiveTargetType = "categorical" | "continuous";

type ProfilingRangeSettings = {
  includeSummary: boolean;
  includeUnivariate: boolean;
  includeTargetRelations: boolean;
  includeSegments: boolean;
  includeGraphicSummaries: boolean;
  rowLimit: number;
  maxTargetFeatures: number;
  maxSegmentFeatures: number;
};

type DescriptiveProfileCacheEntry = {
  datasetUpdatedAt: string;
  preview: DatasetPreview;
  targetColumn: string;
  targetTypeSetting: TargetTypeSetting;
  comparisonColumn: string;
  showIgnoredColumns: boolean;
  profilingRange: ProfilingRangeSettings;
  selectedProfileColumns: string[] | null;
  selectedRelationFeatures: string[] | null;
  collapsedRelationCards: Record<string, boolean>;
  setupCollapsed: boolean;
  univariateCollapsed: boolean;
  targetCollapsed: boolean;
  segmentCollapsed: boolean;
  computedProfile: DescriptiveComputedProfile | null;
};

type DescriptiveComputedProfile = {
  key: string;
  columnProfiles: ColumnProfile[];
  targetRelations: TargetRelationProfile[];
  segmentProfile: SegmentProfile | null;
  dataQualityNotes: string[];
};

const defaultProfilingRangeSettings: ProfilingRangeSettings = {
  includeSummary: true,
  includeUnivariate: true,
  includeTargetRelations: true,
  includeSegments: true,
  includeGraphicSummaries: true,
  rowLimit: 50000,
  maxTargetFeatures: 30,
  maxSegmentFeatures: 4
};

function DescriptiveAnalysisPanel({
  datasets,
  datasetId,
  profileCache,
  setDatasetId,
  setNotice
}: {
  datasets: DataAsset[];
  datasetId: string;
  profileCache: Map<string, DescriptiveProfileCacheEntry>;
  setDatasetId: (datasetId: string) => void;
  setNotice: (message: string) => void;
}) {
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [schemaPreview, setSchemaPreview] = useState<DatasetPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);
  const [error, setError] = useState("");
  const [schemaError, setSchemaError] = useState("");
  const [targetColumn, setTargetColumn] = useState("");
  const [targetTypeSetting, setTargetTypeSetting] = useState<TargetTypeSetting>("auto");
  const [comparisonColumn, setComparisonColumn] = useState("");
  const [showIgnoredColumns, setShowIgnoredColumns] = useState(false);
  const [hasProfileRun, setHasProfileRun] = useState(false);
  const [setupCollapsed, setSetupCollapsed] = useState(false);
  const [univariateCollapsed, setUnivariateCollapsed] = useState(false);
  const [targetCollapsed, setTargetCollapsed] = useState(false);
  const [segmentCollapsed, setSegmentCollapsed] = useState(true);
  const [selectedProfileColumns, setSelectedProfileColumns] = useState<string[] | null>(null);
  const [selectedRelationFeatures, setSelectedRelationFeatures] = useState<string[] | null>(null);
  const [collapsedRelationCards, setCollapsedRelationCards] = useState<Record<string, boolean>>({});
  const [cachedComputedProfile, setCachedComputedProfile] = useState<DescriptiveComputedProfile | null>(null);
  const [profileColumnsModalOpen, setProfileColumnsModalOpen] = useState(false);
  const [relationColumnsModalOpen, setRelationColumnsModalOpen] = useState(false);
  const [profilingRangeModalOpen, setProfilingRangeModalOpen] = useState(false);
  const [profilingRange, setProfilingRange] = useState<ProfilingRangeSettings>(defaultProfilingRangeSettings);
  const profileRequestId = useRef(0);
  const profileAbortController = useRef<AbortController | null>(null);
  const schemaRequestId = useRef(0);
  const selectedDataset = datasets.find((dataset) => dataset.id === datasetId) ?? null;
  const activeProfilePreview = preview?.dataset_id === datasetId && hasProfileRun ? preview : null;
  const activeSchemaPreview = schemaPreview?.dataset_id === datasetId ? schemaPreview : null;
  const configPreview = activeProfilePreview ?? activeSchemaPreview;
  const columns = configPreview?.columns ?? [];
  const rows = activeProfilePreview?.records ?? [];
  const targetInferenceRows = activeProfilePreview?.records.length
    ? activeProfilePreview.records
    : activeSchemaPreview?.records ?? [];
  const rolesMetadata = useMemo(
    () => readRolesMetadata(selectedDataset, datasets, columns.map((column) => column.name)),
    [columns, datasets, selectedDataset]
  );
  const inferredTargetColumn = useMemo(
    () => inferTargetColumn(columns, rolesMetadata),
    [columns, rolesMetadata]
  );
  const effectiveTargetColumn = columns.some((column) => column.name === targetColumn)
    ? targetColumn
    : inferredTargetColumn;
  const targetProfile = effectiveTargetColumn
    ? null
    : columns.find((column) => columnRoleForColumn(column, rolesMetadata) === "target") ?? null;
  const targetColumnDefinition = columns.find((column) => column.name === effectiveTargetColumn) ?? null;
  const inferredTargetType = inferTargetType(targetColumnDefinition, targetInferenceRows, rolesMetadata);
  const effectiveTargetType: EffectiveTargetType = targetTypeSetting === "auto"
    ? inferredTargetType
    : targetTypeSetting;
  const effectiveComparisonColumn = columns.some((column) => column.name === comparisonColumn)
    ? comparisonColumn
    : effectiveTargetColumn;
  const comparisonColumnDefinition = columns.find((column) => column.name === effectiveComparisonColumn) ?? null;
  const effectiveComparisonType = effectiveComparisonColumn === effectiveTargetColumn
    ? effectiveTargetType
    : inferTargetType(comparisonColumnDefinition, targetInferenceRows, rolesMetadata);

  useEffect(() => () => profileAbortController.current?.abort(), []);

  useEffect(() => {
    const schemaRequestIdValue = schemaRequestId.current + 1;
    schemaRequestId.current = schemaRequestIdValue;
    profileRequestId.current += 1;
    profileAbortController.current?.abort();
    profileAbortController.current = null;
    const cachedProfile = profileCache.get(datasetId);
    const cacheIsCurrent = Boolean(
      cachedProfile && selectedDataset && cachedProfile.datasetUpdatedAt === selectedDataset.updated_at
    );

    if (cachedProfile && !cacheIsCurrent) {
      profileCache.delete(datasetId);
    }

    if (cachedProfile && cacheIsCurrent) {
      setPreview(cachedProfile.preview);
      setSchemaPreview(null);
      setError("");
      setSchemaError("");
      setIsLoading(false);
      setIsLoadingSchema(false);
      setHasProfileRun(true);
      setTargetColumn(cachedProfile.targetColumn);
      setTargetTypeSetting(cachedProfile.targetTypeSetting);
      setComparisonColumn(cachedProfile.comparisonColumn);
      setShowIgnoredColumns(cachedProfile.showIgnoredColumns);
      setProfilingRange({ ...cachedProfile.profilingRange });
      setSelectedProfileColumns(cachedProfile.selectedProfileColumns ? [...cachedProfile.selectedProfileColumns] : null);
      setSelectedRelationFeatures(cachedProfile.selectedRelationFeatures ? [...cachedProfile.selectedRelationFeatures] : null);
      setCollapsedRelationCards({ ...cachedProfile.collapsedRelationCards });
      setCachedComputedProfile(cachedProfile.computedProfile);
      setSetupCollapsed(cachedProfile.setupCollapsed);
      setUnivariateCollapsed(cachedProfile.univariateCollapsed);
      setTargetCollapsed(cachedProfile.targetCollapsed);
      setSegmentCollapsed(cachedProfile.segmentCollapsed);
      setNotice(`Cached profile restored for ${selectedDataset?.name ?? "dataset"}`);
      return;
    }

    setPreview(null);
    setSchemaPreview(null);
    setError("");
    setSchemaError("");
    setIsLoading(false);
    setIsLoadingSchema(Boolean(datasetId));
    setHasProfileRun(false);
    setTargetColumn("");
    setTargetTypeSetting("auto");
    setComparisonColumn("");
    setSelectedProfileColumns(null);
    setSelectedRelationFeatures(null);
    setCollapsedRelationCards({});
    setCachedComputedProfile(null);

    if (!datasetId) {
      setIsLoadingSchema(false);
      return;
    }

    api
      .previewDataset(datasetId, 1000)
      .then((result) => {
        if (schemaRequestId.current !== schemaRequestIdValue) {
          return;
        }
        setSchemaPreview(result);
      })
      .catch((loadError) => {
        if (schemaRequestId.current !== schemaRequestIdValue) {
          return;
        }
        const message = loadError instanceof Error ? loadError.message : "Dataset columns failed to load";
        setSchemaError(message);
      })
      .finally(() => {
        if (schemaRequestId.current === schemaRequestIdValue) {
          setIsLoadingSchema(false);
        }
      });
  }, [datasetId, profileCache, selectedDataset, setNotice]);

  useEffect(() => {
    if (columns.length === 0) {
      setTargetColumn("");
      setComparisonColumn("");
      return;
    }
    if (!targetColumn || !columns.some((column) => column.name === targetColumn)) {
      setTargetColumn(inferredTargetColumn);
    }
  }, [columns, inferredTargetColumn, targetColumn]);

  useEffect(() => {
    if (columns.length === 0) {
      setComparisonColumn("");
      return;
    }
    if (!comparisonColumn || !columns.some((column) => column.name === comparisonColumn)) {
      setComparisonColumn(effectiveTargetColumn);
    }
  }, [columns, comparisonColumn, effectiveTargetColumn]);

  function createProfileComputationKey(returnedCount: number) {
    return JSON.stringify({
    datasetId,
    datasetUpdatedAt: selectedDataset?.updated_at ?? "",
    returnedCount,
    targetColumn: effectiveTargetColumn,
    targetType: effectiveTargetType,
    comparisonColumn: effectiveComparisonColumn,
    comparisonType: effectiveComparisonType,
    includeSummary: profilingRange.includeSummary,
    includeUnivariate: profilingRange.includeUnivariate,
    includeTargetRelations: profilingRange.includeTargetRelations,
    includeSegments: profilingRange.includeSegments,
    includeGraphicSummaries: profilingRange.includeGraphicSummaries,
    maxTargetFeatures: profilingRange.maxTargetFeatures,
    maxSegmentFeatures: profilingRange.maxSegmentFeatures
    });
  }

  const profileComputationKey = useMemo(() => createProfileComputationKey(activeProfilePreview?.returned_count ?? 0), [
    activeProfilePreview?.returned_count,
    datasetId,
    effectiveComparisonColumn,
    effectiveComparisonType,
    effectiveTargetColumn,
    effectiveTargetType,
    profilingRange.includeGraphicSummaries,
    profilingRange.includeSegments,
    profilingRange.includeSummary,
    profilingRange.includeTargetRelations,
    profilingRange.includeUnivariate,
    profilingRange.maxSegmentFeatures,
    profilingRange.maxTargetFeatures,
    selectedDataset?.updated_at
  ]);
  const restoredComputedProfile = cachedComputedProfile?.key === profileComputationKey
    ? cachedComputedProfile
    : null;

  const shouldBuildColumnProfiles = Boolean(activeProfilePreview) && (
    profilingRange.includeSummary ||
    profilingRange.includeUnivariate ||
    profilingRange.includeTargetRelations
  );
  const columnProfiles = useMemo(
    () => restoredComputedProfile?.columnProfiles ?? (shouldBuildColumnProfiles
      ? columns.map((column) => buildColumnProfile(column, rows, rolesMetadata, profilingRange.includeGraphicSummaries))
      : []),
    [columns, profilingRange.includeGraphicSummaries, restoredComputedProfile, rolesMetadata, rows, shouldBuildColumnProfiles]
  );
  const selectableProfiles = useMemo(
    () => showIgnoredColumns
      ? columnProfiles
      : columnProfiles.filter((profile) => !["ignored", "identifier"].includes(profile.role)),
    [columnProfiles, showIgnoredColumns]
  );
  const selectableProfileNames = useMemo(
    () => selectableProfiles.map((profile) => profile.name),
    [selectableProfiles]
  );
  const activeProfileColumns = selectedProfileColumns ?? selectableProfileNames;
  const activeProfileColumnSet = useMemo(() => new Set(activeProfileColumns), [activeProfileColumns]);
  const visibleProfiles = useMemo(
    () => selectableProfiles.filter((profile) => activeProfileColumnSet.has(profile.name)),
    [activeProfileColumnSet, selectableProfiles]
  );
  const profileByName = useMemo(
    () => new Map(columnProfiles.map((profile) => [profile.name, profile])),
    [columnProfiles]
  );
  const targetRelations = useMemo(
    () => restoredComputedProfile?.targetRelations ?? (activeProfilePreview && profilingRange.includeTargetRelations
      ? buildTargetRelations(rows, columns, rolesMetadata, effectiveComparisonColumn, effectiveComparisonType, profilingRange.includeGraphicSummaries).slice(0, profilingRange.maxTargetFeatures)
      : []),
    [activeProfilePreview, columns, effectiveComparisonColumn, effectiveComparisonType, profilingRange.includeGraphicSummaries, profilingRange.includeTargetRelations, profilingRange.maxTargetFeatures, restoredComputedProfile, rolesMetadata, rows]
  );
  const relationFeatureNames = useMemo(
    () => targetRelations.map((relation) => relation.feature),
    [targetRelations]
  );
  const activeRelationFeatures = selectedRelationFeatures ?? relationFeatureNames;
  const activeRelationFeatureSet = useMemo(() => new Set(activeRelationFeatures), [activeRelationFeatures]);
  const visibleTargetRelations = useMemo(
    () => targetRelations.filter((relation) => activeRelationFeatureSet.has(relation.feature)),
    [activeRelationFeatureSet, targetRelations]
  );
  const visibleTargetRelationKeys = useMemo(
    () => visibleTargetRelations.map(relationCardKey),
    [visibleTargetRelations]
  );
  const segmentProfile = useMemo(
    () => restoredComputedProfile ? restoredComputedProfile.segmentProfile : (activeProfilePreview && profilingRange.includeSegments
      ? buildSegmentProfile(rows, columns, rolesMetadata, effectiveTargetColumn, effectiveTargetType, profilingRange.maxSegmentFeatures, profilingRange.includeGraphicSummaries)
      : null),
    [activeProfilePreview, columns, effectiveTargetColumn, effectiveTargetType, profilingRange.includeGraphicSummaries, profilingRange.includeSegments, profilingRange.maxSegmentFeatures, restoredComputedProfile, rolesMetadata, rows]
  );
  const dataQualityNotes = useMemo(
    () => restoredComputedProfile?.dataQualityNotes ?? (activeProfilePreview && profilingRange.includeSummary
      ? buildDatasetQualityNotes(columnProfiles, rows.length, rolesMetadata, effectiveTargetColumn)
      : []),
    [activeProfilePreview, columnProfiles, effectiveTargetColumn, profilingRange.includeSummary, restoredComputedProfile, rolesMetadata, rows.length]
  );
  const computedProfileSnapshot = useMemo<DescriptiveComputedProfile>(() => ({
    key: profileComputationKey,
    columnProfiles,
    targetRelations,
    segmentProfile,
    dataQualityNotes
  }), [columnProfiles, dataQualityNotes, profileComputationKey, segmentProfile, targetRelations]);
  const numericProfiles = useMemo(
    () => columnProfiles.filter((profile) => profile.mean !== null),
    [columnProfiles]
  );
  const categoricalProfiles = useMemo(
    () => columnProfiles.filter((profile) =>
      ["feature_categorical", "feature_ordinal", "boolean", "target"].includes(profile.role) ||
      ["text", "boolean"].includes(profile.type)
    ),
    [columnProfiles]
  );
  const featureCount = columns.filter((column) =>
    !["ignored", "identifier", "target"].includes(columnRoleForColumn(column, rolesMetadata))
  ).length;
  const targetSummary = effectiveTargetColumn
    ? profileByName.get(effectiveTargetColumn)
    : undefined;
  const comparisonSummary = effectiveComparisonColumn
    ? profileByName.get(effectiveComparisonColumn)
    : undefined;
  const enabledRangeLabels = [
    profilingRange.includeSummary ? "summary" : "",
    profilingRange.includeUnivariate ? "univariate" : "",
    profilingRange.includeTargetRelations ? "target relations" : "",
    profilingRange.includeSegments ? "segments" : "",
    profilingRange.includeGraphicSummaries ? "graphics" : "no graphics"
  ].filter(Boolean);

  useEffect(() => {
    setSelectedProfileColumns((current) => syncSelectedNames(current, selectableProfileNames));
  }, [selectableProfileNames]);

  useEffect(() => {
    setSelectedRelationFeatures((current) => syncSelectedNames(current, relationFeatureNames));
  }, [relationFeatureNames]);

  useEffect(() => {
    setCollapsedRelationCards((current) => {
      const visibleKeySet = new Set(visibleTargetRelationKeys);
      const next = Object.fromEntries(
        Object.entries(current).filter(([key]) => visibleKeySet.has(key))
      );
      if (Object.keys(next).length === Object.keys(current).length) {
        return current;
      }
      return next;
    });
  }, [visibleTargetRelationKeys]);

  useEffect(() => {
    if (!activeProfilePreview || !selectedDataset) {
      return;
    }
    const cachedProfile = profileCache.get(datasetId);
    if (!cachedProfile || cachedProfile.datasetUpdatedAt !== selectedDataset.updated_at) {
      return;
    }
    profileCache.set(datasetId, createProfileCacheEntry(activeProfilePreview, computedProfileSnapshot));
  }, [
    activeProfilePreview,
    collapsedRelationCards,
    computedProfileSnapshot,
    datasetId,
    effectiveComparisonColumn,
    effectiveTargetColumn,
    profileCache,
    profilingRange,
    segmentCollapsed,
    selectedDataset,
    selectedProfileColumns,
    selectedRelationFeatures,
    setupCollapsed,
    showIgnoredColumns,
    targetCollapsed,
    targetTypeSetting,
    univariateCollapsed
  ]);

  function createProfileCacheEntry(
    profilePreview: DatasetPreview,
    computedProfile: DescriptiveComputedProfile | null
  ): DescriptiveProfileCacheEntry {
    return {
      datasetUpdatedAt: selectedDataset?.updated_at ?? "",
      preview: profilePreview,
      targetColumn: effectiveTargetColumn,
      targetTypeSetting,
      comparisonColumn: effectiveComparisonColumn,
      showIgnoredColumns,
      profilingRange: { ...profilingRange },
      selectedProfileColumns: selectedProfileColumns ? [...selectedProfileColumns] : null,
      selectedRelationFeatures: selectedRelationFeatures ? [...selectedRelationFeatures] : null,
      collapsedRelationCards: { ...collapsedRelationCards },
      setupCollapsed,
      univariateCollapsed,
      targetCollapsed,
      segmentCollapsed,
      computedProfile
    };
  }

  async function runProfiling() {
    if (!datasetId) {
      setNotice("Choose a dataset first");
      return;
    }

    const requestId = profileRequestId.current + 1;
    profileRequestId.current = requestId;
    profileAbortController.current?.abort();
    const abortController = new AbortController();
    profileAbortController.current = abortController;
    setCachedComputedProfile(null);
    setIsLoading(true);
    setError("");
    setHasProfileRun(true);
    setSetupCollapsed(false);
    setNotice("Profiling dataset. This can take a moment.");

    try {
      if (selectedDataset?.source_type === "view") {
        const result = await api.previewDataset(datasetId, profilingRange.rowLimit);
        if (profileRequestId.current !== requestId) {
          return;
        }
        if (selectedDataset) {
          profileCache.set(datasetId, createProfileCacheEntry(result, null));
        }
        setPreview(result);
        setNotice(`Profile loaded for ${result.returned_count} of ${result.row_count} rows`);
        return;
      }
      const result = await api.profileDataset(datasetId, {
        target_column: effectiveTargetColumn,
        target_type: effectiveTargetType,
        comparison_column: effectiveComparisonColumn,
        comparison_type: effectiveComparisonType,
        include_summary: profilingRange.includeSummary,
        include_univariate: profilingRange.includeUnivariate,
        include_target_relations: profilingRange.includeTargetRelations,
        include_segments: profilingRange.includeSegments,
        include_graphic_summaries: profilingRange.includeGraphicSummaries,
        row_limit: profilingRange.rowLimit,
        max_target_features: profilingRange.maxTargetFeatures,
        max_segment_features: profilingRange.maxSegmentFeatures
      }, abortController.signal);
      if (profileRequestId.current !== requestId) {
        return;
      }
      const profilePreview: DatasetPreview = {
        dataset_id: result.dataset_id,
        columns: result.columns,
        records: [],
        row_count: result.row_count,
        returned_count: result.row_count,
        limit: result.row_count
      };
      const backendProfile = result.profile as Omit<DescriptiveComputedProfile, "key">;
      const computedProfile: DescriptiveComputedProfile = {
        key: createProfileComputationKey(result.row_count),
        columnProfiles: backendProfile.columnProfiles ?? [],
        targetRelations: backendProfile.targetRelations ?? [],
        segmentProfile: backendProfile.segmentProfile ?? null,
        dataQualityNotes: backendProfile.dataQualityNotes ?? []
      };
      if (selectedDataset) {
        profileCache.set(datasetId, createProfileCacheEntry(profilePreview, computedProfile));
      }
      setCachedComputedProfile(computedProfile);
      setPreview(profilePreview);
      setNotice(`Profile loaded for all ${result.row_count} rows`);
    } catch (loadError) {
      if (profileRequestId.current !== requestId) {
        return;
      }
      const message = loadError instanceof Error ? loadError.message : "Dataset profile failed";
      setPreview(null);
      setError(message);
      setNotice(message);
    } finally {
      if (profileRequestId.current === requestId) {
        setIsLoading(false);
        profileAbortController.current = null;
      }
    }
  }

  function updateDataset(nextDatasetId: string) {
    setDatasetId(nextDatasetId);
  }

  function updateProfileSelection(values: string[]) {
    setSelectedProfileColumns(values);
  }

  function updateRelationSelection(values: string[]) {
    setSelectedRelationFeatures(values);
  }

  function toggleRelationCard(relation: TargetRelationProfile) {
    const key = relationCardKey(relation);
    setCollapsedRelationCards((current) => ({
      ...current,
      [key]: !current[key]
    }));
  }

  function showAllRelationCards() {
    setCollapsedRelationCards((current) => {
      const visibleKeySet = new Set(visibleTargetRelationKeys);
      const next = Object.fromEntries(
        Object.entries(current).filter(([key]) => !visibleKeySet.has(key))
      );
      return next;
    });
  }

  function collapseAllRelationCards() {
    setCollapsedRelationCards((current) => ({
      ...current,
      ...Object.fromEntries(visibleTargetRelationKeys.map((key) => [key, true]))
    }));
  }

  if (datasets.length === 0) {
    return (
      <div className="panel">
        <div className="empty-state">No datasets available</div>
      </div>
    );
  }

  return (
    <div className="descriptive-analysis-panel">
      <section className="panel profile-run-panel">
        <button
          aria-expanded={!setupCollapsed}
          className="section-toggle profile-section-toggle"
          onClick={() => setSetupCollapsed((current) => !current)}
          type="button"
        >
          {setupCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          <strong>Dataset profile</strong>
          <span>{isLoading ? "running" : isLoadingSchema ? "loading columns" : activeProfilePreview ? "ready" : "not started"}</span>
        </button>

        {!setupCollapsed && (
          <>
            <div className="descriptive-toolbar">
              <label>
                Dataset
                <select value={datasetId} onChange={(event) => updateDataset(event.target.value)}>
                  {datasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {datasetVersionLabel(dataset, datasets)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Target
                <select
                  disabled={columns.length === 0 || isLoading || isLoadingSchema}
                  value={effectiveTargetColumn}
                  onChange={(event) => setTargetColumn(event.target.value)}
                >
                  <option value="">No target selected</option>
                  {columns.map((column) => (
                    <option key={column.name} value={column.name}>
                      {column.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Target type
                <select
                  disabled={!effectiveTargetColumn || isLoading || isLoadingSchema}
                  value={targetTypeSetting}
                  onChange={(event) => setTargetTypeSetting(event.target.value as TargetTypeSetting)}
                >
                  <option value="auto">Auto ({inferredTargetType})</option>
                  <option value="categorical">Categorical/classification</option>
                  <option value="continuous">Continuous/regression</option>
                </select>
              </label>
              <label className="check-tile descriptive-toggle">
                <input
                  checked={showIgnoredColumns}
                  disabled={isLoading}
                  onChange={(event) => setShowIgnoredColumns(event.target.checked)}
                  type="checkbox"
                />
                <span>Show ignored and ID columns</span>
              </label>
              <button
                className="secondary-button toolbar-button"
                disabled={isLoading}
                onClick={() => setProfilingRangeModalOpen(true)}
                type="button"
              >
                <Filter size={16} />
                Profiling range
              </button>
              <button
                className="primary-button toolbar-button"
                disabled={isLoading || isLoadingSchema || !datasetId}
                onClick={runProfiling}
                type="button"
              >
                <Play size={16} />
                {isLoading ? "Profiling" : "Run profiling"}
              </button>
            </div>

            {isLoading && (
              <div className="profiling-status" role="status">
                <div className="progress-track" aria-hidden="true">
                  <div />
                </div>
                <strong>Profiling dataset</strong>
                <span>Working on metadata-aware summaries. Please wait, the app is still running.</span>
              </div>
            )}

            {!isLoading && isLoadingSchema && (
              <div className="profiling-status" role="status">
                <div className="progress-track" aria-hidden="true">
                  <div />
                </div>
                <strong>Loading dataset columns</strong>
                <span>Preparing target and target-type settings before profiling starts.</span>
              </div>
            )}

            {!isLoading && !isLoadingSchema && schemaError && (
              <div className="empty-state error-state">{schemaError}</div>
            )}

            {!isLoading && !isLoadingSchema && !schemaError && !hasProfileRun && (
              <div className="empty-state">
                Choose a dataset, configure profiling range if needed, then run profiling when you are ready.
              </div>
            )}
            {!isLoading && error && <div className="empty-state error-state">{error}</div>}
            {!isLoading && !error && activeProfilePreview && activeProfilePreview.row_count === 0 && (
              <div className="empty-state">Dataset is empty</div>
            )}

            {!isLoading && !error && activeProfilePreview && activeProfilePreview.row_count > 0 && (
              <>
                <section className="profile-metrics">
                  <Metric icon={Database} label="Rows profiled" value={activeProfilePreview.returned_count} tone="teal" />
                  <Metric icon={Table2} label="Columns" value={columns.length} tone="blue" />
                  <Metric icon={BarChart3} label="Features" value={featureCount} tone="amber" />
                  <Metric icon={Activity} label="Feature relations" value={targetRelations.length} tone="teal" />
                </section>

                <div className="profile-range-summary">
                  <strong>Profiling range</strong>
                  <span>{enabledRangeLabels.join(", ")} / all rows / graphics capped at {formatInteger(profilingRange.rowLimit)} source points</span>
                </div>

                {profilingRange.includeSummary && (
                  <section className="profile-overview">
                    <div className="panel-header">
                      <h2>Smart dataset profile</h2>
                      {activeProfilePreview.returned_count < activeProfilePreview.row_count && (
                        <span className="muted-text">Preview limited to {activeProfilePreview.returned_count} rows</span>
                      )}
                    </div>
                    <div className="profile-summary-grid">
                      <ProfileFact label="Dataset roles" value={rolesMetadata.dataset_roles.length ? rolesMetadata.dataset_roles.join(", ") : "not set"} />
                      <ProfileFact label="Target" value={effectiveTargetColumn || "not set"} />
                      <ProfileFact label="Target type" value={effectiveTargetType} />
                      <ProfileFact label="Numeric columns" value={String(numericProfiles.length)} />
                      <ProfileFact label="Categorical columns" value={String(categoricalProfiles.length)} />
                    </div>
                    <div className="insight-list">
                      {dataQualityNotes.map((note) => (
                        <div className="insight-item" key={note}>{note}</div>
                      ))}
                      {dataQualityNotes.length === 0 && (
                        <div className="insight-item">No major profiling warnings in the loaded sample.</div>
                      )}
                    </div>
                  </section>
                )}
              </>
            )}
          </>
        )}
      </section>

      {datasetId && columns.length > 0 && (
        <DeferredPanel>
          <TimeSeriesWorkbench
            columns={columns}
            datasetId={datasetId}
            defaultTimeColumn={rolesMetadata.timestamp_column}
            defaultValueColumn={effectiveTargetColumn || rolesMetadata.target_column}
            mode="descriptive"
          />
        </DeferredPanel>
      )}

      {!isLoading && !error && activeProfilePreview && activeProfilePreview.row_count > 0 && (
        <>
          {profilingRange.includeUnivariate && <section className="panel">
            <button
              aria-expanded={!univariateCollapsed}
              className="section-toggle profile-section-toggle"
              onClick={() => setUnivariateCollapsed((current) => !current)}
              type="button"
            >
              {univariateCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <strong>Univariate profile</strong>
              <span>{visibleProfiles.length}/{selectableProfiles.length} columns</span>
            </button>
            {!univariateCollapsed && (
              <>
                <ColumnSelectionSummary
                  columns={selectableProfiles.map((profile) => ({ name: profile.name, meta: `${columnRoleLabel(profile.role)} / ${profile.type}` }))}
                  selected={activeProfileColumns}
                  onOpen={() => setProfileColumnsModalOpen(true)}
                />
                <div className="profile-column-grid">
                  {visibleProfiles.map((profile) => (
                    <article className="column-profile-card" key={profile.name}>
                      <div className="column-profile-head">
                        <div>
                          <strong>{profile.name}</strong>
                          <span>{columnRoleLabel(profile.role)} / {profile.type}</span>
                        </div>
                        <em>{formatPercent(1 - profile.missingRate)} complete</em>
                      </div>
                      <div className="profile-stat-grid">
                        <ProfileFact label="Count" value={formatInteger(profile.count)} />
                        <ProfileFact label="Missing" value={formatPercent(profile.missingRate)} />
                        <ProfileFact label="Unique" value={formatInteger(profile.unique)} />
                        <ProfileFact label="Mode" value={displayValue(profile.mode)} />
                      </div>
                      {profile.mean !== null && !usesDiscreteDistribution(profile) ? (
                        <>
                          {profilingRange.includeGraphicSummaries && <MiniHistogram bins={profile.histogram} />}
                          <div className="profile-stat-grid">
                            <ProfileFact label="Mean" value={formatNumber(profile.mean)} />
                            <ProfileFact label="Median" value={formatNullableNumber(profile.median)} />
                            <ProfileFact label="Min" value={displayValue(profile.minimum)} />
                            <ProfileFact label="Max" value={displayValue(profile.maximum)} />
                          </div>
                        </>
                      ) : (
                        profilingRange.includeGraphicSummaries && <MiniDiscreteDistribution values={profile.topValues} limit={usesDiscreteDistribution(profile) ? 12 : 4} />
                      )}
                      {profile.notes.length > 0 && (
                        <div className="profile-notes">
                          {profile.notes.map((note) => <span key={note}>{note}</span>)}
                        </div>
                      )}
                    </article>
                  ))}
                  {visibleProfiles.length === 0 && (
                    <div className="empty-state">No columns selected for univariate profile.</div>
                  )}
                </div>
              </>
            )}
          </section>}

          {profilingRange.includeTargetRelations && <section className="panel">
            <button
              aria-expanded={!targetCollapsed}
              className="section-toggle profile-section-toggle"
              onClick={() => setTargetCollapsed((current) => !current)}
              type="button"
            >
              {targetCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <strong>Target vs features</strong>
              <span>{visibleTargetRelations.length}/{targetRelations.length} signals</span>
            </button>
            {!targetCollapsed && (
              <section className="profile-relation-layout">
                <div className="target-relations-main">
                  <div className="relation-compare-toolbar">
                    <label>
                      Compare by
                      <select
                        value={effectiveComparisonColumn}
                        onChange={(event) => setComparisonColumn(event.target.value)}
                      >
                        <option value="">No comparison column</option>
                        {columns
                          .filter((column) => !["ignored", "identifier"].includes(columnRoleForColumn(column, rolesMetadata)))
                          .map((column) => (
                            <option key={column.name} value={column.name}>
                              {column.name}{column.name === effectiveTargetColumn ? " (target)" : ""}
                            </option>
                          ))}
                      </select>
                    </label>
                    <ProfileFact label="Comparison type" value={effectiveComparisonColumn ? effectiveComparisonType : "not set"} />
                  </div>
                  {targetRelations.length > 0 && (
                    <div className="relation-list-toolbar">
                      <ColumnSelectionSummary
                        columns={targetRelations.map((relation) => ({ name: relation.feature, meta: `${columnRoleLabel(relation.role)} / ${relation.kind}` }))}
                        selected={activeRelationFeatures}
                        onOpen={() => setRelationColumnsModalOpen(true)}
                      />
                      <div className="section-actions relation-card-actions">
                        <button className="secondary-button compact-button" onClick={showAllRelationCards} type="button">
                          Show all
                        </button>
                        <button className="secondary-button compact-button" onClick={collapseAllRelationCards} type="button">
                          Collapse all
                        </button>
                      </div>
                    </div>
                  )}
                  {!effectiveComparisonColumn && (
                    <div className="empty-state">
                      Select a target or comparison column to rank feature relationships.
                    </div>
                  )}
                  {effectiveComparisonColumn && targetRelations.length === 0 && (
                    <div className="empty-state">No eligible feature relationships found for the selected comparison column.</div>
                  )}
                  {effectiveComparisonColumn && targetRelations.length > 0 && visibleTargetRelations.length === 0 && (
                    <div className="empty-state">No feature relationships selected.</div>
                  )}
                  {effectiveComparisonColumn && visibleTargetRelations.length > 0 && (
                    <div className="relation-list">
                      {visibleTargetRelations.map((relation) => (
                        <TargetRelationCard
                          collapsed={Boolean(collapsedRelationCards[relationCardKey(relation)])}
                          onToggle={() => toggleRelationCard(relation)}
                          relation={relation}
                          key={relationCardKey(relation)}
                        />
                      ))}
                    </div>
                  )}
                </div>

                <aside className="target-context">
                  <div className="panel-header">
                    <h2>Comparison context</h2>
                  </div>
                  {comparisonSummary ? (
                    <>
                      <div className="profile-stat-grid">
                        <ProfileFact label="Column" value={comparisonSummary.name} />
                        <ProfileFact label="Role" value={columnRoleLabel(comparisonSummary.role)} />
                        <ProfileFact label="Type" value={comparisonSummary.type} />
                        <ProfileFact label="Missing" value={formatPercent(comparisonSummary.missingRate)} />
                        <ProfileFact label="Unique" value={formatInteger(comparisonSummary.unique)} />
                      </div>
                      {profilingRange.includeGraphicSummaries && comparisonSummary.mean !== null && !usesDiscreteDistribution(comparisonSummary) && <MiniHistogram bins={comparisonSummary.histogram} />}
                      {profilingRange.includeGraphicSummaries && <MiniDiscreteDistribution values={comparisonSummary.topValues} limit={6} />}
                    </>
                  ) : (
                    <div className="empty-state compact-empty">Comparison column not selected</div>
                  )}
                  {targetProfile && (
                    <div className="insight-item">Role metadata marks {targetProfile.name} as target.</div>
                  )}
                </aside>
              </section>
            )}
          </section>}

          {profilingRange.includeSegments && <section className="panel">
            <button
              aria-expanded={!segmentCollapsed}
              className="section-toggle profile-section-toggle"
              onClick={() => setSegmentCollapsed((current) => !current)}
              type="button"
            >
              {segmentCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <strong>Multivariate segment scan</strong>
              <span>role-aware categorical feature combinations</span>
            </button>
            {!segmentCollapsed && (
              segmentProfile && segmentProfile.results.length > 0 ? (
                <div className="segment-scan">
                  <div className="profile-summary-grid">
                    <ProfileFact label="Target" value={segmentProfile.targetColumn} />
                    <ProfileFact label="Candidate features" value={formatInteger(segmentProfile.candidateFeatures.length)} />
                    <ProfileFact label="Feature pairs scanned" value={formatInteger(segmentProfile.pairsScanned)} />
                    <ProfileFact label="Eligible segments" value={formatInteger(segmentProfile.segmentsEvaluated)} />
                  </div>
                  <SegmentScanResults profile={segmentProfile} />
                </div>
              ) : (
                <div className="empty-state">
                  Need a selected target and at least two low-cardinality categorical features to scan combined segments.
                </div>
              )
            )}
          </section>}
        </>
      )}

      {profileColumnsModalOpen && (
        <ColumnSelectionModal
          columns={selectableProfiles.map((profile) => ({ name: profile.name, meta: `${columnRoleLabel(profile.role)} / ${profile.type}` }))}
          onChange={updateProfileSelection}
          onClose={() => setProfileColumnsModalOpen(false)}
          selected={activeProfileColumns}
          title="Univariate columns"
        />
      )}
      {relationColumnsModalOpen && (
        <ColumnSelectionModal
          columns={targetRelations.map((relation) => ({ name: relation.feature, meta: `${columnRoleLabel(relation.role)} / ${relation.kind}` }))}
          onChange={updateRelationSelection}
          onClose={() => setRelationColumnsModalOpen(false)}
          selected={activeRelationFeatures}
          title="Relationship columns"
        />
      )}
      {profilingRangeModalOpen && (
        <ProfilingRangeModal
          onApply={setProfilingRange}
          onClose={() => setProfilingRangeModalOpen(false)}
          settings={profilingRange}
        />
      )}
    </div>
  );
}

type SelectableColumn = {
  name: string;
  meta: string;
};

function ColumnSelectionSummary({
  columns,
  selected,
  onOpen
}: {
  columns: SelectableColumn[];
  selected: string[];
  onOpen: () => void;
}) {
  const selectedPreview = selected.slice(0, 4).join(", ");
  return (
    <div className="column-selection-summary">
      <div>
        <strong>Columns</strong>
        <span>
          {selected.length} of {columns.length} selected
          {selectedPreview ? ` / ${selectedPreview}${selected.length > 4 ? ", ..." : ""}` : ""}
        </span>
      </div>
      <button className="secondary-button compact-button" onClick={onOpen} type="button">
        <Table2 size={14} />
        Columns selection
      </button>
    </div>
  );
}

function ColumnSelectionModal({
  columns,
  onChange,
  onClose,
  selected,
  title
}: {
  columns: SelectableColumn[];
  onChange: (columns: string[]) => void;
  onClose: () => void;
  selected: string[];
  title: string;
}) {
  const [searchValue, setSearchValue] = useState("");
  const [draftSelected, setDraftSelected] = useState(selected);
  const [lastClickedIndex, setLastClickedIndex] = useState<number | null>(null);
  const draftSelectedSet = new Set(draftSelected);
  const normalizedSearch = searchValue.trim().toLowerCase();
  const filteredColumns = normalizedSearch
    ? columns.filter((column) =>
        column.name.toLowerCase().includes(normalizedSearch) ||
        column.meta.toLowerCase().includes(normalizedSearch)
      )
    : columns;
  const selectedVisibleCount = filteredColumns.filter((column) => draftSelectedSet.has(column.name)).length;

  function applySelection() {
    onChange(draftSelected);
    onClose();
  }

  function toggleColumn(column: SelectableColumn, filteredIndex: number, event: ChangeEvent<HTMLInputElement>) {
    const nextChecked = event.target.checked;
    const visibleNames = filteredColumns.map((item) => item.name);
    let namesToUpdate = [column.name];
    if (event.nativeEvent instanceof MouseEvent && event.nativeEvent.shiftKey && lastClickedIndex !== null) {
      const start = Math.min(lastClickedIndex, filteredIndex);
      const end = Math.max(lastClickedIndex, filteredIndex);
      namesToUpdate = visibleNames.slice(start, end + 1);
    }
    const updateSet = new Set(namesToUpdate);
    setDraftSelected((current) => {
      const currentSet = new Set(current);
      for (const name of updateSet) {
        if (nextChecked) {
          currentSet.add(name);
        } else {
          currentSet.delete(name);
        }
      }
      return columns.map((item) => item.name).filter((name) => currentSet.has(name));
    });
    setLastClickedIndex(filteredIndex);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-label={title} className="column-selection-modal" role="dialog">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Columns selection</p>
            <h2>{title}</h2>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close columns selection">
            <X size={18} />
          </button>
        </header>

        <div className="column-selection-body">
          <div className="column-selection-tools">
            <label>
              Search columns
              <div className="input-with-icon">
                <Search size={16} />
                <input
                  value={searchValue}
                  onChange={(event) => {
                    setSearchValue(event.target.value);
                    setLastClickedIndex(null);
                  }}
                  placeholder="Column name or role"
                />
              </div>
            </label>
            <div className="section-actions">
              <button className="secondary-button compact-button" onClick={() => setDraftSelected(columns.map((column) => column.name))} type="button">
                Show all
              </button>
              <button className="secondary-button compact-button" onClick={() => setDraftSelected([])} type="button">
                Hide all
              </button>
            </div>
          </div>

          <div className="selector-filter-summary">
            {draftSelected.length} of {columns.length} selected
            {searchValue.trim() ? ` / ${selectedVisibleCount} of ${filteredColumns.length} matching selected` : ""}
          </div>

          <div className="column-selector-grid modal-selector-grid">
            {filteredColumns.map((column, index) => (
              <label className={draftSelectedSet.has(column.name) ? "selector-column selected" : "selector-column"} key={column.name}>
                <input
                  checked={draftSelectedSet.has(column.name)}
                  onChange={(event) => toggleColumn(column, index, event)}
                  type="checkbox"
                />
                <span>
                  <strong>{column.name}</strong>
                  <em>{column.meta}</em>
                </span>
              </label>
            ))}
            {filteredColumns.length === 0 && (
              <div className="empty-state compact-empty">No columns match current search</div>
            )}
          </div>
        </div>

        <footer className="modal-actions">
          <button className="secondary-button" onClick={onClose} type="button">
            Cancel
          </button>
          <button className="primary-button" onClick={applySelection} type="button">
            Apply selection
          </button>
        </footer>
      </section>
    </div>
  );
}

function ProfilingRangeModal({
  onApply,
  onClose,
  settings
}: {
  onApply: (settings: ProfilingRangeSettings) => void;
  onClose: () => void;
  settings: ProfilingRangeSettings;
}) {
  const [draftSettings, setDraftSettings] = useState(settings);

  function updateBoolean(key: keyof Pick<
    ProfilingRangeSettings,
    "includeSummary" | "includeUnivariate" | "includeTargetRelations" | "includeSegments" | "includeGraphicSummaries"
  >, value: boolean) {
    setDraftSettings((current) => ({ ...current, [key]: value }));
  }

  function updateNumber(key: keyof Pick<
    ProfilingRangeSettings,
    "rowLimit" | "maxTargetFeatures" | "maxSegmentFeatures"
  >, value: string) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return;
    }
    const minimum = key === "maxSegmentFeatures" ? 2 : 1;
    setDraftSettings((current) => ({
      ...current,
      [key]: Math.max(minimum, Math.trunc(parsed))
    }));
  }

  function applySettings() {
    onApply(draftSettings);
    onClose();
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-label="Profiling range" className="profiling-range-modal" role="dialog">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Profiling range</p>
            <h2>Configure profiling scope</h2>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close profiling range">
            <X size={18} />
          </button>
        </header>

        <div className="profiling-range-body">
          <section className="range-section">
            <div className="panel-header compact-header">
              <h2>Sections</h2>
            </div>
            <div className="range-choice-grid">
              <label className="check-tile">
                <input
                  checked={draftSettings.includeSummary}
                  onChange={(event) => updateBoolean("includeSummary", event.target.checked)}
                  type="checkbox"
                />
                <span>Dataset summary and quality notes</span>
              </label>
              <label className="check-tile">
                <input
                  checked={draftSettings.includeUnivariate}
                  onChange={(event) => updateBoolean("includeUnivariate", event.target.checked)}
                  type="checkbox"
                />
                <span>Univariate column profiles</span>
              </label>
              <label className="check-tile">
                <input
                  checked={draftSettings.includeTargetRelations}
                  onChange={(event) => updateBoolean("includeTargetRelations", event.target.checked)}
                  type="checkbox"
                />
                <span>Target vs feature relations</span>
              </label>
              <label className="check-tile">
                <input
                  checked={draftSettings.includeSegments}
                  onChange={(event) => updateBoolean("includeSegments", event.target.checked)}
                  type="checkbox"
                />
                <span>Multivariate segment scan</span>
              </label>
            </div>
          </section>

          <section className="range-section">
            <div className="panel-header compact-header">
              <h2>Options</h2>
            </div>
            <div className="range-choice-grid">
              <label className="check-tile">
                <input
                  checked={draftSettings.includeGraphicSummaries}
                  onChange={(event) => updateBoolean("includeGraphicSummaries", event.target.checked)}
                  type="checkbox"
                />
                <span>Graphic summaries</span>
              </label>
            </div>
          </section>

          <section className="range-section">
            <div className="panel-header compact-header">
              <h2>Limits</h2>
            </div>
            <div className="range-number-grid">
              <label>
                Graphic source-point limit
                <input
                  min={1}
                  onChange={(event) => updateNumber("rowLimit", event.target.value)}
                  type="number"
                  value={draftSettings.rowLimit}
                />
              </label>
              <label>
                Max target relation features
                <input
                  min={1}
                  onChange={(event) => updateNumber("maxTargetFeatures", event.target.value)}
                  type="number"
                  value={draftSettings.maxTargetFeatures}
                />
              </label>
              <label>
                Max segment scan features
                <input
                  min={2}
                  onChange={(event) => updateNumber("maxSegmentFeatures", event.target.value)}
                  type="number"
                  value={draftSettings.maxSegmentFeatures}
                />
              </label>
            </div>
          </section>

          <div className="insight-item">
            Lighter ranges finish faster. For a quick look, run only Dataset summary or Univariate profiles.
          </div>
        </div>

        <footer className="modal-actions">
          <button className="secondary-button" onClick={onClose} type="button">
            Cancel
          </button>
          <button className="secondary-button" onClick={() => setDraftSettings(defaultProfilingRangeSettings)} type="button">
            Reset defaults
          </button>
          <button className="primary-button" onClick={applySettings} type="button">
            Apply range
          </button>
        </footer>
      </section>
    </div>
  );
}

function MiniHistogram({ bins }: { bins: Array<{ label: string; count: number; share: number }> }) {
  if (bins.length === 0) {
    return <div className="empty-state compact-empty">No numeric distribution available</div>;
  }
  const maxCount = Math.max(...bins.map((bin) => bin.count), 1);
  return (
    <div className="mini-histogram" aria-label="Mini histogram">
      <div className="histogram-bars">
        {bins.map((bin) => (
          <div className="histogram-bin" key={bin.label} title={`${bin.label}: ${formatInteger(bin.count)}`}>
            <div style={{ height: `${Math.max(6, (bin.count / maxCount) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="histogram-axis">
        <span>{bins[0]?.label.split(" - ")[0]}</span>
        <span>{bins.at(-1)?.label.split(" - ").at(-1)}</span>
      </div>
    </div>
  );
}

function TargetRelationCard({
  collapsed,
  onToggle,
  relation
}: {
  collapsed: boolean;
  onToggle: () => void;
  relation: TargetRelationProfile;
}) {
  return (
    <article className={relation.groupStats.length > 0 || relation.numericStats ? "relation-row relation-row-detailed" : "relation-row"}>
      <button
        aria-expanded={!collapsed}
        className="relation-card-toggle"
        onClick={onToggle}
        type="button"
      >
        <span className="relation-card-title">
          {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          <span>
            <strong>{relation.feature}</strong>
            <em>{columnRoleLabel(relation.role)} / {relation.kind}</em>
          </span>
        </span>
        <span className="relation-score">
          <span className="mini-bar" aria-hidden="true">
            <span style={{ width: `${Math.max(4, relation.score * 100)}%` }} />
          </span>
          <em>{relation.signal}</em>
        </span>
      </button>
      {!collapsed && (
        <div className="relation-card-body">
          <p>{relation.detail}</p>
          {relation.numericStats && (
            <>
              {relation.scatterPlot && <MiniScatterPlot plot={relation.scatterPlot} />}
              <div className="numeric-relation-table" role="table" aria-label={`${relation.feature} numeric relationship with ${relation.comparisonColumn}`}>
                <div className="numeric-relation-row numeric-relation-head" role="row">
                  <span role="columnheader">Pearson</span>
                  <span role="columnheader">Spearman</span>
                  <span role="columnheader">R²</span>
                  <span role="columnheader">Slope</span>
                  <span role="columnheader">Intercept</span>
                  <span role="columnheader">Covariance</span>
                </div>
                <div className="numeric-relation-row" role="row">
                  <span role="cell">{formatSignedNumber(relation.numericStats.pearson)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.spearman)}</span>
                  <span role="cell">{formatNumber(relation.numericStats.rSquared)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.slope)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.intercept)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.covariance)}</span>
                </div>
              </div>
            </>
          )}
          {relation.groupStats.length > 0 && (
            <>
              {relation.densityPlot && <MiniDensityPlot plot={relation.densityPlot} />}
              <div className="relation-stats-table" role="table" aria-label={`${relation.feature} by ${relation.comparisonColumn}`}>
                <div className="relation-stats-row relation-stats-head" role="row">
                  <span role="columnheader">{relation.comparisonColumn}</span>
                  <span role="columnheader">Rows</span>
                  <span role="columnheader">Min</span>
                  <span role="columnheader">Max</span>
                  <span role="columnheader">Median</span>
                  <span role="columnheader">Average</span>
                  <span role="columnheader">Std</span>
                </div>
                {relation.groupStats.map((group) => (
                  <div className="relation-stats-row" key={group.group} role="row">
                    <span role="cell">
                      <i style={{ background: group.color }} />
                      {group.group}
                    </span>
                    <span role="cell">{formatInteger(group.count)}</span>
                    <span role="cell">{formatNumber(group.minimum)}</span>
                    <span role="cell">{formatNumber(group.maximum)}</span>
                    <span role="cell">{formatNumber(group.median)}</span>
                    <span role="cell">{formatNumber(group.mean)}</span>
                    <span role="cell">{formatNumber(group.stdDev)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {relation.categoricalStats && (
            <CategoricalRelationDetails
              comparisonColumn={relation.comparisonColumn}
              feature={relation.feature}
              stats={relation.categoricalStats}
            />
          )}
        </div>
      )}
    </article>
  );
}

function CategoricalRelationDetails({
  comparisonColumn,
  feature,
  stats
}: {
  comparisonColumn: string;
  feature: string;
  stats: CategoricalRelationStats;
}) {
  return (
    <>
      <div className="categorical-metric-grid">
        <ProfileFact label="Cramer's V" value={formatNumber(stats.cramersV)} />
        <ProfileFact label="Chi-square" value={formatNumber(stats.chiSquare)} />
        <ProfileFact label="Degrees of freedom" value={formatInteger(stats.degreesFreedom)} />
        <ProfileFact label="Sparse expected cells" value={formatPercent(stats.sparseCellShare)} />
      </div>
      {stats.ordinalTrend && (
        <div className="ordinal-trend-summary">
          <strong>Ordinal trend</strong>
          <span>
            Spearman {formatSignedNumber(stats.ordinalTrend.spearman)} for target value {stats.ordinalTrend.focusValue}
          </span>
          <em>Order: {stats.ordinalTrend.orderBasis}</em>
        </div>
      )}
      <div className="categorical-relation-table" role="table" aria-label={`${feature} distribution by ${comparisonColumn}`}>
        <div
          className="categorical-relation-row categorical-relation-head"
          role="row"
          style={{ gridTemplateColumns: `minmax(140px, 1.3fr) 72px repeat(${stats.comparisonValues.length}, minmax(130px, 1fr))` }}
        >
          <span role="columnheader">{feature}</span>
          <span role="columnheader">Rows</span>
          {stats.comparisonValues.map((value) => (
            <span key={value} role="columnheader">{comparisonColumn}={value}</span>
          ))}
        </div>
        {stats.rows.map((row) => (
          <div
            className="categorical-relation-row"
            key={row.featureValue}
            role="row"
            style={{ gridTemplateColumns: `minmax(140px, 1.3fr) 72px repeat(${stats.comparisonValues.length}, minmax(130px, 1fr))` }}
          >
            <strong role="cell">{row.featureValue}</strong>
            <span role="cell">{formatInteger(row.count)}</span>
            {row.cells.map((cell) => (
              <span
                className="categorical-relation-cell"
                key={cell.comparisonValue}
                role="cell"
                style={stats.graphicSummaries ? { backgroundColor: `rgba(46, 163, 154, ${Math.min(0.42, 0.04 + cell.rowShare * 0.42)})` } : undefined}
                title={`Lift ${formatNumber(cell.lift)} / Pearson residual ${formatSignedNumber(cell.residual)}`}
              >
                <b>{formatInteger(cell.count)} ({formatPercent(cell.rowShare)})</b>
                <em>lift {formatNumber(cell.lift)} / resid {formatSignedNumber(cell.residual)}</em>
              </span>
            ))}
          </div>
        ))}
      </div>
      {stats.sparseCellShare > 0.2 && (
        <div className="insight-item">
          Many expected cell counts are below 5; treat chi-square and Cramer's V as exploratory signals.
        </div>
      )}
    </>
  );
}

function SegmentScanResults({ profile }: { profile: SegmentProfile }) {
  const categorical = profile.targetType === "categorical";
  const maximumDifference = Math.max(...profile.results.map((item) => Math.abs(item.difference)), Number.EPSILON);
  return (
    <>
      <div className="segment-results-table">
        <div className={`segment-result-row segment-result-head ${categorical ? "categorical" : "continuous"}`}>
          <span>Segment</span>
          <span>Rows</span>
          <span>Support</span>
          <span>{categorical ? "Target rate" : "Mean"}</span>
          <span>Baseline</span>
          <span>Difference</span>
          {categorical ? <span title="Segment rate divided by the population rate">Lift</span> : <span title="Difference from the rest of the population in pooled standard deviations">Cohen's d</span>}
          <span title={categorical ? "Weighted Relative Accuracy: support multiplied by the target-rate difference" : "Support multiplied by Cohen's d"}>
            {categorical ? "WRAcc" : "Impact"}
          </span>
          <span>{categorical ? "Rate 95% CI" : "Mean 95% CI"}</span>
        </div>
        {profile.results.map((result) => {
          const barWidth = `${Math.max(2, (Math.abs(result.difference) / maximumDifference) * 50)}%`;
          return (
            <div className={`segment-result-row ${categorical ? "categorical" : "continuous"}`} key={`${result.columns.join("|")}:${result.segment}:${result.targetValue}`}>
              <strong title={result.columns.join(" + ")}>{result.segment}</strong>
              <span>{formatInteger(result.count)}</span>
              <span>{formatPercent(result.support)}</span>
              <span>{formatSegmentMetric(result.segmentValue, result.format)}</span>
              <span>{formatSegmentMetric(result.baseline, result.format)}</span>
              <span className={result.difference >= 0 ? "positive-difference" : "negative-difference"}>
                {profile.graphicSummaries && <i className="segment-difference-bar" style={{ width: barWidth }} />}
                {formatSignedSegmentMetric(result.difference, result.format)}
              </span>
              <span>{categorical ? `${formatNumber(result.relativeLift ?? 0)}x` : formatSignedNumber(result.effectSize ?? 0)}</span>
              <span>{formatSignedNumber(result.score)}</span>
              <span>{result.confidenceInterval ? `${formatSegmentMetric(result.confidenceInterval[0], result.format)} - ${formatSegmentMetric(result.confidenceInterval[1], result.format)}` : "n/a"}</span>
            </div>
          );
        })}
      </div>
      <p className="segment-method-note">
        Minimum segment size: {formatInteger(profile.minimumSegmentSize)} rows. Ranked by coverage-adjusted impact; results are exploratory associations, not causal effects.
      </p>
    </>
  );
}

function MiniScatterPlot({ plot }: { plot: ScatterPlot }) {
  const width = 640;
  const height = 220;
  const padding = { top: 14, right: 18, bottom: 38, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xRange = plot.xMax - plot.xMin || 1;
  const yRange = plot.yMax - plot.yMin || 1;
  const xToPx = (value: number) => padding.left + ((value - plot.xMin) / xRange) * plotWidth;
  const yToPx = (value: number) => padding.top + plotHeight - ((value - plot.yMin) / yRange) * plotHeight;
  const xTicks = [plot.xMin, plot.xMin + xRange / 2, plot.xMax];
  const yTicks = [plot.yMin, plot.yMin + yRange / 2, plot.yMax];
  const sampledPoints = plot.points.length > 700
    ? plot.points.filter((_, index) => index % Math.ceil(plot.points.length / 700) === 0)
    : plot.points;

  return (
    <div className="scatter-plot" aria-label={`${plot.yColumn} by ${plot.xColumn} scatter plot`}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <g className="density-grid">
          {yTicks.map((tick) => (
            <line key={`y-${tick}`} x1={padding.left} x2={width - padding.right} y1={yToPx(tick)} y2={yToPx(tick)} />
          ))}
          {xTicks.map((tick) => (
            <line key={`x-${tick}`} x1={xToPx(tick)} x2={xToPx(tick)} y1={padding.top} y2={height - padding.bottom} />
          ))}
        </g>
        <line className="density-axis" x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} />
        <line className="density-axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} />
        {sampledPoints.map((point, index) => (
          <circle
            className="scatter-point"
            cx={xToPx(point.x)}
            cy={yToPx(point.y)}
            key={`${point.x}-${point.y}-${index}`}
            r="2.6"
          />
        ))}
        {plot.trendLine && (
          <line
            className="scatter-trend"
            x1={xToPx(plot.trendLine.x1)}
            x2={xToPx(plot.trendLine.x2)}
            y1={yToPx(plot.trendLine.y1)}
            y2={yToPx(plot.trendLine.y2)}
          />
        )}
        <g className="density-labels">
          {xTicks.map((tick) => (
            <text key={tick} x={xToPx(tick)} y={height - 20} textAnchor="middle">
              {formatNumber(tick)}
            </text>
          ))}
          {yTicks.map((tick) => (
            <text key={tick} x={padding.left - 8} y={yToPx(tick) + 4} textAnchor="end">
              {formatNumber(tick)}
            </text>
          ))}
          <text x={padding.left + plotWidth / 2} y={height - 4} textAnchor="middle">{plot.xColumn}</text>
          <text transform={`translate(12 ${padding.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">{plot.yColumn}</text>
        </g>
      </svg>
    </div>
  );
}

function MiniDensityPlot({ plot }: { plot: DensityPlot | null }) {
  if (!plot || plot.series.length === 0 || plot.yMax <= 0) {
    return <div className="empty-state compact-empty">No density distribution available</div>;
  }
  const width = 640;
  const height = 190;
  const padding = { top: 14, right: 18, bottom: 28, left: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xRange = plot.xMax - plot.xMin || 1;
  const xToPx = (value: number) => padding.left + ((value - plot.xMin) / xRange) * plotWidth;
  const yToPx = (value: number) => padding.top + plotHeight - (value / plot.yMax) * plotHeight;
  const baseline = padding.top + plotHeight;
  const xTicks = [plot.xMin, plot.xMin + xRange / 2, plot.xMax];
  const yTicks = [0, plot.yMax / 2, plot.yMax];

  return (
    <div className="density-plot" aria-label="Grouped density plot">
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <g className="density-grid">
          {yTicks.map((tick) => (
            <line
              key={tick}
              x1={padding.left}
              x2={width - padding.right}
              y1={yToPx(tick)}
              y2={yToPx(tick)}
            />
          ))}
        </g>
        <line className="density-axis" x1={padding.left} x2={width - padding.right} y1={baseline} y2={baseline} />
        <line className="density-axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={baseline} />
        {plot.series.map((series) => {
          const linePath = densityLinePath(series.points, xToPx, yToPx);
          const areaPath = densityAreaPath(series.points, xToPx, yToPx, baseline);
          return (
            <g key={series.group}>
              <path d={areaPath} fill={series.color} opacity="0.22" />
              <path d={linePath} fill="none" stroke={series.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </g>
          );
        })}
        <g className="density-labels">
          {xTicks.map((tick) => (
            <text key={tick} x={xToPx(tick)} y={height - 8} textAnchor="middle">
              {formatNumber(tick)}
            </text>
          ))}
          {yTicks.map((tick) => (
            <text key={tick} x={padding.left - 8} y={yToPx(tick) + 4} textAnchor="end">
              {formatNumber(tick)}
            </text>
          ))}
        </g>
      </svg>
      <div className="density-legend">
        {plot.series.map((series) => (
          <span key={series.group}>
            <i style={{ background: series.color }} />
            {series.group}
          </span>
        ))}
      </div>
    </div>
  );
}

function densityLinePath(
  points: DensitySeries["points"],
  xToPx: (value: number) => number,
  yToPx: (value: number) => number
) {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xToPx(point.x).toFixed(2)} ${yToPx(point.y).toFixed(2)}`)
    .join(" ");
}

function densityAreaPath(
  points: DensitySeries["points"],
  xToPx: (value: number) => number,
  yToPx: (value: number) => number,
  baseline: number
) {
  if (points.length === 0) {
    return "";
  }
  const start = points[0];
  const end = points.at(-1) ?? start;
  return [
    `M ${xToPx(start.x).toFixed(2)} ${baseline.toFixed(2)}`,
    densityLinePath(points, xToPx, yToPx).replace(/^M/, "L"),
    `L ${xToPx(end.x).toFixed(2)} ${baseline.toFixed(2)}`,
    "Z"
  ].join(" ");
}

function relationCardKey(relation: TargetRelationProfile) {
  return `${relation.comparisonColumn}\u0000${relation.feature}`;
}

function MiniDiscreteDistribution({
  values,
  limit
}: {
  values: Array<{ value: DatasetCellValue; count: number; share: number }>;
  limit: number;
}) {
  const visibleValues = values.slice(0, limit);
  if (visibleValues.length === 0) {
    return <div className="empty-state compact-empty">No distribution available</div>;
  }

  return (
    <div className="mini-discrete-distribution" aria-label="Value distribution">
      {visibleValues.map((item) => (
        <div className="discrete-bar-row" key={displayValue(item.value)} title={`${displayValue(item.value)}: ${formatInteger(item.count)}`}>
          <span>{displayValue(item.value)}</span>
          <div className="discrete-bar-track" aria-hidden="true">
            <div style={{ width: `${Math.max(4, item.share * 100)}%` }} />
          </div>
          <strong>{formatPercent(item.share)}</strong>
        </div>
      ))}
    </div>
  );
}

function ProfileFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="profile-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DataBrowsingPanel({
  datasets,
  datasetId,
  setDatasetId,
  onRefresh,
  setNotice,
  visualizationDrill,
  onVisualizationDrillConsumed,
  allowPersistence = true
}: {
  datasets: DataAsset[];
  datasetId: string;
  setDatasetId: (datasetId: string) => void;
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
  visualizationDrill: VisualizationDrillRequest | null;
  onVisualizationDrillConsumed: (requestId: string) => void;
  allowPersistence?: boolean;
}) {
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [isSqlOpen, setIsSqlOpen] = useState(false);
  const [isSaveViewOpen, setIsSaveViewOpen] = useState(false);
  const [isSavingView, setIsSavingView] = useState(false);
  const [customSql, setCustomSql] = useState("");
  const [isSqlResult, setIsSqlResult] = useState(false);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Record<string, ColumnFilterConfig>>({});
  const [aggregationFilters, setAggregationFilters] = useState<Record<string, ColumnFilterConfig>>({});
  const [sortRules, setSortRules] = useState<SortRule[]>([]);
  const [grouping, setGrouping] = useState<Record<string, GroupingColumnConfig>>({});
  const [sortingCollapsed, setSortingCollapsed] = useState(true);
  const [filtersCollapsed, setFiltersCollapsed] = useState(true);
  const [groupingCollapsed, setGroupingCollapsed] = useState(true);
  const [aggregationFiltersCollapsed, setAggregationFiltersCollapsed] = useState(true);
  const [columnsCollapsed, setColumnsCollapsed] = useState(true);
  const [hiddenSourceColumns, setHiddenSourceColumns] = useState<Record<string, boolean>>({});
  const [expandedGroupingColumns, setExpandedGroupingColumns] = useState<Record<string, boolean>>({});
  const [showControlsOnlySelected, setShowControlsOnlySelected] = useState(false);
  const [tableScrollWidth, setTableScrollWidth] = useState(900);
  const [drilldown, setDrilldown] = useState<{
    title: string;
    rows: Array<Record<string, DatasetCellValue>>;
    columns: DatasetPreview["columns"];
    initialHiddenColumns: Record<string, boolean>;
    initialSortRules: SortRule[];
  } | null>(null);
  const [page, setPage] = useState(1);
  const topScrollRef = useRef<HTMLDivElement | null>(null);
  const tableScrollRef = useRef<HTMLDivElement | null>(null);
  const pageSize = 25;
  const selectedDataset = datasets.find((dataset) => dataset.id === datasetId) ?? null;
  const rolesMetadata = useMemo(
    () => readRolesMetadata(selectedDataset, datasets, preview?.columns.map((column) => column.name) ?? []),
    [datasets, preview, selectedDataset]
  );

  useEffect(() => {
    resetViewState();
    if (!datasetId) {
      setPreview(null);
      setError("");
      return;
    }

    let isCurrent = true;
    setIsLoading(true);
    setError("");
    const drillRequest = visualizationDrill?.datasetId === datasetId ? visualizationDrill : null;
    const loadRequest = drillRequest
      ? api.drillDataset(datasetId, { filters: drillRequest.filters, limit: DATA_BROWSER_DRILL_PREVIEW_LIMIT })
      : api.previewDataset(datasetId);
    loadRequest
      .then((result) => {
        if (!isCurrent) {
          return;
        }
        setPreview(result);
        if (drillRequest) {
          setFilters(browserFiltersFromVisualizationDrill(drillRequest));
          setFiltersCollapsed(false);
          setNotice(`Drill loaded ${result.returned_count} of ${result.row_count} matching rows from the full dataset`);
          onVisualizationDrillConsumed(drillRequest.id);
        } else {
          setNotice(`Loaded ${result.returned_count} of ${result.row_count} rows`);
        }
      })
      .catch((loadError) => {
        if (!isCurrent) {
          return;
        }
        const message = loadError instanceof Error ? loadError.message : "Dataset preview failed";
        setPreview(null);
        setError(message);
        setNotice(message);
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [datasetId]);

  const columns = preview?.columns ?? [];
  const rows = preview?.records ?? [];

  useEffect(() => {
    setGrouping((current) => {
      const columnNames = new Set(columns.map((column) => column.name));
      return Object.fromEntries(
        Object.entries(current).filter(([column]) => columnNames.has(column))
      );
    });
  }, [columns]);

  const filteredRows = useMemo(() => {
    const searchValue = search.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesSearch =
        !searchValue ||
        columns.some((column) => valueToSearchText(row[column.name]).includes(searchValue));
      if (!matchesSearch) {
        return false;
      }
      return columns.every((column) => {
        return matchesFilter(row[column.name], filters[column.name]);
      });
    });
  }, [columns, filters, rows, search]);

  const aggregationResult = useMemo(
    () => buildAggregationResult(filteredRows, columns, grouping),
    [columns, filteredRows, grouping]
  );
  const isAggregationMode = aggregationResult.isActive;
  const rawTableColumns: AggregatedColumn[] = isAggregationMode
    ? aggregationResult.columns
    : columns.map((column) => ({ ...column, sourceColumn: column.name }));
  const allTableColumns = isAggregationMode
    ? orderAggregatedColumns(rawTableColumns, grouping, sortRules)
    : rawTableColumns;
  const tableColumns = isAggregationMode
    ? allTableColumns
    : allTableColumns.filter((column) => !hiddenSourceColumns[column.name]);
  const tableRows = isAggregationMode
    ? aggregationResult.records.filter((row) =>
        allTableColumns.every((column) => matchesFilter(row[column.name], aggregationFilters[column.name]))
      )
    : filteredRows;

  const sortedRows = useMemo(() => {
    return sortRecords(tableRows, sortRules);
  }, [sortRules, tableRows]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const visibleRows = sortedRows.slice((safePage - 1) * pageSize, safePage * pageSize);
  const visibleStart = sortedRows.length === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const visibleEnd = Math.min(safePage * pageSize, sortedRows.length);
  const controlColumns = showControlsOnlySelected
    ? columns.filter((column) => isSourceColumnVisible(column.name))
    : columns;
  const aggregationFilterColumns = showControlsOnlySelected ? tableColumns : allTableColumns;
  const sourceColumnCount = columns.filter((column) => !hiddenSourceColumns[column.name]).length;
  const categoricalValueOptions = useMemo(
    () => buildColumnValueOptions(rows, columns),
    [columns, rows]
  );

  useEffect(() => {
    setHiddenSourceColumns((current) => (
      Object.fromEntries(
        Object.entries(current).filter(([column]) =>
          columns.some((sourceColumn) => sourceColumn.name === column)
        )
      )
    ));
  }, [columns]);

  useEffect(() => {
    const tableScroll = tableScrollRef.current;
    if (!tableScroll) {
      return;
    }

    function measureTableWidth() {
      if (tableScroll) {
        setTableScrollWidth(Math.max(tableScroll.scrollWidth, tableScroll.clientWidth));
      }
    }

    measureTableWidth();
    const resizeObserver = new ResizeObserver(measureTableWidth);
    resizeObserver.observe(tableScroll);
    const animationFrame = window.requestAnimationFrame(measureTableWidth);
    return () => {
      resizeObserver.disconnect();
      window.cancelAnimationFrame(animationFrame);
    };
  }, [tableColumns, visibleRows]);

  function resetViewState() {
    setSearch("");
    setFilters({});
    setAggregationFilters({});
    setSortRules([]);
    setGrouping({});
    setExpandedGroupingColumns({});
    setHiddenSourceColumns({});
    setShowControlsOnlySelected(false);
    setPage(1);
  }

  async function resetToDatasetPreview() {
    resetViewState();
    setCustomSql("");
    setIsSqlResult(false);
    if (!datasetId) {
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const result = await api.previewDataset(datasetId);
      setPreview(result);
      setNotice(`Loaded ${result.returned_count} of ${result.row_count} rows`);
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Dataset preview failed";
      setPreview(null);
      setError(message);
      setNotice(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function runCustomSql(sql: string) {
    if (!selectedDataset) {
      setNotice("Choose a dataset first");
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const result = await api.queryDataset(selectedDataset.id, sql);
      setPreview(result);
      resetViewState();
      setCustomSql(sql);
      setIsSqlResult(true);
      setNotice(`SQL returned ${result.returned_count} of ${result.row_count} rows`);
      setIsSqlOpen(false);
    } catch (queryError) {
      const message = queryError instanceof Error ? queryError.message : "SQL query failed";
      setError(message);
      setNotice(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function saveDataView(name: string) {
    if (!selectedDataset) {
      setNotice("Choose a dataset first");
      return;
    }
    setIsSavingView(true);
    try {
      await api.createDataView({
        name,
        source_dataset_id: selectedDataset.id,
        definition: buildDataViewDefinition({
          search,
          filters,
          aggregationFilters,
          sortRules,
          grouping,
          visibleColumns: tableColumns.map((column) => column.name),
          customSql: isSqlResult ? customSql : "",
          isSqlResult
        })
      });
      await onRefresh();
      setIsSaveViewOpen(false);
      setNotice(`Saved Data View ${name}`);
    } catch (saveError) {
      setNotice(saveError instanceof Error ? saveError.message : "Saving Data View failed");
    } finally {
      setIsSavingView(false);
    }
  }

  function updateSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function updateFilter(column: DatasetPreview["columns"][number], value: string) {
    setFilters((current) => ({
      ...current,
      [column.name]: {
        operator: current[column.name]?.operator ?? defaultFilterOperator(column.type),
        value
      }
    }));
    setPage(1);
  }

  function updateFilterOperator(column: string, operator: FilterOperator) {
    setFilters((current) => ({
      ...current,
      [column]: {
        operator,
        value: current[column]?.value ?? "",
        values: current[column]?.values ?? []
      }
    }));
    setPage(1);
  }

  function updateFilterValues(column: string, values: string[]) {
    setFilters((current) => ({
      ...current,
      [column]: {
        operator: current[column]?.operator ?? "in",
        value: values[0] ?? "",
        values
      }
    }));
    setPage(1);
  }

  function updateAggregationFilter(column: AggregatedColumn, value: string) {
    setAggregationFilters((current) => ({
      ...current,
      [column.name]: {
        operator: current[column.name]?.operator ?? defaultFilterOperator(column.type),
        value
      }
    }));
    setPage(1);
  }

  function updateAggregationFilterOperator(column: string, operator: FilterOperator) {
    setAggregationFilters((current) => ({
      ...current,
      [column]: {
        operator,
        value: current[column]?.value ?? "",
        values: current[column]?.values ?? []
      }
    }));
    setPage(1);
  }

  function updateAggregationFilterValues(column: string, values: string[]) {
    setAggregationFilters((current) => ({
      ...current,
      [column]: {
        operator: current[column]?.operator ?? "in",
        value: values[0] ?? "",
        values
      }
    }));
    setPage(1);
  }

  function cycleSort(column: string) {
    setSortRules((current) => {
      const existing = current.find((rule) => rule.column === column);
      if (!existing) {
        return [{ column, direction: "asc" }];
      }
      if (existing.direction === "asc") {
        return [{ column, direction: "desc" }];
      }
      return [];
    });
  }

  function addSortRule() {
    const nextColumn = allTableColumns.find((column) => !sortRules.some((rule) => rule.column === column.name));
    if (!nextColumn) {
      return;
    }
    setSortRules((current) => [...current, { column: nextColumn.name, direction: "asc" }]);
  }

  function updateSortRule(index: number, patch: Partial<SortRule>) {
    setSortRules((current) =>
      current.map((rule, ruleIndex) => ruleIndex === index ? { ...rule, ...patch } : rule)
    );
    setPage(1);
  }

  function removeSortRule(index: number) {
    setSortRules((current) => current.filter((_, ruleIndex) => ruleIndex !== index));
    setPage(1);
  }

  function moveSortRule(index: number, direction: -1 | 1) {
    setSortRules((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) {
        return current;
      }
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(nextIndex, 0, item);
      return next;
    });
  }

  function updateGroupingRole(column: DatasetPreview["columns"][number], role: GroupingRole) {
    setGrouping((current) => ({
      ...current,
      [column.name]: {
        role,
        aggregate: current[column.name]?.aggregate ?? defaultAggregationFunction(column, rolesMetadata)
      }
    }));
    setSortRules([]);
    setPage(1);
  }

  function updateAggregationFunction(column: string, aggregate: AggregationFunction) {
    setGrouping((current) => ({
      ...current,
      [column]: {
        role: current[column]?.role ?? "aggregate",
        aggregate
      }
    }));
    setSortRules([]);
    setPage(1);
  }

  function toggleGroupingColumn(column: string) {
    setExpandedGroupingColumns((current) => ({
      ...current,
      [column]: !current[column]
    }));
  }

  function syncHorizontalScroll(source: "top" | "table") {
    const sourceElement = source === "top" ? topScrollRef.current : tableScrollRef.current;
    const targetElement = source === "top" ? tableScrollRef.current : topScrollRef.current;
    if (!sourceElement || !targetElement) {
      return;
    }
    targetElement.scrollLeft = sourceElement.scrollLeft;
  }

  function toggleColumnVisibility(column: string) {
    setHiddenSourceColumns((current) => ({
      ...current,
      [column]: !current[column]
    }));
  }

  function showAllColumns() {
    setHiddenSourceColumns({});
  }

  function hideAllColumns() {
    setHiddenSourceColumns(Object.fromEntries(columns.map((column) => [column.name, true])));
  }

  function showOnlyColumns(predicate: (column: DatasetPreview["columns"][number]) => boolean) {
    setHiddenSourceColumns(Object.fromEntries(
      columns.map((column) => [column.name, !predicate(column)])
    ));
  }

  const visibleColumnCount = tableColumns.length;

  function isSourceColumnVisible(columnName: string) {
    return !hiddenSourceColumns[columnName];
  }

  function jumpToPage(value: string) {
    const nextPage = Number(value);
    if (!Number.isFinite(nextPage)) {
      return;
    }
    setPage(Math.max(1, Math.min(pageCount, Math.trunc(nextPage))));
  }

  function openDrilldown(row: Record<string, DatasetCellValue>) {
    const groupColumns = columns.filter((column) => grouping[column.name]?.role === "group");
    const detailRows = groupColumns.length === 0
      ? filteredRows
      : filteredRows.filter((record) =>
          groupColumns.every((column) => displayValue(record[column.name]) === displayValue(row[column.name]))
        );
    const title = groupColumns.length === 0
      ? "All filtered records"
      : groupColumns.map((column) => `${column.name}: ${displayValue(row[column.name])}`).join(" / ");
    setDrilldown({
      title,
      rows: detailRows,
      columns,
      initialHiddenColumns: hiddenSourceColumns,
      initialSortRules: sortRules.filter((rule) => columns.some((column) => column.name === rule.column))
    });
  }

  function renderRows(
    tableRows: Array<Record<string, DatasetCellValue>>,
    visibleColumns: AggregatedColumn[]
  ) {
    return tableRows.map((row, rowIndex) => (
      <tr key={`${safePage}-${rowIndex}`}>
        {isAggregationMode && (
          <td className="cell-action">
            <button
              aria-label="Drill down"
              className="icon-button table-action"
              onClick={() => openDrilldown(row)}
              title="Drill down"
              type="button"
            >
              <Drill size={15} />
            </button>
          </td>
        )}
        {visibleColumns.map((column) => (
          <td className={`cell-${cellKind(row[column.name])}`} key={column.name}>
            {displayValue(row[column.name])}
          </td>
        ))}
      </tr>
    ));
  }

  if (datasets.length === 0) {
    return (
      <div className="panel">
        <div className="empty-state">No datasets available</div>
      </div>
    );
  }

  return (
    <div className="data-browser-layout">
      <DeferredPanel>
        <TimeSeriesWorkbench
          columns={columns}
          datasetId={datasetId}
          defaultTimeColumn={rolesMetadata.timestamp_column}
          defaultValueColumn={rolesMetadata.target_column}
          mode="browser"
          onChronologicalSort={(column) => {
            setSortRules([{ column, direction: "asc" }]);
            setSortingCollapsed(false);
            setPage(1);
          }}
        />
      </DeferredPanel>
      <main className="panel data-browser-main">
        {isLoading && <div className="empty-state">Loading dataset</div>}
        {!isLoading && error && <div className="empty-state error-state">{error}</div>}
        {!isLoading && !error && preview && preview.row_count === 0 && (
          <div className="empty-state">Dataset is empty</div>
        )}
        {!isLoading && !error && preview && preview.row_count > 0 && sortedRows.length === 0 && (
          <div className="empty-state">No results match current search and filters</div>
        )}
        {!isLoading && !error && preview && preview.row_count > 0 && sortedRows.length > 0 && visibleColumnCount === 0 && (
          <div className="empty-state">All columns are hidden</div>
        )}

        {!isLoading && !error && preview && preview.row_count > 0 && sortedRows.length > 0 && visibleColumnCount > 0 && (
          <>
            <div className="browser-summary">
              <span>
                Showing {visibleStart}-{visibleEnd} of {sortedRows.length} visible {isAggregationMode ? "groups" : "records"}
              </span>
              <span>{preview.row_count} total rows</span>
              {isAggregationMode && <span>Aggregated from {filteredRows.length} filtered records</span>}
              {preview.returned_count < preview.row_count && (
                <span>Preview limited to {preview.returned_count} rows</span>
              )}
            </div>

            <div
              className="data-table-top-scroll"
              onScroll={() => syncHorizontalScroll("top")}
              ref={topScrollRef}
            >
              <div style={{ width: `${tableScrollWidth}px` }} />
            </div>

            <div
              className="data-table-wrap"
              onScroll={() => syncHorizontalScroll("table")}
              ref={tableScrollRef}
            >
              <table className="data-table">
                <thead>
                  <tr>
                    {isAggregationMode && <th className="action-column">Drill</th>}
                    {tableColumns.map((column) => (
                      <th key={column.name}>
                        <button onClick={() => cycleSort(column.name)} type="button">
                          <span>{column.name}</span>
                          <em>{column.type}</em>
                          <strong>{sortLabel(column.name, sortRules)}</strong>
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>{renderRows(visibleRows, tableColumns)}</tbody>
              </table>
            </div>

            <div className="pagination">
              <button
                className="secondary-button"
                disabled={safePage === 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                type="button"
              >
                Previous
              </button>
              <span>
                Page
                <input
                  aria-label="Page number"
                  className="page-input"
                  max={pageCount}
                  min={1}
                  onChange={(event) => jumpToPage(event.target.value)}
                  type="number"
                  value={safePage}
                />
                of {pageCount}
              </span>
              <button
                className="secondary-button"
                disabled={safePage === pageCount}
                onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                type="button"
              >
                Next
              </button>
            </div>
          </>
        )}
      </main>

      <aside className="panel data-browser-sidebar">
        <div className="browser-toolbar">
          <label>
            Dataset
            <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {datasetVersionLabel(dataset, datasets)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Search
            <div className="input-with-icon">
              <Search size={16} />
              <input
                value={search}
                onChange={(event) => updateSearch(event.target.value)}
                placeholder="Search all columns"
              />
            </div>
          </label>
          <button className="secondary-button toolbar-button" onClick={resetToDatasetPreview} type="button">
            <RotateCcw size={16} />
            Reset view
          </button>
          <button
            className={isSqlResult ? "secondary-button toolbar-button active" : "secondary-button toolbar-button"}
            onClick={() => setIsSqlOpen(true)}
            type="button"
          >
            <Database size={16} />
            Custom SQL
          </button>
          {allowPersistence && (
            <button
              className="primary-button toolbar-button"
              disabled={!preview || isSavingView}
              onClick={() => setIsSaveViewOpen(true)}
              type="button"
            >
              <Save size={16} />
              Save View
            </button>
          )}
        </div>

        {columns.length > 0 && (
          <div className={columnsCollapsed ? "columns-section collapsed" : "columns-section"}>
            <button
              aria-expanded={!columnsCollapsed}
              className="section-toggle"
              onClick={() => setColumnsCollapsed((current) => !current)}
              type="button"
            >
              {columnsCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <Table2 size={16} />
              <strong>Columns selection</strong>
              <span>{sourceColumnCount}/{columns.length}</span>
            </button>
            {!columnsCollapsed && (
              <div className="columns-selection-body">
                <div className="preset-row">
                  <button className="secondary-button compact-button" onClick={showAllColumns} type="button">
                    Show all
                  </button>
                  <button className="secondary-button compact-button" onClick={hideAllColumns} type="button">
                    Hide all
                  </button>
                  <button
                    className="secondary-button compact-button"
                    onClick={() => showOnlyColumns((column) => column.type === "number")}
                    type="button"
                  >
                    Numeric only
                  </button>
                  <button
                    className="secondary-button compact-button"
                    onClick={() => showOnlyColumns((column) => ["text", "boolean", "date"].includes(column.type))}
                    type="button"
                  >
                    Non-numeric
                  </button>
                  <button
                    className="secondary-button compact-button"
                    onClick={() => showOnlyColumns((column) => {
                      const role = rolesMetadata.column_roles[column.name] ?? "";
                      return !["identifier", "timestamp", "period_id", "ignored"].includes(role);
                    })}
                    type="button"
                  >
                    Model-ready
                  </button>
                  <button
                    className="secondary-button compact-button"
                    onClick={() => showOnlyColumns((column) => {
                      const role = rolesMetadata.column_roles[column.name] ?? "";
                      return ["identifier", "timestamp", "period_id", "target"].includes(role)
                        || column.name === "records";
                    })}
                    type="button"
                  >
                    Essentials
                  </button>
                </div>
                <div className="column-check-list">
                  {columns.map((column) => (
                    <label className="check-tile compact-check" key={column.name}>
                      <input
                        checked={!hiddenSourceColumns[column.name]}
                        onChange={() => toggleColumnVisibility(column.name)}
                        type="checkbox"
                      />
                      <span>{column.name}</span>
                      <em>{column.type}</em>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {allTableColumns.length > 0 && (
          <div className={sortingCollapsed ? "sorting-section collapsed" : "sorting-section"}>
            <button
              aria-expanded={!sortingCollapsed}
              className="section-toggle"
              onClick={() => setSortingCollapsed((current) => !current)}
              type="button"
            >
              {sortingCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <ListChecks size={16} />
              <strong>Sorting options</strong>
              <span>{sortRules.length}</span>
            </button>
            {!sortingCollapsed && (
              <div className="sorting-body">
                <div className="section-actions">
                  <button className="secondary-button compact-button" onClick={addSortRule} type="button">
                    Add sort
                  </button>
                  <button className="secondary-button compact-button" onClick={() => setSortRules([])} type="button">
                    Clear
                  </button>
                </div>
                <div className="sort-rule-list">
                  {sortRules.map((rule, index) => (
                    <div className="sort-rule-row" key={`${rule.column}-${index}`}>
                      <strong>{index + 1}</strong>
                      <label>
                        Column
                        <select
                          value={rule.column}
                          onChange={(event) => updateSortRule(index, { column: event.target.value })}
                        >
                          {allTableColumns.map((column) => (
                            <option key={column.name} value={column.name}>
                              {column.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="field-group">
                        <span>Direction</span>
                        <SortDirectionToggle
                          value={rule.direction}
                          onChange={(direction) => updateSortRule(index, { direction })}
                        />
                      </div>
                      <div className="sort-rule-actions">
                        <button
                          className="secondary-button compact-button"
                          disabled={index === 0}
                          onClick={() => moveSortRule(index, -1)}
                          type="button"
                        >
                          Up
                        </button>
                        <button
                          className="secondary-button compact-button"
                          disabled={index === sortRules.length - 1}
                          onClick={() => moveSortRule(index, 1)}
                          type="button"
                        >
                          Down
                        </button>
                        <button className="secondary-button compact-button" onClick={() => removeSortRule(index)} type="button">
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                  {sortRules.length === 0 && (
                    <div className="empty-state compact-empty">No sort rules</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {columns.length > 0 && (
          <div className={filtersCollapsed ? "filter-section collapsed" : "filter-section"}>
            <button
              aria-expanded={!filtersCollapsed}
              className="section-toggle"
              onClick={() => setFiltersCollapsed((current) => !current)}
              type="button"
            >
              {filtersCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <Filter size={16} />
              <strong>Column filters</strong>
            </button>
            {!filtersCollapsed && (
              <>
                <div className="section-actions">
                  <button
                    className={showControlsOnlySelected ? "secondary-button compact-button active" : "secondary-button compact-button"}
                    onClick={() => setShowControlsOnlySelected((current) => !current)}
                    type="button"
                  >
                    Show only selected
                  </button>
                </div>
                <div className="filter-grid">
                  {controlColumns.map((column) => {
                    const config = filters[column.name] ?? { operator: defaultFilterOperator(column.type), value: "" };
                    const role = columnRoleForColumn(column, rolesMetadata);
                    const operators = filterOperatorsForColumn(column.type, role);
                    const valueOptions = categoricalValueOptions[column.name] ?? [];
                    const useValueList = valueOptions.length > 0 && ["equals", "in"].includes(config.operator);
                    return (
                      <div className="filter-row" key={column.name}>
                        <strong>{column.name}</strong>
                        <span>{column.type} / {columnRoleLabel(role)}</span>
                        <label>
                          Operator
                          <select
                            value={config.operator}
                            onChange={(event) => updateFilterOperator(column.name, event.target.value as FilterOperator)}
                          >
                            {operators.map((operator) => (
                              <option key={operator} value={operator}>
                                {filterOperatorLabels[operator]}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Value
                          {useValueList && config.operator === "in" ? (
                            <select
                              multiple
                              value={config.values ?? []}
                              onChange={(event) =>
                                updateFilterValues(
                                  column.name,
                                  Array.from(event.currentTarget.selectedOptions).map((option) => option.value)
                                )
                              }
                            >
                              {valueOptions.map((value) => (
                                <option key={value} value={value}>
                                  {value}
                                </option>
                              ))}
                            </select>
                          ) : useValueList ? (
                            <select
                              value={config.value}
                              onChange={(event) => updateFilter(column, event.target.value)}
                            >
                              <option value="">Any value</option>
                              {valueOptions.map((value) => (
                                <option key={value} value={value}>
                                  {value}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <input
                              disabled={operatorDoesNotNeedValue(config.operator)}
                              value={config.value}
                              onChange={(event) => updateFilter(column, event.target.value)}
                              placeholder={`Filter ${column.type}`}
                            />
                          )}
                        </label>
                      </div>
                    );
                  })}
                  {controlColumns.length === 0 && (
                    <div className="empty-state compact-empty">No selected columns</div>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {columns.length > 0 && (
          <div className={groupingCollapsed ? "grouping-section collapsed" : "grouping-section"}>
            <button
              aria-expanded={!groupingCollapsed}
              className="section-toggle"
              onClick={() => setGroupingCollapsed((current) => !current)}
              type="button"
            >
              {groupingCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <BarChart3 size={16} />
              <strong>Grouping options</strong>
            </button>
            {!groupingCollapsed && (
              <>
                <div className="section-actions">
                  <button
                    className={showControlsOnlySelected ? "secondary-button compact-button active" : "secondary-button compact-button"}
                    onClick={() => setShowControlsOnlySelected((current) => !current)}
                    type="button"
                  >
                    Show only selected
                  </button>
                </div>
                <div className="aggregation-grid">
                {controlColumns.map((column) => {
                  const config = grouping[column.name] ?? {
                    role: "none" as GroupingRole,
                    aggregate: defaultAggregationFunction(column, rolesMetadata)
                  };
                  const availableFunctions = aggregationFunctionsForColumn(column, rolesMetadata);
                  const isColumnExpanded = Boolean(expandedGroupingColumns[column.name]);
                  return (
                    <div className={isColumnExpanded ? "aggregation-row expanded" : "aggregation-row"} key={column.name}>
                      <button
                        aria-expanded={isColumnExpanded}
                        className="aggregation-toggle"
                        onClick={() => toggleGroupingColumn(column.name)}
                        type="button"
                      >
                        {isColumnExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                        <span>
                          <strong>{column.name}</strong>
                          <em>{column.type} / {columnRoleLabel(columnRoleForColumn(column, rolesMetadata))}</em>
                        </span>
                        <small>
                          {groupingRoleOptions.find((option) => option.value === config.role)?.label}
                          {config.role === "aggregate" ? ` / ${aggregationFunctionLabels[config.aggregate]}` : ""}
                        </small>
                      </button>
                      {isColumnExpanded && (
                        <div className="aggregation-controls">
                          <div className="field-group">
                            <span>Role</span>
                            <div className="segmented-control three-way" role="group" aria-label={`${column.name} grouping role`}>
                              {groupingRoleOptions.map((option) => (
                                <button
                                  className={config.role === option.value ? "active" : ""}
                                  key={option.value}
                                  onClick={() => updateGroupingRole(column, option.value)}
                                  type="button"
                                >
                                  {option.label}
                                </button>
                              ))}
                            </div>
                          </div>
                          {config.role === "aggregate" && (
                            <label>
                              Function
                              <select
                                value={availableFunctions.includes(config.aggregate) ? config.aggregate : availableFunctions[0]}
                                onChange={(event) =>
                                  updateAggregationFunction(column.name, event.target.value as AggregationFunction)
                                }
                              >
                                {availableFunctions.map((aggregate) => (
                                  <option key={aggregate} value={aggregate}>
                                    {aggregationFunctionLabels[aggregate]}
                                  </option>
                                ))}
                              </select>
                            </label>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                  {controlColumns.length === 0 && (
                    <div className="empty-state compact-empty">No selected columns</div>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {isAggregationMode && allTableColumns.length > 0 && (
          <div className={aggregationFiltersCollapsed ? "having-section collapsed" : "having-section"}>
            <button
              aria-expanded={!aggregationFiltersCollapsed}
              className="section-toggle"
              onClick={() => setAggregationFiltersCollapsed((current) => !current)}
              type="button"
            >
              {aggregationFiltersCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <Filter size={16} />
              <strong>Aggregation filters</strong>
            </button>
            {!aggregationFiltersCollapsed && (
              <>
                <div className="section-actions">
                  <button
                    className={showControlsOnlySelected ? "secondary-button compact-button active" : "secondary-button compact-button"}
                    onClick={() => setShowControlsOnlySelected((current) => !current)}
                    type="button"
                  >
                    Show only selected
                  </button>
                  <button className="secondary-button compact-button" onClick={() => setAggregationFilters({})} type="button">
                    Clear
                  </button>
                </div>
                <div className="filter-grid">
                  {aggregationFilterColumns.map((column) => {
                    const config = aggregationFilters[column.name] ?? { operator: defaultFilterOperator(column.type), value: "" };
                    const operators = filterOperatorsForColumn(column.type);
                    return (
                      <div className="filter-row" key={column.name}>
                        <strong>{column.name}</strong>
                        <span>{column.type}</span>
                        <label>
                          Operator
                          <select
                            value={config.operator}
                            onChange={(event) => updateAggregationFilterOperator(column.name, event.target.value as FilterOperator)}
                          >
                            {operators.map((operator) => (
                              <option key={operator} value={operator}>
                                {filterOperatorLabels[operator]}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Value
                          <input
                            disabled={operatorDoesNotNeedValue(config.operator)}
                            value={config.value}
                            onChange={(event) => updateAggregationFilter(column, event.target.value)}
                            placeholder={`Filter ${column.type}`}
                          />
                        </label>
                      </div>
                    );
                  })}
                  {aggregationFilterColumns.length === 0 && (
                    <div className="empty-state compact-empty">No selected columns</div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </aside>
      {drilldown && (
        <DrilldownModal
          columns={drilldown.columns}
          initialHiddenColumns={drilldown.initialHiddenColumns}
          initialSortRules={drilldown.initialSortRules}
          onClose={() => setDrilldown(null)}
          rows={drilldown.rows}
          title={drilldown.title}
        />
      )}
      {isSqlOpen && selectedDataset && (
        <CustomSqlModal
          columns={columns}
          dataset={selectedDataset}
          initialSql={customSql}
          onClose={() => setIsSqlOpen(false)}
          onRun={runCustomSql}
        />
      )}
      {isSaveViewOpen && selectedDataset && (
        <SaveViewModal
          defaultName={`${selectedDataset.name} view`}
          isSaving={isSavingView}
          onClose={() => setIsSaveViewOpen(false)}
          onSave={saveDataView}
        />
      )}
    </div>
  );
}

function SortDirectionToggle({
  value,
  onChange
}: {
  value: SortDirection;
  onChange: (value: SortDirection) => void;
}) {
  return (
    <div className="segmented-control two-way" role="group" aria-label="Sort direction">
      <button
        className={value === "asc" ? "active" : ""}
        onClick={() => onChange("asc")}
        type="button"
      >
        Asc
      </button>
      <button
        className={value === "desc" ? "active" : ""}
        onClick={() => onChange("desc")}
        type="button"
      >
        Desc
      </button>
    </div>
  );
}

function SaveViewModal({
  defaultName,
  isSaving,
  onClose,
  onSave
}: {
  defaultName: string;
  isSaving: boolean;
  onClose: () => void;
  onSave: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState(defaultName);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (trimmedName) {
      await onSave(trimmedName);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-label="Save Data View" className="save-view-modal" role="dialog">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Data Browser</p>
            <h2>Save View</h2>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close save view">
            <X size={18} />
          </button>
        </header>
        <form className="panel save-view-form" onSubmit={submit}>
          <label>
            View name
            <input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Enter Data View name"
              required
            />
          </label>
          <div className="button-row">
            <button className="primary-button" disabled={isSaving || !name.trim()} type="submit">
              <Save size={16} />
              {isSaving ? "Saving" : "Save View"}
            </button>
            <button className="secondary-button" onClick={onClose} type="button">
              Cancel
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function CustomSqlModal({
  columns,
  dataset,
  initialSql,
  onClose,
  onRun
}: {
  columns: DatasetPreview["columns"];
  dataset: DataAsset;
  initialSql: string;
  onClose: () => void;
  onRun: (sql: string) => Promise<void>;
}) {
  const tableName = quoteSqlIdentifier(dataset.name);
  const defaultSql = `SELECT *\nFROM ${tableName}\nLIMIT 100`;
  const initialEditorSql = initialSql || defaultSql;
  const [sql, setSql] = useState(initialEditorSql);
  const [isRunning, setIsRunning] = useState(false);
  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  const historyRef = useRef({ entries: [initialEditorSql], index: 0 });
  const sqlFunctions = [
    "COUNT(*)",
    "AVG()",
    "SUM()",
    "MIN()",
    "MAX()",
    "ROUND(, 2)",
    "COALESCE(, 0)",
    "CASE WHEN  THEN  ELSE  END"
  ];

  function setEditorSelection(start?: number, end?: number) {
    const editor = editorRef.current;
    if (!editor || start === undefined) {
      return;
    }
    window.requestAnimationFrame(() => {
      editor.focus();
      editor.selectionStart = start;
      editor.selectionEnd = end ?? start;
    });
  }

  function commitSql(nextSql: string, selectionStart?: number, selectionEnd?: number, recordHistory = true) {
    setSql(nextSql);
    if (recordHistory) {
      const history = historyRef.current;
      if (history.entries[history.index] !== nextSql) {
        history.entries = history.entries.slice(0, history.index + 1);
        history.entries.push(nextSql);
        if (history.entries.length > 100) {
          history.entries.shift();
        }
        history.index = history.entries.length - 1;
      }
    }
    setEditorSelection(selectionStart, selectionEnd);
  }

  function restoreHistory(direction: -1 | 1) {
    const history = historyRef.current;
    const nextIndex = history.index + direction;
    if (nextIndex < 0 || nextIndex >= history.entries.length) {
      return;
    }
    history.index = nextIndex;
    const nextSql = history.entries[nextIndex];
    setSql(nextSql);
    setEditorSelection(nextSql.length);
  }

  function insertText(value: string, selectionStartOffset = value.length, selectionEndOffset = selectionStartOffset) {
    const editor = editorRef.current;
    if (!editor) {
      commitSql(`${sql}${value}`);
      return;
    }
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const nextSql = `${sql.slice(0, start)}${value}${sql.slice(end)}`;
    commitSql(nextSql, start + selectionStartOffset, start + selectionEndOffset);
  }

  function insertSqlFunction(fn: string) {
    const editor = editorRef.current;
    const start = editor?.selectionStart ?? sql.length;
    const end = editor?.selectionEnd ?? sql.length;
    const selectedText = sql.slice(start, end);
    const hasSelection = start !== end;
    let value = fn;
    let cursorOffset = fn.length;

    if (fn === "AVG()" || fn === "SUM()" || fn === "MIN()" || fn === "MAX()") {
      const name = fn.slice(0, -2);
      value = `${name}(${selectedText})`;
      cursorOffset = hasSelection ? value.length : name.length + 1;
    } else if (fn === "ROUND(, 2)") {
      value = `ROUND(${selectedText}, 2)`;
      cursorOffset = hasSelection ? value.length : "ROUND(".length;
    } else if (fn === "COALESCE(, 0)") {
      value = `COALESCE(${selectedText}, 0)`;
      cursorOffset = hasSelection ? value.length : "COALESCE(".length;
    } else if (fn === "CASE WHEN  THEN  ELSE  END") {
      value = hasSelection ? `CASE WHEN ${selectedText} THEN  ELSE  END` : fn;
      cursorOffset = hasSelection ? `CASE WHEN ${selectedText} THEN `.length : "CASE WHEN ".length;
    }

    insertText(value, cursorOffset);
  }

  function changeIndent(shouldOutdent: boolean) {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const lineStart = sql.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    const blockEnd = end > start ? sql.indexOf("\n", end) : -1;
    const lineEnd = blockEnd === -1 ? sql.length : blockEnd;
    const block = sql.slice(lineStart, lineEnd);
    const lines = block.split("\n");

    if (!shouldOutdent) {
      const nextBlock = lines.map((line) => `    ${line}`).join("\n");
      const nextSql = `${sql.slice(0, lineStart)}${nextBlock}${sql.slice(lineEnd)}`;
      commitSql(nextSql, start + 4, end + lines.length * 4);
      return;
    }

    let firstLineDelta = 0;
    let totalDelta = 0;
    const nextBlock = lines
      .map((line, index) => {
        const removableSpaces = line.match(/^ {1,4}/)?.[0].length ?? 0;
        const removeCount = line.startsWith("\t") ? 1 : removableSpaces;
        if (index === 0) {
          firstLineDelta = removeCount;
        }
        totalDelta += removeCount;
        return line.slice(removeCount);
      })
      .join("\n");

    const nextSql = `${sql.slice(0, lineStart)}${nextBlock}${sql.slice(lineEnd)}`;
    commitSql(nextSql, Math.max(lineStart, start - firstLineDelta), Math.max(lineStart, end - totalDelta));
  }

  function handleSqlKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    const editor = event.currentTarget;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      restoreHistory(-1);
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
      event.preventDefault();
      restoreHistory(1);
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      if (!event.shiftKey && editor.selectionStart === editor.selectionEnd) {
        insertText("    ");
        return;
      }
      changeIndent(event.shiftKey);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      const lineStart = sql.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
      const indent = sql.slice(lineStart, start).match(/^[ \t]*/)?.[0] ?? "";
      const insertedText = `\n${indent}`;
      const nextSql = `${sql.slice(0, start)}${insertedText}${sql.slice(end)}`;
      commitSql(nextSql, start + insertedText.length);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setIsRunning(true);
    try {
      await onRun(sql);
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-label="Custom SQL" className="sql-modal" role="dialog">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Data Browser</p>
            <h2>Custom SQL</h2>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close SQL editor">
            <X size={18} />
          </button>
        </header>

        <form className="sql-layout" onSubmit={submit}>
          <main className="panel sql-editor-panel">
            <div className="sql-hint">
              <span>Table</span>
              <button className="secondary-button compact-button" onClick={() => insertText(tableName)} type="button">
                {tableName}
              </button>
            </div>
            <textarea
              className="sql-textarea"
              ref={editorRef}
              spellCheck={false}
              value={sql}
              onChange={(event) => commitSql(event.target.value)}
              onKeyDown={handleSqlKeyDown}
            />
            <div className="button-row">
              <button className="primary-button" disabled={isRunning || !sql.trim()} type="submit">
                <Play size={16} />
                {isRunning ? "Running" : "Run SQL"}
              </button>
              <button
                className="secondary-button"
                onClick={() => commitSql(defaultSql, defaultSql.length)}
                type="button"
              >
                <RotateCcw size={16} />
                Reset
              </button>
            </div>
          </main>

          <aside className="panel sql-helper-sidebar">
            <section>
              <div className="section-toggle static-section-title">
                <Table2 size={16} />
                <strong>Columns</strong>
              </div>
              <div className="sql-token-list">
                {columns.map((column) => (
                  <button
                    className="secondary-button compact-button sql-token"
                    key={column.name}
                    onClick={() => insertText(quoteSqlIdentifier(column.name))}
                    type="button"
                  >
                    {column.name}
                  </button>
                ))}
              </div>
            </section>

            <section>
              <div className="section-toggle static-section-title">
                <ListChecks size={16} />
                <strong>Functions</strong>
              </div>
              <div className="sql-token-list">
                {sqlFunctions.map((fn) => (
                  <button
                    className="secondary-button compact-button sql-token"
                    key={fn}
                    onClick={() => insertSqlFunction(fn)}
                    type="button"
                  >
                    {fn}
                  </button>
                ))}
              </div>
            </section>

            <section>
              <div className="section-toggle static-section-title">
                <Database size={16} />
                <strong>Snippets</strong>
              </div>
              <div className="sql-token-list">
                <button
                  className="secondary-button compact-button sql-token"
                  onClick={() => insertText(`SELECT COUNT(*) AS records\nFROM ${tableName}`)}
                  type="button"
                >
                  Count records
                </button>
                <button
                  className="secondary-button compact-button sql-token"
                  onClick={() => insertText(`GROUP BY `)}
                  type="button"
                >
                  GROUP BY
                </button>
                <button
                  className="secondary-button compact-button sql-token"
                  onClick={() => insertText(`ORDER BY `)}
                  type="button"
                >
                  ORDER BY
                </button>
              </div>
            </section>
          </aside>
        </form>
      </section>
    </div>
  );
}

function DrilldownModal({
  columns,
  initialHiddenColumns,
  initialSortRules,
  onClose,
  rows,
  title
}: {
  columns: DatasetPreview["columns"];
  initialHiddenColumns: Record<string, boolean>;
  initialSortRules: SortRule[];
  onClose: () => void;
  rows: Array<Record<string, DatasetCellValue>>;
  title: string;
}) {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Record<string, ColumnFilterConfig>>({});
  const [sortRules, setSortRules] = useState<SortRule[]>(initialSortRules);
  const [hiddenColumns, setHiddenColumns] = useState<Record<string, boolean>>(initialHiddenColumns);
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const visibleColumns = columns.filter((column) => !hiddenColumns[column.name]);
  const visibleColumnCount = visibleColumns.length;
  const valueOptions = useMemo(() => buildColumnValueOptions(rows, columns), [columns, rows]);

  const filteredRows = useMemo(() => {
    const searchValue = search.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesSearch =
        !searchValue ||
        columns.some((column) => valueToSearchText(row[column.name]).includes(searchValue));
      if (!matchesSearch) {
        return false;
      }
      return columns.every((column) => matchesFilter(row[column.name], filters[column.name]));
    });
  }, [columns, filters, rows, search]);

  const sortedRows = useMemo(() => sortRecords(filteredRows, sortRules), [filteredRows, sortRules]);
  const pageCount = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const visibleRows = sortedRows.slice((safePage - 1) * pageSize, safePage * pageSize);

  function updateFilter(column: DatasetPreview["columns"][number], value: string) {
    setFilters((current) => ({
      ...current,
      [column.name]: {
        operator: current[column.name]?.operator ?? defaultFilterOperator(column.type),
        value,
        values: current[column.name]?.values ?? []
      }
    }));
    setPage(1);
  }

  function updateFilterOperator(column: string, operator: FilterOperator) {
    setFilters((current) => ({
      ...current,
      [column]: {
        operator,
        value: current[column]?.value ?? "",
        values: current[column]?.values ?? []
      }
    }));
    setPage(1);
  }

  function updateFilterValues(column: string, values: string[]) {
    setFilters((current) => ({
      ...current,
      [column]: {
        operator: current[column]?.operator ?? "in",
        value: values[0] ?? "",
        values
      }
    }));
    setPage(1);
  }

  function addSortRule() {
    const nextColumn = columns.find((column) => !sortRules.some((rule) => rule.column === column.name));
    if (nextColumn) {
      setSortRules((current) => [...current, { column: nextColumn.name, direction: "asc" }]);
    }
  }

  function updateSortRule(index: number, patch: Partial<SortRule>) {
    setSortRules((current) =>
      current.map((rule, ruleIndex) => ruleIndex === index ? { ...rule, ...patch } : rule)
    );
    setPage(1);
  }

  function removeSortRule(index: number) {
    setSortRules((current) => current.filter((_, ruleIndex) => ruleIndex !== index));
    setPage(1);
  }

  function toggleColumnVisibility(column: string) {
    setHiddenColumns((current) => ({
      ...current,
      [column]: !current[column]
    }));
  }

  function showAllColumns() {
    setHiddenColumns({});
  }

  function hideAllColumns() {
    setHiddenColumns(Object.fromEntries(columns.map((column) => [column.name, true])));
  }

  function showOnlyColumns(predicate: (column: DatasetPreview["columns"][number]) => boolean) {
    setHiddenColumns(Object.fromEntries(columns.map((column) => [column.name, !predicate(column)])));
  }

  function jumpToPage(value: string) {
    const nextPage = Number(value);
    if (Number.isFinite(nextPage)) {
      setPage(Math.max(1, Math.min(pageCount, Math.trunc(nextPage))));
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-label="Drill down details" className="drilldown-modal" role="dialog">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Drill down</p>
            <h2>{title}</h2>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close drill down">
            <X size={18} />
          </button>
        </header>

        <div className="drilldown-layout">
          <main className="panel drilldown-table-panel">
            <div className="browser-summary">
              <span>Showing {visibleRows.length} of {sortedRows.length} detail records</span>
              <span>{rows.length} records in group</span>
            </div>
            {visibleColumnCount === 0 && <div className="empty-state">All detail columns are hidden</div>}
            {visibleColumnCount > 0 && <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {visibleColumns.map((column) => (
                      <th key={column.name}>
                        <button type="button" onClick={() => setSortRules([{ column: column.name, direction: "asc" }])}>
                          <span>{column.name}</span>
                          <em>{column.type}</em>
                          <strong>{sortLabel(column.name, sortRules)}</strong>
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {visibleColumns.map((column) => (
                        <td className={`cell-${cellKind(row[column.name])}`} key={column.name}>
                          {displayValue(row[column.name])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>}
            <div className="pagination">
              <button
                className="secondary-button"
                disabled={safePage === 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                type="button"
              >
                Previous
              </button>
              <span>
                Page
                <input
                  aria-label="Drill down page number"
                  className="page-input"
                  max={pageCount}
                  min={1}
                  onChange={(event) => jumpToPage(event.target.value)}
                  type="number"
                  value={safePage}
                />
                of {pageCount}
              </span>
              <button
                className="secondary-button"
                disabled={safePage === pageCount}
                onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                type="button"
              >
                Next
              </button>
            </div>
          </main>

          <aside className="panel drilldown-sidebar">
            <label>
              Search
              <div className="input-with-icon">
                <Search size={16} />
                <input
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setPage(1);
                  }}
                  placeholder="Search details"
                />
              </div>
            </label>

            <section className="columns-section">
              <div className="section-toggle static-section-title">
                <Table2 size={16} />
                <strong>Columns selection</strong>
                <span>{visibleColumnCount}/{columns.length}</span>
              </div>
              <div className="columns-selection-body">
                <div className="preset-row">
                  <button className="secondary-button compact-button" onClick={showAllColumns} type="button">
                    Show all
                  </button>
                  <button className="secondary-button compact-button" onClick={hideAllColumns} type="button">
                    Hide all
                  </button>
                  <button className="secondary-button compact-button" onClick={() => showOnlyColumns((column) => column.type === "number")} type="button">
                    Numeric only
                  </button>
                  <button className="secondary-button compact-button" onClick={() => showOnlyColumns((column) => column.type !== "number")} type="button">
                    Non-numeric
                  </button>
                </div>
                <div className="column-check-list">
                  {columns.map((column) => (
                    <label className="check-tile compact-check" key={column.name}>
                      <input
                        checked={!hiddenColumns[column.name]}
                        onChange={() => toggleColumnVisibility(column.name)}
                        type="checkbox"
                      />
                      <span>{column.name}</span>
                      <em>{column.type}</em>
                    </label>
                  ))}
                </div>
              </div>
            </section>

            <section className="sorting-section">
              <div className="section-toggle static-section-title">
                <ListChecks size={16} />
                <strong>Detail sorting</strong>
                <span>{sortRules.length}</span>
              </div>
              <div className="section-actions">
                <button className="secondary-button compact-button" onClick={addSortRule} type="button">
                  Add sort
                </button>
                <button className="secondary-button compact-button" onClick={() => setSortRules([])} type="button">
                  Clear
                </button>
              </div>
              <div className="sort-rule-list">
                {sortRules.map((rule, index) => (
                  <div className="sort-rule-row" key={`${rule.column}-${index}`}>
                    <strong>{index + 1}</strong>
                    <label>
                      Column
                      <select value={rule.column} onChange={(event) => updateSortRule(index, { column: event.target.value })}>
                        {columns.map((column) => (
                          <option key={column.name} value={column.name}>{column.name}</option>
                        ))}
                      </select>
                    </label>
                    <div className="field-group">
                      <span>Direction</span>
                      <SortDirectionToggle
                        value={rule.direction}
                        onChange={(direction) => updateSortRule(index, { direction })}
                      />
                    </div>
                    <div className="sort-rule-actions">
                      <button className="secondary-button compact-button" onClick={() => removeSortRule(index)} type="button">
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
                {sortRules.length === 0 && <div className="empty-state compact-empty">No sort rules</div>}
              </div>
            </section>

            <section className="filter-section">
              <div className="section-toggle static-section-title">
                <Filter size={16} />
                <strong>Detail filters</strong>
              </div>
              <div className="filter-grid">
                {columns.map((column) => {
                  const config = filters[column.name] ?? { operator: defaultFilterOperator(column.type), value: "" };
                  const operators = filterOperatorsForColumn(column.type);
                  const options = valueOptions[column.name] ?? [];
                  const useValueList = options.length > 0 && ["equals", "in"].includes(config.operator);
                  return (
                    <div className="filter-row" key={column.name}>
                      <strong>{column.name}</strong>
                      <span>{column.type}</span>
                      <label>
                        Operator
                        <select value={config.operator} onChange={(event) => updateFilterOperator(column.name, event.target.value as FilterOperator)}>
                          {operators.map((operator) => (
                            <option key={operator} value={operator}>{filterOperatorLabels[operator]}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Value
                        {useValueList && config.operator === "in" ? (
                          <select
                            multiple
                            value={config.values ?? []}
                            onChange={(event) => updateFilterValues(
                              column.name,
                              Array.from(event.currentTarget.selectedOptions).map((option) => option.value)
                            )}
                          >
                            {options.map((value) => <option key={value} value={value}>{value}</option>)}
                          </select>
                        ) : useValueList ? (
                          <select value={config.value} onChange={(event) => updateFilter(column, event.target.value)}>
                            <option value="">Any value</option>
                            {options.map((value) => <option key={value} value={value}>{value}</option>)}
                          </select>
                        ) : (
                          <input
                            disabled={operatorDoesNotNeedValue(config.operator)}
                            value={config.value}
                            onChange={(event) => updateFilter(column, event.target.value)}
                            placeholder={`Filter ${column.type}`}
                          />
                        )}
                      </label>
                    </div>
                  );
                })}
              </div>
            </section>
          </aside>
        </div>
      </section>
    </div>
  );
}

function defaultFilterOperator(type: DatasetPreview["columns"][number]["type"] = "text"): FilterOperator {
  return type === "number" || type === "date" || type === "boolean" ? "equals" : "contains";
}

function filterOperatorsForColumn(type: DatasetPreview["columns"][number]["type"], role = ""): FilterOperator[] {
  if (type === "number") {
    return ["equals", "not_equals", "gt", "gte", "lt", "lte", "between", "empty", "not_empty"];
  }
  if (type === "date") {
    return ["equals", "not_equals", "gt", "gte", "lt", "lte", "empty", "not_empty"];
  }
  if (type === "boolean") {
    return ["equals", "not_equals", "in", "empty", "not_empty"];
  }
  if (["feature_categorical", "feature_ordinal", "target"].includes(role)) {
    return ["equals", "in", "not_equals", "contains", "regex", "empty", "not_empty"];
  }
  return ["contains", "equals", "in", "not_equals", "regex", "starts_with", "ends_with", "empty", "not_empty"];
}

function operatorDoesNotNeedValue(operator: FilterOperator) {
  return operator === "empty" || operator === "not_empty";
}

function matchesFilter(value: unknown, config: ColumnFilterConfig | undefined) {
  if (!config) {
    return true;
  }
  const filterValue = config.value.trim();
  const textValue = displayValue(value);
  const normalizedText = textValue.toLowerCase();
  const normalizedFilter = filterValue.toLowerCase();
  const isEmpty = value === null || value === undefined || value === "";

  if (config.operator === "empty") {
    return isEmpty;
  }
  if (config.operator === "not_empty") {
    return !isEmpty;
  }
  if (config.operator === "between") {
    const bounds = config.values?.length === 2
      ? config.values
      : filterValue.split(",").map((item) => item.trim()).filter(Boolean);
    if (bounds.length !== 2) return true;
    const leftNumber = comparableNumber(value);
    const lower = Number(bounds[0]);
    const upper = Number(bounds[1]);
    if (!Number.isFinite(leftNumber) || !Number.isFinite(lower) || !Number.isFinite(upper)) return false;
    return leftNumber >= lower && (config.upperInclusive ? leftNumber <= upper : leftNumber < upper);
  }
  if (!filterValue) {
    return true;
  }
  if (config.operator === "contains") {
    return normalizedText.includes(normalizedFilter);
  }
  if (config.operator === "equals") {
    return normalizedText === normalizedFilter;
  }
  if (config.operator === "not_equals") {
    return normalizedText !== normalizedFilter;
  }
  if (config.operator === "in") {
    const values = config.values?.length ? config.values : filterValue.split(",").map((item) => item.trim()).filter(Boolean);
    return values.map((item) => item.toLowerCase()).includes(normalizedText);
  }
  if (config.operator === "starts_with") {
    return normalizedText.startsWith(normalizedFilter);
  }
  if (config.operator === "ends_with") {
    return normalizedText.endsWith(normalizedFilter);
  }
  if (config.operator === "regex") {
    try {
      return new RegExp(filterValue, "i").test(textValue);
    } catch {
      return false;
    }
  }

  const leftNumber = comparableNumber(value);
  const rightNumber = Number(filterValue);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    if (config.operator === "gt") {
      return leftNumber > rightNumber;
    }
    if (config.operator === "gte") {
      return leftNumber >= rightNumber;
    }
    if (config.operator === "lt") {
      return leftNumber < rightNumber;
    }
    if (config.operator === "lte") {
      return leftNumber <= rightNumber;
    }
  }

  const comparison = compareValues(value, filterValue);
  if (config.operator === "gt") {
    return comparison > 0;
  }
  if (config.operator === "gte") {
    return comparison >= 0;
  }
  if (config.operator === "lt") {
    return comparison < 0;
  }
  if (config.operator === "lte") {
    return comparison <= 0;
  }
  return true;
}

function comparableNumber(value: unknown) {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string") {
    const parsedDate = Date.parse(value);
    if (Number.isFinite(parsedDate)) {
      return parsedDate;
    }
    const parsedNumber = Number(value);
    if (Number.isFinite(parsedNumber)) {
      return parsedNumber;
    }
  }
  return Number.NaN;
}

function sortLabel(column: string, sortRules: SortRule[]) {
  const index = sortRules.findIndex((rule) => rule.column === column);
  if (index === -1) {
    return "";
  }
  return `${index + 1} ${sortRules[index].direction}`;
}

function sortRecords<T extends Record<string, unknown>>(records: T[], sortRules: SortRule[]) {
  if (sortRules.length === 0) {
    return records;
  }
  return [...records].sort((left, right) => {
    for (const rule of sortRules) {
      const comparison = compareValues(left[rule.column], right[rule.column]);
      if (comparison !== 0) {
        return rule.direction === "asc" ? comparison : -comparison;
      }
    }
    return 0;
  });
}

function quoteSqlIdentifier(identifier: string) {
  return `"${identifier.replaceAll('"', '""')}"`;
}

function buildDataViewDefinition({
  search,
  filters,
  aggregationFilters,
  sortRules,
  grouping,
  visibleColumns,
  customSql,
  isSqlResult
}: {
  search: string;
  filters: Record<string, ColumnFilterConfig>;
  aggregationFilters: Record<string, ColumnFilterConfig>;
  sortRules: SortRule[];
  grouping: Record<string, GroupingColumnConfig>;
  visibleColumns: string[];
  customSql: string;
  isSqlResult: boolean;
}) {
  if (isSqlResult && customSql.trim()) {
    return {
      kind: "sql",
      sql: customSql.trim()
    };
  }

  return {
    kind: "browser",
    search,
    filters: removeEmptyFilterConfigs(filters),
    aggregation_filters: removeEmptyFilterConfigs(aggregationFilters),
    sort_rules: sortRules,
    grouping: Object.fromEntries(
      Object.entries(grouping).filter(([, config]) => config.role !== "none")
    ),
    visible_columns: visibleColumns
  };
}

function removeEmptyFilterConfigs(filters: Record<string, ColumnFilterConfig>) {
  return Object.fromEntries(
    Object.entries(filters).filter(([, config]) => {
      if (operatorDoesNotNeedValue(config.operator)) {
        return true;
      }
      if (config.operator === "in") {
        return (config.values ?? []).length > 0;
      }
      return config.value.trim() !== "";
    })
  );
}

function orderAggregatedColumns(
  columns: AggregatedColumn[],
  grouping: Record<string, GroupingColumnConfig>,
  sortRules: SortRule[]
) {
  const recordsColumn = columns.find((column) => column.name === "records");
  const groupColumns = columns.filter((column) => grouping[column.sourceColumn ?? column.name]?.role === "group");
  const aggregateColumns = columns.filter((column) =>
    column.name !== "records" && grouping[column.sourceColumn ?? column.name]?.role !== "group"
  );

  return [
    ...orderColumnsBySortRules(groupColumns, sortRules),
    ...(recordsColumn ? [recordsColumn] : []),
    ...orderColumnsBySortRules(aggregateColumns, sortRules)
  ];
}

function orderColumnsBySortRules(columns: AggregatedColumn[], sortRules: SortRule[]) {
  const sortIndex = new Map(sortRules.map((rule, index) => [rule.column, index]));
  return [...columns].sort((left, right) => {
    const leftIndex = sortIndex.get(left.name);
    const rightIndex = sortIndex.get(right.name);
    if (leftIndex === undefined && rightIndex === undefined) {
      return 0;
    }
    if (leftIndex === undefined) {
      return 1;
    }
    if (rightIndex === undefined) {
      return -1;
    }
    return leftIndex - rightIndex;
  });
}

function buildColumnValueOptions(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"]
) {
  const options: Record<string, string[]> = {};
  for (const column of columns) {
    if (!["text", "boolean", "date"].includes(column.type)) {
      continue;
    }
    const values = new Set<string>();
    for (const row of rows) {
      const value = row[column.name];
      if (value === null || value === undefined || value === "") {
        continue;
      }
      values.add(displayValue(value));
      if (values.size > 150) {
        break;
      }
    }
    if (values.size > 0 && values.size <= 150) {
      options[column.name] = [...values].sort((left, right) => left.localeCompare(right, undefined, {
        numeric: true,
        sensitivity: "base"
      }));
    }
  }
  return options;
}

function buildAggregationResult(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"],
  grouping: Record<string, GroupingColumnConfig>
): {
  isActive: boolean;
  columns: AggregatedColumn[];
  records: Array<Record<string, DatasetCellValue>>;
} {
  const groupColumns = columns.filter((column) => grouping[column.name]?.role === "group");
  const aggregateColumns = columns.filter((column) => grouping[column.name]?.role === "aggregate");
  const isActive = groupColumns.length > 0 || aggregateColumns.length > 0;

  if (!isActive) {
    return { isActive: false, columns, records: rows };
  }

  const resultColumns: AggregatedColumn[] = [
    ...groupColumns.map((column) => ({ ...column, sourceColumn: column.name })),
    { name: "records", type: "number" },
    ...aggregateColumns.map((column) => ({
      name: `${aggregationFunctionLabels[grouping[column.name].aggregate]} ${column.name}`,
      type: aggregateResultType(grouping[column.name].aggregate, column.type),
      sourceColumn: column.name
    }))
  ];

  const groups = new Map<string, Array<Record<string, DatasetCellValue>>>();
  for (const row of rows) {
    const key = groupColumns.length === 0
      ? "__all__"
      : JSON.stringify(groupColumns.map((column) => displayValue(row[column.name])));
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }

  const records = Array.from(groups.values()).map((groupRows) => {
    const record: Record<string, DatasetCellValue> = {};
    for (const column of groupColumns) {
      record[column.name] = groupRows[0]?.[column.name] ?? null;
    }
    record.records = groupRows.length;
    for (const column of aggregateColumns) {
      const aggregate = grouping[column.name].aggregate;
      record[`${aggregationFunctionLabels[aggregate]} ${column.name}`] = aggregateValues(
        groupRows.map((row) => row[column.name]),
        aggregate
      );
    }
    return record;
  });

  return { isActive, columns: resultColumns, records };
}

function aggregationFunctionsForColumn(
  column: DatasetPreview["columns"][number],
  rolesMetadata: DataRolesMetadata
): AggregationFunction[] {
  const role = columnRoleForColumn(column, rolesMetadata);
  const numericColumn = column.type === "number" || role === "feature_continuous" || role === "sample_weight";
  const orderedColumn = column.type === "date" || role === "timestamp" || role === "period_id" || role === "feature_ordinal";

  if (numericColumn) {
    return ["count", "count_non_empty", "unique_count", "sum", "average", "min", "max", "median"];
  }
  if (orderedColumn) {
    return ["count", "count_non_empty", "unique_count", "min", "max", "first", "last"];
  }
  if (role === "identifier") {
    return ["count", "count_non_empty", "unique_count", "first", "last"];
  }
  return ["count", "count_non_empty", "unique_count", "mode", "first", "last"];
}

function defaultAggregationFunction(
  column: DatasetPreview["columns"][number],
  rolesMetadata: DataRolesMetadata
): AggregationFunction {
  const role = columnRoleForColumn(column, rolesMetadata);
  if (role === "sample_weight") {
    return "sum";
  }
  if (column.type === "number" || role === "feature_continuous") {
    return "average";
  }
  if (role === "identifier") {
    return "unique_count";
  }
  return "count_non_empty";
}

function columnRoleForColumn(
  column: DatasetPreview["columns"][number],
  rolesMetadata: DataRolesMetadata
) {
  return rolesMetadata.column_roles[column.name] ?? defaultColumnRole(column.type);
}

function columnRoleLabel(role: string) {
  return columnRoleOptions.find((option) => option.value === role)?.label ?? role;
}

function aggregateResultType(
  aggregate: AggregationFunction,
  fallbackType: DatasetPreview["columns"][number]["type"]
) {
  if (["count", "count_non_empty", "unique_count", "sum", "average", "median"].includes(aggregate)) {
    return "number";
  }
  return fallbackType;
}

function aggregateValues(values: DatasetCellValue[], aggregate: AggregationFunction): DatasetCellValue {
  const concreteValues = values.filter((value) => value !== null && value !== undefined && value !== "");
  const numericValues = concreteValues
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => left - right);

  if (aggregate === "count") {
    return values.length;
  }
  if (aggregate === "count_non_empty") {
    return concreteValues.length;
  }
  if (aggregate === "unique_count") {
    return new Set(concreteValues.map(displayValue)).size;
  }
  if (aggregate === "sum") {
    return numericValues.reduce((total, value) => total + value, 0);
  }
  if (aggregate === "average") {
    return numericValues.length === 0 ? null : roundNumber(numericValues.reduce((total, value) => total + value, 0) / numericValues.length);
  }
  if (aggregate === "min") {
    return minComparableValue(concreteValues);
  }
  if (aggregate === "max") {
    return maxComparableValue(concreteValues);
  }
  if (aggregate === "median") {
    if (numericValues.length === 0) {
      return null;
    }
    const middle = Math.floor(numericValues.length / 2);
    return numericValues.length % 2 === 0
      ? roundNumber((numericValues[middle - 1] + numericValues[middle]) / 2)
      : numericValues[middle];
  }
  if (aggregate === "mode") {
    return mostCommonValue(concreteValues);
  }
  if (aggregate === "first") {
    return concreteValues[0] ?? null;
  }
  return concreteValues[concreteValues.length - 1] ?? null;
}

function firstNonEmptyValue(values: DatasetCellValue[]) {
  return values.find((value) => value !== null && value !== undefined && value !== "") ?? null;
}

function minComparableValue(values: DatasetCellValue[]) {
  if (values.length === 0) {
    return null;
  }
  return [...values].sort(compareValues)[0] ?? null;
}

function maxComparableValue(values: DatasetCellValue[]) {
  if (values.length === 0) {
    return null;
  }
  return [...values].sort(compareValues).at(-1) ?? null;
}

function mostCommonValue(values: DatasetCellValue[]) {
  const counts = new Map<string, { value: DatasetCellValue; count: number }>();
  for (const value of values) {
    const key = displayValue(value);
    const current = counts.get(key);
    counts.set(key, { value, count: (current?.count ?? 0) + 1 });
  }
  return [...counts.values()].sort((left, right) => right.count - left.count)[0]?.value ?? null;
}

function roundNumber(value: number) {
  return Number(value.toFixed(6));
}

function inferTargetColumn(columns: DatasetPreview["columns"], rolesMetadata: DataRolesMetadata) {
  const names = new Set(columns.map((column) => column.name));
  if (rolesMetadata.target_column && names.has(rolesMetadata.target_column)) {
    return rolesMetadata.target_column;
  }
  const roleTarget = columns.find((column) => rolesMetadata.column_roles[column.name] === "target");
  if (roleTarget) {
    return roleTarget.name;
  }
  const commonTargetNames = new Set(["target", "label", "class", "outcome", "churn", "y"]);
  return columns.find((column) => commonTargetNames.has(column.name.toLowerCase()))?.name ?? "";
}

function inferTargetType(
  column: DatasetPreview["columns"][number] | null,
  rows: Array<Record<string, DatasetCellValue>>,
  rolesMetadata: DataRolesMetadata
): EffectiveTargetType {
  if (!column) {
    return "categorical";
  }
  const role = columnRoleForColumn(column, rolesMetadata);
  if (["feature_categorical", "feature_ordinal", "boolean", "text"].includes(role)) {
    return "categorical";
  }
  if (role === "feature_continuous") {
    return "continuous";
  }
  if (column.type === "boolean" || column.type === "text") {
    return "categorical";
  }
  if (column.type !== "number") {
    return "categorical";
  }

  const present = rows.map((row) => normalizeCellValue(row[column.name])).filter(isPresentCell);
  const uniqueValues = [...new Set(present.map(displayValue))];
  if (uniqueValues.length <= 2) {
    return "categorical";
  }
  const lowCardinalityLimit = Math.min(20, Math.max(5, Math.floor(present.length * 0.05)));
  if (uniqueValues.length <= lowCardinalityLimit) {
    return "categorical";
  }
  return "continuous";
}

function buildColumnProfile(
  column: DatasetPreview["columns"][number],
  rows: Array<Record<string, DatasetCellValue>>,
  rolesMetadata: DataRolesMetadata,
  includeGraphics: boolean
): ColumnProfile {
  const values = rows.map((row) => normalizeCellValue(row[column.name]));
  const present = values.filter(isPresentCell);
  const numericValues = present
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => left - right);
  const topValues = countTopValues(present, rows.length);
  const role = columnRoleForColumn(column, rolesMetadata);
  const mean = numericValues.length === present.length && numericValues.length > 0
    ? numericValues.reduce((total, value) => total + value, 0) / numericValues.length
    : null;
  const notes: string[] = [];
  const unique = new Set(present.map(displayValue)).size;
  const missingRate = rows.length === 0 ? 0 : (rows.length - present.length) / rows.length;
  const uniqueRate = present.length === 0 ? 0 : unique / present.length;

  if (missingRate >= 0.3) {
    notes.push("High missingness");
  }
  if (uniqueRate >= 0.95 && !["identifier", "timestamp", "period_id"].includes(role)) {
    notes.push("Near-unique values");
  }
  if (unique <= 1 && present.length > 0) {
    notes.push("Constant column");
  }
  if (role === "ignored") {
    notes.push("Excluded by role");
  }
  if (["feature_categorical", "text"].includes(role) && unique > 50) {
    notes.push("High-cardinality category");
  }

  return {
    name: column.name,
    type: column.type,
    role,
    count: present.length,
    missing: rows.length - present.length,
    missingRate,
    unique,
    uniqueRate,
    mean: mean === null ? null : roundNumber(mean),
    median: mean === null ? null : roundNumber(medianNumber(numericValues)),
    minimum: mean === null ? minComparableValue(present) : numericValues[0] ?? null,
    maximum: mean === null ? maxComparableValue(present) : numericValues.at(-1) ?? null,
    stdDev: mean === null ? null : roundNumber(standardDeviation(numericValues)),
    mode: topValues[0]?.value ?? null,
    topValues,
    histogram: mean === null || !includeGraphics ? [] : buildHistogramBins(numericValues),
    examples: present.slice(0, 3),
    notes
  };
}

function usesDiscreteDistribution(profile: ColumnProfile) {
  return profile.mean !== null && profile.unique > 0 && profile.unique <= 12;
}

function buildTargetRelations(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"],
  rolesMetadata: DataRolesMetadata,
  comparisonColumn: string,
  comparisonType: EffectiveTargetType,
  includeGraphics: boolean
): TargetRelationProfile[] {
  const comparison = columns.find((column) => column.name === comparisonColumn);
  if (!comparison) {
    return [];
  }

  const comparisonIsNumeric = comparisonType === "continuous";
  const relations = columns
    .filter((column) => column.name !== comparison.name)
    .filter((column) => !["ignored", "identifier"].includes(columnRoleForColumn(column, rolesMetadata)))
    .map((feature) => {
      const role = columnRoleForColumn(feature, rolesMetadata);
      const featureIsNumeric = isNumericMeasureColumn(feature, rolesMetadata, rows, false);
      const relationRows = rows.filter((row) =>
        isPresentCell(normalizeCellValue(row[comparison.name])) &&
        isPresentCell(normalizeCellValue(row[feature.name]))
      );
      if (relationRows.length < 3) {
        return null;
      }

      if (comparisonIsNumeric && featureIsNumeric) {
        const pairs = relationRows
          .map((row) => [Number(row[feature.name]), Number(row[comparison.name])] as const)
          .filter(([featureValue, targetValue]) => Number.isFinite(featureValue) && Number.isFinite(targetValue));
        const correlation = pearsonCorrelation(pairs);
        if (correlation === null) {
          return null;
        }
        const numericStats = numericRelationStats(pairs);
        const scatterPlot = includeGraphics ? buildScatterPlot(pairs, feature.name, comparison.name, numericStats) : null;
        return {
          feature: feature.name,
          role,
          type: feature.type,
          kind: "numeric correlation",
          score: Math.min(1, Math.abs(correlation)),
          signal: `r ${formatSignedNumber(correlation)}`,
          detail: `${feature.name} moves ${correlation >= 0 ? "with" : "against"} ${comparison.name} in the loaded sample.`,
          comparisonColumn: comparison.name,
          groupStats: [],
          densityPlot: null,
          numericStats,
          scatterPlot,
          categoricalStats: null
        };
      }

      if (comparisonIsNumeric && !featureIsNumeric) {
        return groupedMeanRelation({
          rows: relationRows,
          groupColumn: feature.name,
          numericColumn: comparison.name,
          feature,
          role,
          kind: "comparison mean by feature",
          comparisonColumn: comparison.name,
          includeGraphics
        });
      }

      if (!comparisonIsNumeric && featureIsNumeric) {
        return groupedMeanRelation({
          rows: relationRows,
          groupColumn: comparison.name,
          numericColumn: feature.name,
          feature,
          role,
          kind: "feature stats by comparison",
          comparisonColumn: comparison.name,
          includeGraphics
        });
      }

      return categoricalRelation(relationRows, comparison.name, feature, role, includeGraphics);
    })
    .filter((relation): relation is TargetRelationProfile => relation !== null);

  return relations;
}

function groupedMeanRelation({
  rows,
  groupColumn,
  numericColumn,
  feature,
  role,
  kind,
  comparisonColumn,
  includeGraphics
}: {
  rows: Array<Record<string, DatasetCellValue>>;
  groupColumn: string;
  numericColumn: string;
  feature: DatasetPreview["columns"][number];
  role: string;
  kind: string;
  comparisonColumn: string;
  includeGraphics: boolean;
}): TargetRelationProfile | null {
  const groups = new Map<string, number[]>();
  for (const row of rows) {
    const numericValue = Number(row[numericColumn]);
    if (!Number.isFinite(numericValue)) {
      continue;
    }
    const group = displayValue(row[groupColumn]);
    groups.set(group, [...(groups.get(group) ?? []), numericValue]);
  }

  const minimumGroupSize = Math.max(3, Math.floor(rows.length * 0.03));
  const summaries = [...groups.entries()]
    .map(([group, values], index) => {
      const sortedValues = [...values].sort((left, right) => left - right);
      return {
        group,
        count: values.length,
        minimum: sortedValues[0] ?? 0,
        maximum: sortedValues.at(-1) ?? 0,
        median: medianNumber(sortedValues),
        mean: values.reduce((total, value) => total + value, 0) / values.length,
        stdDev: standardDeviation(sortedValues),
        color: comparisonColor(index)
      };
    })
    .filter((summary) => summary.count >= minimumGroupSize);
  if (summaries.length < 2) {
    return null;
  }

  const allValues = [...groups.values()].flat();
  const spread = standardDeviation(allValues);
  const ordered = summaries.sort((left, right) => right.mean - left.mean);
  const range = ordered[0].mean - ordered.at(-1)!.mean;
  const score = spread === 0 ? 0 : Math.min(1, Math.abs(range) / (spread * 4));
  const groupStats = ordered.map((summary) => ({
    ...summary,
    minimum: roundNumber(summary.minimum),
    maximum: roundNumber(summary.maximum),
    median: roundNumber(summary.median),
    mean: roundNumber(summary.mean),
    stdDev: roundNumber(summary.stdDev)
  }));
  return {
    feature: feature.name,
    role,
    type: feature.type,
    kind,
    score,
    signal: `effect ${formatNumber(score)}`,
    detail: `${ordered[0].group} has the highest mean (${formatNumber(ordered[0].mean)}), ${ordered.at(-1)!.group} the lowest (${formatNumber(ordered.at(-1)!.mean)}).`,
    comparisonColumn,
    groupStats,
    densityPlot: includeGraphics ? buildDensityPlot(groupStats, groups) : null,
    numericStats: null,
    scatterPlot: null,
    categoricalStats: null
  };
}

function categoricalRelation(
  rows: Array<Record<string, DatasetCellValue>>,
  targetColumn: string,
  feature: DatasetPreview["columns"][number],
  role: string,
  includeGraphics: boolean
): TargetRelationProfile | null {
  const targetValues = sortCategoryValues(uniqueDisplayValues(rows, targetColumn));
  const rawFeatureValues = uniqueDisplayValues(rows, feature.name);
  const featureValues = role === "feature_ordinal"
    ? orderOrdinalValues(rawFeatureValues)
    : rawFeatureValues;
  if (targetValues.length < 2 || featureValues.length < 2 || featureValues.length > 50) {
    return null;
  }

  const rowTotals = new Map<string, number>();
  const columnTotals = new Map<string, number>();
  const cells = new Map<string, number>();
  for (const row of rows) {
    const targetValue = displayValue(row[targetColumn]);
    const featureValue = displayValue(row[feature.name]);
    rowTotals.set(targetValue, (rowTotals.get(targetValue) ?? 0) + 1);
    columnTotals.set(featureValue, (columnTotals.get(featureValue) ?? 0) + 1);
    cells.set(`${targetValue}\u0000${featureValue}`, (cells.get(`${targetValue}\u0000${featureValue}`) ?? 0) + 1);
  }

  let chiSquare = 0;
  let sparseCells = 0;
  let strongest = { targetValue: "", featureValue: "", lift: 0, residual: 0 };
  const tableRows = featureValues.map((featureValue) => {
    const rowCount = columnTotals.get(featureValue) ?? 0;
    const tableCells = targetValues.map((targetValue) => {
      const observed = cells.get(`${targetValue}\u0000${featureValue}`) ?? 0;
      const expected = ((rowTotals.get(targetValue) ?? 0) * rowCount) / rows.length;
      if (expected < 5) {
        sparseCells += 1;
      }
      const residual = expected > 0 ? (observed - expected) / Math.sqrt(expected) : 0;
      const lift = expected > 0 ? observed / expected : 0;
      if (!strongest.featureValue || Math.abs(residual) > Math.abs(strongest.residual)) {
        strongest = { targetValue, featureValue, lift, residual };
      }
      if (expected > 0) {
        chiSquare += ((observed - expected) ** 2) / expected;
      }
      return {
        comparisonValue: targetValue,
        count: observed,
        rowShare: rowCount === 0 ? 0 : observed / rowCount,
        lift,
        residual
      };
    });
    return { featureValue, count: rowCount, cells: tableCells };
  });

  const ordinalTrend = role === "feature_ordinal" && targetValues.length === 2
    ? buildOrdinalTrend(rows, feature.name, targetColumn, featureValues, targetValues.at(-1)!)
    : null;

  const degreesFreedom = (targetValues.length - 1) * (featureValues.length - 1);
  const cellCount = targetValues.length * featureValues.length;

  const denominator = rows.length * Math.max(1, Math.min(targetValues.length - 1, featureValues.length - 1));
  const cramersV = denominator === 0 ? 0 : Math.sqrt(chiSquare / denominator);
  return {
    feature: feature.name,
    role,
    type: feature.type,
    kind: "categorical association",
    score: Math.min(1, cramersV),
    signal: `V ${formatNumber(cramersV)}`,
    detail: `${feature.name}=${strongest.featureValue} has the strongest cell deviation for ${targetColumn}=${strongest.targetValue} (lift ${formatNumber(strongest.lift)}, residual ${formatSignedNumber(strongest.residual)}).`,
    comparisonColumn: targetColumn,
    groupStats: [],
    densityPlot: null,
    numericStats: null,
    scatterPlot: null,
    categoricalStats: {
      comparisonValues: targetValues,
      rows: tableRows,
      chiSquare: roundNumber(chiSquare),
      degreesFreedom,
      cramersV: roundNumber(cramersV),
      sparseCellShare: cellCount === 0 ? 0 : sparseCells / cellCount,
      ordinalTrend,
      graphicSummaries: includeGraphics
    }
  };
}

function buildSegmentProfile(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"],
  rolesMetadata: DataRolesMetadata,
  targetColumn: string,
  targetType: EffectiveTargetType,
  maxSegmentFeatures: number,
  includeGraphics: boolean
): SegmentProfile | null {
  const target = columns.find((column) => column.name === targetColumn);
  if (!target) {
    return null;
  }

  const candidates = columns
    .filter((column) => column.name !== targetColumn)
    .filter((column) => {
      const role = columnRoleForColumn(column, rolesMetadata);
      const uniqueCount = uniqueDisplayValues(rows, column.name).length;
      return !["ignored", "identifier"].includes(role) && uniqueCount >= 2 && uniqueCount <= 12;
    })
    .slice(0, maxSegmentFeatures);
  if (candidates.length < 2) {
    return null;
  }

  const validRows = rows.filter((row) => {
    const targetValue = normalizeCellValue(row[targetColumn]);
    return isPresentCell(targetValue) && (targetType !== "continuous" || Number.isFinite(Number(targetValue)));
  });
  if (validRows.length === 0) {
    return null;
  }
  const minimumGroupSize = Math.max(5, Math.floor(validRows.length * 0.03));

  const featurePairs: Array<typeof candidates> = [];
  for (let left = 0; left < candidates.length - 1; left += 1) {
    for (let right = left + 1; right < candidates.length; right += 1) {
      featurePairs.push([candidates[left], candidates[right]]);
    }
  }

  const results: SegmentResult[] = [];
  let segmentsEvaluated = 0;
  const numericTargetValues = targetType === "continuous"
    ? validRows.map((row) => Number(row[targetColumn])).filter(Number.isFinite)
    : [];
  const numericBaseline = numericTargetValues.length > 0
    ? numericTargetValues.reduce((total, value) => total + value, 0) / numericTargetValues.length
    : 0;
  const numericTargetSum = numericTargetValues.reduce((total, value) => total + value, 0);
  const numericTargetSumSquares = numericTargetValues.reduce((total, value) => total + value ** 2, 0);
  const categoryCounts = new Map<string, number>();
  if (targetType === "categorical") {
    for (const row of validRows) {
      const label = displayValue(row[targetColumn]);
      categoryCounts.set(label, (categoryCounts.get(label) ?? 0) + 1);
    }
  }
  const orderedTargetValues = [...categoryCounts.entries()]
    .sort((left, right) => left[1] - right[1] || left[0].localeCompare(right[0]))
    .map(([value]) => value);
  const targetValuesToScan = orderedTargetValues.length === 2 ? orderedTargetValues.slice(0, 1) : orderedTargetValues;

  for (const pair of featurePairs) {
    const groups = new Map<string, { label: string; rows: Array<Record<string, DatasetCellValue>> }>();
    for (const row of validRows) {
      const values = pair.map((column) => displayValue(row[column.name]));
      if (values.some((value) => value === "null")) {
        continue;
      }
      const key = values.join("\u001f");
      const group = groups.get(key) ?? {
        label: pair.map((column, index) => `${column.name}=${values[index]}`).join(" / "),
        rows: []
      };
      group.rows.push(row);
      groups.set(key, group);
    }

    for (const group of groups.values()) {
      if (group.rows.length < minimumGroupSize || group.rows.length >= validRows.length) {
        continue;
      }
      segmentsEvaluated += 1;
      const support = group.rows.length / validRows.length;
      if (targetType === "continuous") {
        const values = group.rows.map((row) => Number(row[targetColumn])).filter(Number.isFinite);
        const restCount = numericTargetValues.length - values.length;
        if (values.length < 2 || restCount < 2) {
          continue;
        }
        const segmentSum = values.reduce((total, value) => total + value, 0);
        const segmentSumSquares = values.reduce((total, value) => total + value ** 2, 0);
        const restSum = numericTargetSum - segmentSum;
        const restSumSquares = numericTargetSumSquares - segmentSumSquares;
        const segmentMean = segmentSum / values.length;
        const restMean = restSum / restCount;
        const segmentDeviation = sampleDeviationFromMoments(values.length, segmentSum, segmentSumSquares);
        const restDeviation = sampleDeviationFromMoments(restCount, restSum, restSumSquares);
        const pooledVariance = (((values.length - 1) * segmentDeviation ** 2) + ((restCount - 1) * restDeviation ** 2))
          / (values.length + restCount - 2);
        const pooledDeviation = Math.sqrt(Math.max(0, pooledVariance));
        const effectSize = pooledDeviation === 0 ? 0 : (segmentMean - restMean) / pooledDeviation;
        const standardError = segmentDeviation / Math.sqrt(values.length);
        results.push({
          columns: pair.map((column) => column.name),
          segment: group.label,
          count: values.length,
          support,
          targetValue: `mean ${targetColumn}`,
          baseline: numericBaseline,
          segmentValue: segmentMean,
          difference: segmentMean - numericBaseline,
          relativeLift: null,
          confidenceInterval: [segmentMean - 1.96 * standardError, segmentMean + 1.96 * standardError],
          effectSize,
          score: support * effectSize,
          format: "number"
        });
        continue;
      }

      for (const targetValue of targetValuesToScan) {
        const targetCount = group.rows.filter((row) => displayValue(row[targetColumn]) === targetValue).length;
        const segmentRate = targetCount / group.rows.length;
        const baseline = (categoryCounts.get(targetValue) ?? 0) / validRows.length;
        const difference = segmentRate - baseline;
        results.push({
          columns: pair.map((column) => column.name),
          segment: group.label,
          count: group.rows.length,
          support,
          targetValue: `${targetColumn}=${targetValue}`,
          baseline,
          segmentValue: segmentRate,
          difference,
          relativeLift: baseline === 0 ? null : segmentRate / baseline,
          confidenceInterval: wilsonInterval(targetCount, group.rows.length),
          effectSize: null,
          score: support * difference,
          format: "percent"
        });
      }
    }
  }

  return {
    targetColumn,
    targetType,
    candidateFeatures: candidates.map((column) => column.name),
    pairsScanned: featurePairs.length,
    segmentsEvaluated,
    minimumSegmentSize: minimumGroupSize,
    graphicSummaries: includeGraphics,
    results: results.sort((left, right) => Math.abs(right.score) - Math.abs(left.score)).slice(0, 12)
  };
}

function wilsonInterval(successes: number, trials: number): [number, number] {
  if (trials === 0) {
    return [0, 0];
  }
  const z = 1.96;
  const proportion = successes / trials;
  const denominator = 1 + (z ** 2) / trials;
  const center = (proportion + (z ** 2) / (2 * trials)) / denominator;
  const margin = (z / denominator) * Math.sqrt((proportion * (1 - proportion) / trials) + (z ** 2) / (4 * trials ** 2));
  return [Math.max(0, center - margin), Math.min(1, center + margin)];
}

function sampleDeviationFromMoments(count: number, sum: number, sumSquares: number) {
  if (count < 2) {
    return 0;
  }
  const variance = Math.max(0, (sumSquares - (sum ** 2) / count) / (count - 1));
  return Math.sqrt(variance);
}

function buildDatasetQualityNotes(
  profiles: ColumnProfile[],
  rowCount: number,
  rolesMetadata: DataRolesMetadata,
  targetColumn: string
) {
  const notes: string[] = [];
  if (!targetColumn) {
    notes.push("No target role is set; target-feature profiling is waiting for metadata.");
  }
  if (rolesMetadata.dataset_roles.length === 0) {
    notes.push("Dataset role is not set; mark training, validation, scoring, or monitoring intent in Data Roles.");
  }
  const highMissing = profiles.filter((profile) => profile.missingRate >= 0.3 && profile.role !== "ignored");
  if (highMissing.length > 0) {
    notes.push(`${highMissing.length} columns have at least 30% missing values.`);
  }
  const nearUnique = profiles.filter((profile) =>
    profile.uniqueRate >= 0.95 && !["identifier", "timestamp", "period_id", "ignored"].includes(profile.role)
  );
  if (nearUnique.length > 0) {
    notes.push(`${nearUnique.length} non-ID columns look near-unique; review roles before modeling.`);
  }
  const constants = profiles.filter((profile) => profile.unique <= 1 && profile.count > 0);
  if (constants.length > 0) {
    notes.push(`${constants.length} columns are constant in ${formatInteger(rowCount)} profiled rows.`);
  }
  return notes;
}

function isNumericMeasureColumn(
  column: DatasetPreview["columns"][number],
  rolesMetadata: DataRolesMetadata,
  rows: Array<Record<string, DatasetCellValue>>,
  isTarget: boolean
) {
  const role = columnRoleForColumn(column, rolesMetadata);
  if (role === "feature_continuous" || role === "sample_weight") {
    return true;
  }
  if (role === "feature_categorical" || role === "feature_ordinal" || role === "boolean") {
    return false;
  }
  if (column.type !== "number") {
    return false;
  }
  if (!isTarget) {
    return true;
  }
  const present = rows.map((row) => normalizeCellValue(row[column.name])).filter(isPresentCell);
  const unique = new Set(present.map(displayValue)).size;
  return unique > Math.min(20, Math.max(2, Math.floor(present.length * 0.1)));
}

function pearsonCorrelation(pairs: Array<readonly [number, number]>) {
  if (pairs.length < 3) {
    return null;
  }
  const meanX = pairs.reduce((total, pair) => total + pair[0], 0) / pairs.length;
  const meanY = pairs.reduce((total, pair) => total + pair[1], 0) / pairs.length;
  let numerator = 0;
  let sumX = 0;
  let sumY = 0;
  for (const [x, y] of pairs) {
    const dx = x - meanX;
    const dy = y - meanY;
    numerator += dx * dy;
    sumX += dx ** 2;
    sumY += dy ** 2;
  }
  const denominator = Math.sqrt(sumX * sumY);
  return denominator === 0 ? null : numerator / denominator;
}

function numericRelationStats(pairs: Array<readonly [number, number]>): NumericRelationStats {
  const pearson = pearsonCorrelation(pairs) ?? 0;
  const spearman = spearmanCorrelation(pairs) ?? 0;
  const meanX = pairs.reduce((total, pair) => total + pair[0], 0) / pairs.length;
  const meanY = pairs.reduce((total, pair) => total + pair[1], 0) / pairs.length;
  let covarianceNumerator = 0;
  let varianceXNumerator = 0;
  for (const [x, y] of pairs) {
    covarianceNumerator += (x - meanX) * (y - meanY);
    varianceXNumerator += (x - meanX) ** 2;
  }
  const covariance = pairs.length > 1 ? covarianceNumerator / (pairs.length - 1) : 0;
  const slope = varianceXNumerator === 0 ? 0 : covarianceNumerator / varianceXNumerator;
  const intercept = meanY - slope * meanX;
  return {
    pearson: roundNumber(pearson),
    spearman: roundNumber(spearman),
    rSquared: roundNumber(pearson ** 2),
    covariance: roundNumber(covariance),
    slope: roundNumber(slope),
    intercept: roundNumber(intercept)
  };
}

function spearmanCorrelation(pairs: Array<readonly [number, number]>) {
  if (pairs.length < 3) {
    return null;
  }
  const xRanks = rankValues(pairs.map((pair) => pair[0]));
  const yRanks = rankValues(pairs.map((pair) => pair[1]));
  return pearsonCorrelation(xRanks.map((rank, index) => [rank, yRanks[index]] as const));
}

function buildOrdinalTrend(
  rows: Array<Record<string, DatasetCellValue>>,
  featureColumn: string,
  targetColumn: string,
  orderedFeatureValues: string[],
  focusValue: string
) {
  const rankByValue = new Map(orderedFeatureValues.map((value, index) => [value, index + 1]));
  const pairs = rows
    .map((row) => {
      const featureValue = displayValue(row[featureColumn]);
      const targetValue = displayValue(row[targetColumn]);
      const rank = rankByValue.get(featureValue);
      return rank === undefined ? null : [rank, targetValue === focusValue ? 1 : 0] as const;
    })
    .filter((pair): pair is readonly [number, 0 | 1] => pair !== null);
  const spearman = spearmanCorrelation(pairs);
  if (spearman === null) {
    return null;
  }
  const numericOrder = orderedFeatureValues.every((value) => Number.isFinite(Number(value)));
  return {
    focusValue,
    spearman: roundNumber(spearman),
    orderBasis: numericOrder ? "numeric ascending" : "observed category order"
  };
}

function sortCategoryValues(values: string[]) {
  const numeric = values.every((value) => Number.isFinite(Number(value)));
  return [...values].sort((left, right) => numeric
    ? Number(left) - Number(right)
    : left.localeCompare(right)
  );
}

function orderOrdinalValues(values: string[]) {
  const numeric = values.every((value) => Number.isFinite(Number(value)));
  return numeric ? sortCategoryValues(values) : values;
}

function rankValues(values: number[]) {
  const sorted = values
    .map((value, index) => ({ value, index }))
    .sort((left, right) => left.value - right.value);
  const ranks = Array(values.length).fill(0);
  let index = 0;
  while (index < sorted.length) {
    let end = index + 1;
    while (end < sorted.length && sorted[end].value === sorted[index].value) {
      end += 1;
    }
    const averageRank = (index + 1 + end) / 2;
    for (let cursor = index; cursor < end; cursor += 1) {
      ranks[sorted[cursor].index] = averageRank;
    }
    index = end;
  }
  return ranks;
}

function buildScatterPlot(
  pairs: Array<readonly [number, number]>,
  xColumn: string,
  yColumn: string,
  stats: NumericRelationStats
): ScatterPlot | null {
  if (pairs.length === 0) {
    return null;
  }
  const xValues = pairs.map((pair) => pair[0]);
  const yValues = pairs.map((pair) => pair[1]);
  const xMinRaw = Math.min(...xValues);
  const xMaxRaw = Math.max(...xValues);
  const yMinRaw = Math.min(...yValues);
  const yMaxRaw = Math.max(...yValues);
  const xPadding = (xMaxRaw - xMinRaw || Math.max(1, Math.abs(xMinRaw) * 0.1)) * 0.06;
  const yPadding = (yMaxRaw - yMinRaw || Math.max(1, Math.abs(yMinRaw) * 0.1)) * 0.06;
  const xMin = xMinRaw - xPadding;
  const xMax = xMaxRaw + xPadding;
  const yMin = yMinRaw - yPadding;
  const yMax = yMaxRaw + yPadding;
  const trendLine = Number.isFinite(stats.slope) && Number.isFinite(stats.intercept)
    ? {
      x1: xMinRaw,
      y1: stats.slope * xMinRaw + stats.intercept,
      x2: xMaxRaw,
      y2: stats.slope * xMaxRaw + stats.intercept
    }
    : null;
  return {
    xColumn,
    yColumn,
    xMin,
    xMax,
    yMin,
    yMax,
    points: pairs.map(([x, y]) => ({ x, y })),
    trendLine
  };
}

function countTopValues(values: DatasetCellValue[], denominator: number) {
  const counts = new Map<string, { value: DatasetCellValue; count: number }>();
  for (const value of values) {
    const key = displayValue(value);
    const current = counts.get(key);
    counts.set(key, { value, count: (current?.count ?? 0) + 1 });
  }
  return [...counts.values()]
    .sort((left, right) => right.count - left.count || displayValue(left.value).localeCompare(displayValue(right.value)))
    .slice(0, 10)
    .map((item) => ({
      ...item,
      share: denominator === 0 ? 0 : item.count / denominator
    }));
}

function buildHistogramBins(values: number[], binCount = 12) {
  if (values.length === 0) {
    return [];
  }
  const minimum = values[0];
  const maximum = values.at(-1) ?? minimum;
  if (minimum === maximum) {
    return [{
      label: formatNumber(minimum),
      count: values.length,
      share: 1
    }];
  }

  const width = (maximum - minimum) / binCount;
  const bins = Array.from({ length: binCount }, (_, index) => {
    const start = minimum + index * width;
    const end = index === binCount - 1 ? maximum : start + width;
    return {
      label: `${formatNumber(start)} - ${formatNumber(end)}`,
      count: 0,
      share: 0
    };
  });

  for (const value of values) {
    const index = Math.min(binCount - 1, Math.floor((value - minimum) / width));
    bins[index].count += 1;
  }

  return bins.map((bin) => ({
    ...bin,
    share: bin.count / values.length
  }));
}

function buildDensityPlot(groupStats: NumericGroupStats[], groups: Map<string, number[]>, pointCount = 80): DensityPlot | null {
  const groupEntries = groupStats
    .map((summary) => ({
      summary,
      values: [...(groups.get(summary.group) ?? [])].sort((left, right) => left - right)
    }))
    .filter((entry) => entry.values.length > 0);
  const allValues = groupEntries.flatMap((entry) => entry.values);
  if (allValues.length === 0) {
    return null;
  }

  const sortedValues = [...allValues].sort((left, right) => left - right);
  const minimum = sortedValues[0];
  const maximum = sortedValues.at(-1) ?? minimum;
  const rawRange = maximum - minimum;
  const range = rawRange || Math.max(1, Math.abs(minimum) * 0.1);
  const xMin = minimum - range * 0.08;
  const xMax = maximum + range * 0.08;
  const step = (xMax - xMin) / Math.max(1, pointCount - 1);
  const xValues = Array.from({ length: pointCount }, (_, index) => xMin + index * step);
  let yMax = 0;

  const series = groupEntries.map((entry) => {
    const stdDev = standardDeviation(entry.values);
    const fallbackBandwidth = Math.max(range / 18, 0.001);
    const silverman = 1.06 * (stdDev || fallbackBandwidth) * entry.values.length ** -0.2;
    const bandwidth = Math.max(silverman, fallbackBandwidth);
    const coefficient = 1 / (entry.values.length * bandwidth * Math.sqrt(2 * Math.PI));
    const points = xValues.map((x) => {
      const kernelSum = entry.values.reduce((total, value) => {
        const z = (x - value) / bandwidth;
        return total + Math.exp(-0.5 * z * z);
      }, 0);
      const y = coefficient * kernelSum;
      yMax = Math.max(yMax, y);
      return { x, y };
    });
    return {
      group: entry.summary.group,
      color: entry.summary.color,
      points
    };
  });

  return { xMin, xMax, yMax, series };
}

function comparisonColor(index: number) {
  const colors = ["#2ea39a", "#4477c2", "#c08522", "#8b6bd6", "#cf5f5f", "#5a9f45"];
  return colors[index % colors.length];
}

function syncSelectedNames(current: string[] | null, available: string[]) {
  if (current === null) {
    return null;
  }
  const availableSet = new Set(available);
  const next = current.filter((name) => availableSet.has(name));
  if (next.length === current.length && next.every((name, index) => name === current[index])) {
    return current;
  }
  return next;
}

function uniqueDisplayValues(rows: Array<Record<string, DatasetCellValue>>, column: string) {
  return [...new Set(
    rows
      .map((row) => normalizeCellValue(row[column]))
      .filter(isPresentCell)
      .map(displayValue)
  )];
}

function normalizeCellValue(value: unknown): DatasetCellValue {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value === null) {
    return value;
  }
  return null;
}

function isPresentCell(value: DatasetCellValue): value is Exclude<DatasetCellValue, null> {
  return value !== null && value !== "";
}

function medianNumber(values: number[]) {
  if (values.length === 0) {
    return 0;
  }
  const middle = Math.floor(values.length / 2);
  return values.length % 2 === 0
    ? (values[middle - 1] + values[middle]) / 2
    : values[middle];
}

function standardDeviation(values: number[]) {
  if (values.length < 2) {
    return 0;
  }
  const mean = values.reduce((total, value) => total + value, 0) / values.length;
  const variance = values.reduce((total, value) => total + (value - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function formatInteger(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(roundNumber(value));
}

function formatNullableNumber(value: number | null) {
  return value === null ? "null" : formatNumber(value);
}

function formatSignedNumber(value: number) {
  return `${value >= 0 ? "+" : ""}${formatNumber(value)}`;
}

function formatPercent(value: number) {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
    style: "percent"
  }).format(value);
}

function formatSegmentMetric(value: number, format: SegmentResult["format"]) {
  return format === "percent" ? formatPercent(value) : formatNumber(value);
}

function formatSignedSegmentMetric(value: number, format: SegmentResult["format"]) {
  const formatted = formatSegmentMetric(Math.abs(value), format);
  return `${value >= 0 ? "+" : "-"}${formatted}`;
}

function valueToSearchText(value: unknown) {
  return displayValue(value).toLowerCase();
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "unsupported";
  }
  if (typeof value === "string") {
    return value;
  }
  return "unsupported";
}

function cellKind(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "empty";
  }
  if (typeof value === "boolean") {
    return "boolean";
  }
  if (typeof value === "number") {
    return "number";
  }
  if (typeof value === "string") {
    return "text";
  }
  return "unsupported";
}

function compareValues(left: unknown, right: unknown) {
  if (left === null || left === undefined) {
    return right === null || right === undefined ? 0 : 1;
  }
  if (right === null || right === undefined) {
    return -1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  if (typeof left === "boolean" && typeof right === "boolean") {
    return Number(left) - Number(right);
  }
  return displayValue(left).localeCompare(displayValue(right), undefined, {
    numeric: true,
    sensitivity: "base"
  });
}
