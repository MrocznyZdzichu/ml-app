import {
  Activity,
  BarChart3,
  Brain,
  CheckCircle2,
  Database,
  Drill,
  History,
  ListChecks,
  LogOut,
  RotateCcw,
  Rocket,
  Share2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, getAccessToken, setAccessToken } from "./api/client";
import type {
  BusinessCase,
  DataAsset,
  Deployment,
  ModelArtifact,
  Pipeline,
  ScoringReport,
  UserProfile
} from "./api/client";
import { DeferredPanel } from "./components/DeferredPanel";
import { JobsPanel } from "./operational/JobsPanel";
import type { DescriptiveProfileCacheEntry } from "./data/DataWorkspacePanels";
import { AuthScreen } from "./workspace/AuthScreen";
import { Overview } from "./workspace/Overview";

type TabId = "overview" | "business-cases" | "data" | "analysis" | "pipelines" | "jobs" | "models" | "scoring-reports" | "serving" | "share";

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
  { id: "jobs", label: "Jobs", icon: History },
  { id: "models", label: "Models", icon: Brain },
  { id: "scoring-reports", label: "Scoring Reports", icon: BarChart3 },
  { id: "serving", label: "Serving", icon: Rocket },
  { id: "share", label: "Share", icon: Share2 }
];

const ModelsPanel = lazy(() =>
  import("./operational/LifecyclePanels").then((module) => ({ default: module.ModelsPanel }))
);
const BusinessCasesPanel = lazy(() =>
  import("./operational/BusinessCasesPanel").then((module) => ({
    default: module.BusinessCasesPanel
  }))
);
const PipelinesPanel = lazy(() =>
  import("./operational/PipelinePanel").then((module) => ({
    default: module.PipelinesPanel
  }))
);
const DataPanel = lazy(() =>
  import("./data/DataWorkspacePanels").then((module) => ({
    default: module.DataPanel
  }))
);
const AnalysisPanel = lazy(() =>
  import("./data/DataWorkspacePanels").then((module) => ({
    default: module.AnalysisPanel
  }))
);
const ScoringReportsPanel = lazy(() =>
  import("./operational/ScoringReportsPanel").then((module) => ({ default: module.ScoringReportsPanel }))
);
const ServingPanel = lazy(() =>
  import("./operational/ServingPanel").then((module) => ({ default: module.ServingPanel }))
);
const SharePanel = lazy(() =>
  import("./operational/CollaborationPanel").then((module) => ({ default: module.CollaborationPanel }))
);
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
  const [servingDeploymentId, setServingDeploymentId] = useState("");
  const [apiStatus, setApiStatus] = useState("checking");
  const [authStatus, setAuthStatus] = useState(getAccessToken() ? "checking" : "anonymous");
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [businessCases, setBusinessCases] = useState<BusinessCase[]>([]);
  const [datasets, setDatasets] = useState<DataAsset[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [models, setModels] = useState<ModelArtifact[]>([]);
  const [scoringReports, setScoringReports] = useState<ScoringReport[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [catalogCounts, setCatalogCounts] = useState({
    businessCases: 0,
    datasets: 0,
    dataViews: 0,
    pipelines: 0,
    models: 0,
    deployments: 0
  });
  const [notice, setNotice] = useState("Workspace ready");
  const [isRefreshingWorkspace, setIsRefreshingWorkspace] = useState(false);
  const descriptiveProfileCache = useRef<Map<string, DescriptiveProfileCacheEntry>>(new Map());
  const sectionRefreshHandlers = useRef<Partial<Record<TabId, () => Promise<void>>>>({});

  const activeConfig = useMemo(
    () => navItems.find((item) => item.id === activeTab) ?? navItems[0],
    [activeTab]
  );

  const refreshResources = useCallback(async (tab: TabId | "workspace") => {
    try {
      const includeBusinessCases = ["workspace", "overview", "business-cases", "data", "analysis", "pipelines", "jobs", "models", "scoring-reports", "share"].includes(tab);
      const includeDatasets = ["workspace", "overview", "business-cases", "data", "analysis", "pipelines", "serving", "share"].includes(tab);
      const includePipelines = ["workspace", "overview", "business-cases", "data", "analysis", "pipelines", "jobs", "models", "scoring-reports"].includes(tab);
      const includeModels = ["workspace", "overview", "business-cases", "pipelines", "models", "serving"].includes(tab);
      const includeReports = ["workspace", "business-cases", "scoring-reports"].includes(tab);
      const includeDeployments = ["workspace", "overview", "business-cases", "serving"].includes(tab);
      const cacheLimit = 100;
      await Promise.all([
        includeBusinessCases
          ? api.pageBusinessCases({ limit: cacheLimit }).then((page) => {
              setBusinessCases(page.items);
              setCatalogCounts((current) => ({ ...current, businessCases: page.total }));
            })
          : Promise.resolve(),
        includeDatasets
          ? Promise.all([
              api.pageDatasets({ limit: cacheLimit }),
              api.pageDatasets({ limit: 1, asset_kind: "dataset", include_deleted: false }),
              api.pageDatasets({ limit: 1, asset_kind: "view", include_deleted: false })
            ]).then(([page, datasetPage, viewPage]) => {
              setDatasets(page.items);
              setCatalogCounts((current) => ({
                ...current,
                datasets: datasetPage.total,
                dataViews: viewPage.total
              }));
            })
          : Promise.resolve(),
        includePipelines
          ? api.pagePipelines({ limit: cacheLimit }).then((page) => {
              setPipelines(page.items);
              setCatalogCounts((current) => ({ ...current, pipelines: page.total }));
            })
          : Promise.resolve(),
        includeModels
          ? api.pageModels({ limit: cacheLimit }).then((page) => {
              setModels(page.items.map((family) => family.latest));
              setCatalogCounts((current) => ({ ...current, models: page.total }));
            })
          : Promise.resolve(),
        includeReports
          ? api.pageScoringReports({ limit: cacheLimit }).then((page) => {
              setScoringReports(page.items.map((family) => family.latest));
            })
          : Promise.resolve(),
        includeDeployments
          ? api.pageDeployments({ limit: cacheLimit }).then((page) => {
              setDeployments(page.items);
              setCatalogCounts((current) => ({ ...current, deployments: page.total }));
            })
          : Promise.resolve(),
      ]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "API request failed");
      throw error;
    }
  }, []);

  const refreshWorkspace = useCallback(
    () => refreshResources("workspace"),
    [refreshResources]
  );

  const refreshServingCatalog = useCallback(async () => {
    await refreshResources("serving");
  }, [refreshResources]);
  const refreshJobsCatalog = useCallback(
    () => refreshResources("jobs"),
    [refreshResources]
  );
  const refreshShareCatalog = useCallback(
    () => refreshResources("share"),
    [refreshResources]
  );

  const registerSectionRefresh = useCallback((tab: TabId, handler: (() => Promise<void>) | null) => {
    if (handler) sectionRefreshHandlers.current[tab] = handler;
    else delete sectionRefreshHandlers.current[tab];
  }, []);

  const registerServingRefresh = useCallback(
    (handler: (() => Promise<void>) | null) => registerSectionRefresh("serving", handler),
    [registerSectionRefresh]
  );
  const registerJobsRefresh = useCallback(
    (handler: (() => Promise<void>) | null) => registerSectionRefresh("jobs", handler),
    [registerSectionRefresh]
  );
  const registerShareRefresh = useCallback(
    (handler: (() => Promise<void>) | null) => registerSectionRefresh("share", handler),
    [registerSectionRefresh]
  );

  async function handleGlobalRefresh() {
    if (isRefreshingWorkspace) return;
    setIsRefreshingWorkspace(true);
    setNotice(`Refreshing ${activeConfig.label}…`);
    try {
      const registeredHandler = sectionRefreshHandlers.current[activeTab];
      if (registeredHandler) await registeredHandler();
      else await refreshResources(activeTab);
      setNotice(`${activeConfig.label} refreshed`);
    } catch {
      // The section refresh exposes the actionable API error in the notice bar.
    } finally {
      setIsRefreshingWorkspace(false);
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
      void refreshWorkspace().catch(() => undefined);
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
    setCatalogCounts({
      businessCases: 0,
      datasets: 0,
      dataViews: 0,
      pipelines: 0,
      models: 0,
      deployments: 0
    });
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

  function openServingDeployment(deploymentId: string) {
    setServingDeploymentId(deploymentId);
    setActiveTab("serving");
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
          <div className="topbar-actions">
            <div className={`status-pill ${apiStatus}`}>
              {apiStatus === "online" ? <CheckCircle2 size={16} /> : <Activity size={16} />}
              <span>API {apiStatus}</span>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => void handleGlobalRefresh()}
              disabled={isRefreshingWorkspace}
              aria-label="Refresh current workspace data"
              title={`Reload data used by ${activeConfig.label}`}
            >
              <RotateCcw className={isRefreshingWorkspace ? "run-spinner" : undefined} size={16} />
              {isRefreshingWorkspace ? "Refreshing…" : "Refresh"}
            </button>
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
            counts={catalogCounts}
          />
        )}
        {activeTab === "business-cases" && (
          <DeferredPanel>
            <BusinessCasesPanel
              businessCases={businessCases}
              datasets={datasets}
              pipelines={pipelines}
              models={models}
              deployments={deployments}
              scoringReports={scoringReports}
              onRefresh={() => refreshResources("business-cases")}
              onEditPipeline={openPipelineEditor}
              onOpenModels={openBusinessCaseModels}
              onOpenScoringReports={openBusinessCaseScoringReports}
              onOpenServing={openServingDeployment}
              onOpenDataset={openDatasetAnalysis}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
        {activeTab === "data" && (
          <DeferredPanel>
            <DataPanel
              businessCases={businessCases}
              datasets={datasets}
              pipelines={pipelines}
              onAnalyze={openDatasetAnalysis}
              onRefresh={() => refreshResources("data")}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
        {activeTab === "analysis" && (
          <DeferredPanel>
            <AnalysisPanel
              datasets={datasets}
              businessCases={businessCases}
              pipelines={pipelines}
              descriptiveProfileCache={descriptiveProfileCache.current}
              initialDatasetId={analysisOpenRequest?.datasetId}
              initialTab={analysisOpenRequest ? "browse" : "roles"}
              onInitialDatasetConsumed={() => setAnalysisOpenRequest(null)}
              onRefresh={() => refreshResources("analysis")}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
        {activeTab === "pipelines" && (
          <DeferredPanel>
            <PipelinesPanel
              businessCases={businessCases}
              datasets={datasets}
              pipelines={pipelines}
              models={models}
              openRequest={pipelineOpenRequest}
              onOpenRequestConsumed={() => setPipelineOpenRequest(null)}
              onRefresh={() => refreshResources("pipelines")}
              onExamineDataset={openDatasetAnalysis}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
        {activeTab === "jobs" && (
          <JobsPanel
            businessCases={businessCases}
            pipelines={pipelines}
            onRefreshCatalog={refreshJobsCatalog}
            onRegisterRefresh={registerJobsRefresh}
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
              onRefresh={() => refreshResources("models")}
              setNotice={setNotice}
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
              initialDeploymentId={servingDeploymentId}
              onRefresh={refreshServingCatalog}
              onRegisterRefresh={registerServingRefresh}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
        {activeTab === "share" && (
          <DeferredPanel>
            <SharePanel
              businessCases={businessCases}
              datasets={datasets}
              currentUser={currentUser}
              onRefresh={refreshShareCatalog}
              onRegisterRefresh={registerShareRefresh}
              setNotice={setNotice}
            />
          </DeferredPanel>
        )}
      </main>
    </div>
  );
}
