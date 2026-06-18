import {
  Activity,
  BarChart3,
  Brain,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Database,
  Drill,
  Download,
  Filter,
  ListChecks,
  LogIn,
  LogOut,
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
  UserPlus,
  X
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ChangeEvent, FormEvent, KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api, getAccessToken, setAccessToken } from "./api/client";
import type {
  DataAsset,
  DatasetPreview,
  Deployment,
  ModelArtifact,
  ScoreResponse,
  UserProfile
} from "./api/client";
import {
  columnRoleOptions,
  datasetRoleOptions,
  defaultColumnRole,
  emptyRolesMetadata,
  normalizeRolesMetadata,
  readRolesMetadata
} from "./analysis/dataRoles";
import type { DataRolesMetadata } from "./analysis/dataRoles";

type TabId = "overview" | "data" | "analysis" | "models" | "serving" | "share";

type NavItem = {
  id: TabId;
  label: string;
  icon: LucideIcon;
};

const navItems: NavItem[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "data", label: "Data", icon: Database },
  { id: "analysis", label: "Analysis", icon: BarChart3 },
  { id: "models", label: "Models", icon: Brain },
  { id: "serving", label: "Serving", icon: Rocket },
  { id: "share", label: "Share", icon: Share2 }
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [apiStatus, setApiStatus] = useState("checking");
  const [authStatus, setAuthStatus] = useState(getAccessToken() ? "checking" : "anonymous");
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [datasets, setDatasets] = useState<DataAsset[]>([]);
  const [models, setModels] = useState<ModelArtifact[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [notice, setNotice] = useState("Workspace ready");

  const activeConfig = useMemo(
    () => navItems.find((item) => item.id === activeTab) ?? navItems[0],
    [activeTab]
  );

  async function refreshWorkspace() {
    try {
      const [datasetItems, modelItems, deploymentItems] = await Promise.all([
        api.listDatasets(),
        api.listModels(),
        api.listDeployments()
      ]);
      setDatasets(datasetItems);
      setModels(modelItems);
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
    setAccessToken(token);
    const profile = await api.me();
    setCurrentUser(profile);
    setAuthStatus("authenticated");
    setNotice(`Signed in as ${profile.display_name}`);
  }

  function logout() {
    setAccessToken(null);
    setCurrentUser(null);
    setDatasets([]);
    setModels([]);
    setDeployments([]);
    setAuthStatus("anonymous");
    setNotice("Signed out");
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
          <Overview datasets={datasets} models={models} deployments={deployments} />
        )}
        {activeTab === "data" && (
          <DataPanel datasets={datasets} onRefresh={refreshWorkspace} setNotice={setNotice} />
        )}
        {activeTab === "analysis" && (
          <AnalysisPanel datasets={datasets} onRefresh={refreshWorkspace} setNotice={setNotice} />
        )}
        {activeTab === "models" && (
          <ModelsPanel
            datasets={datasets}
            models={models}
            onRefresh={refreshWorkspace}
            setNotice={setNotice}
          />
        )}
        {activeTab === "serving" && (
          <ServingPanel
            deployments={deployments}
            models={models}
            onRefresh={refreshWorkspace}
            setNotice={setNotice}
          />
        )}
        {activeTab === "share" && (
          <SharePanel
            datasets={datasets}
            models={models}
            deployments={deployments}
            setNotice={setNotice}
          />
        )}
      </main>
    </div>
  );
}

function AuthScreen({
  apiStatus,
  isChecking,
  onAuthenticated
}: {
  apiStatus: string;
  isChecking: boolean;
  onAuthenticated: (token: string) => Promise<void>;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("demo@example.com");
  const [displayName, setDisplayName] = useState("Demo Analyst");
  const [password, setPassword] = useState("password123");
  const [message, setMessage] = useState(isChecking ? "Checking session" : "Sign in to continue");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isChecking && message === "Checking session") {
      setMessage("Sign in to continue");
    }
  }, [isChecking, message]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setMessage(mode === "login" ? "Signing in" : "Creating account");
    try {
      const response =
        mode === "login"
          ? await api.login({ email, password })
          : await api.register({ email, password, display_name: displayName });
      await onAuthenticated(response.access_token);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-panel">
        <div className="brand auth-brand">
          <div className="brand-mark">ML</div>
          <div>
            <strong>ML App</strong>
            <span>Private analytics workspace</span>
          </div>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button
            className={mode === "login" ? "active" : ""}
            onClick={() => setMode("login")}
            type="button"
          >
            <LogIn size={16} />
            Login
          </button>
          <button
            className={mode === "register" ? "active" : ""}
            onClick={() => setMode("register")}
            type="button"
          >
            <UserPlus size={16} />
            Register
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          <label>
            Email
            <input
              autoComplete="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          {mode === "register" && (
            <label>
              Display name
              <input
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
          )}
          <label>
            Password
            <input
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={6}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <button className="primary-button" disabled={isSubmitting || isChecking} type="submit">
            {mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />}
            {mode === "login" ? "Login" : "Create account"}
          </button>
        </form>

        <div className="auth-footer">
          <span>{message}</span>
          <span>API {apiStatus}</span>
        </div>
      </section>
    </main>
  );
}

function Overview({
  datasets,
  models,
  deployments
}: {
  datasets: DataAsset[];
  models: ModelArtifact[];
  deployments: Deployment[];
}) {
  const activeDataAssets = datasets.filter((dataset) => dataset.status !== "deleted");
  const dataViews = activeDataAssets.filter(isDataView);
  const sourceDatasets = activeDataAssets.filter((dataset) => !isDataView(dataset));
  const recentAssets = [
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
      <Metric icon={Database} label="Datasets" value={sourceDatasets.length} tone="teal" />
      <Metric icon={Table2} label="Data Views" value={dataViews.length} tone="blue" />
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

function Metric({
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

function DataPanel({
  datasets,
  onRefresh,
  setNotice
}: {
  datasets: DataAsset[];
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const activeDatasets = datasets.filter((dataset) => dataset.status !== "deleted" && !isDataView(dataset));
  const dataViews = datasets.filter((dataset) => dataset.status !== "deleted" && isDataView(dataset));
  const deletedDatasets = datasets.filter((dataset) => dataset.status === "deleted");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setNotice("Choose a CSV file first");
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

    const uploaded = await api.uploadDataset(formData);
    setNotice(
      `Uploaded ${uploaded.name}: ${uploaded.row_count ?? 0} rows, headers ${uploaded.has_header ? "detected" : "not detected"}`
    );
    setName("");
    setDescription("");
    setTags("");
    setFile(null);
    setFileInputKey((current) => current + 1);
    await onRefresh();
  }

  async function deleteDataset(dataset: DataAsset) {
    const deleted = await api.deleteDataset(dataset.id);
    setNotice(`Deleted ${deleted.name}`);
    await onRefresh();
  }

  return (
    <section className="two-column">
      <form className="panel form-panel" onSubmit={submit}>
        <div className="panel-header">
          <h2>Upload CSV</h2>
          <Upload size={18} />
        </div>
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          CSV file
          <input
            accept=".csv,text/csv"
            key={fileInputKey}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
            type="file"
          />
        </label>
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
          <input value={tags} onChange={(event) => setTags(event.target.value)} />
        </label>
        <button className="primary-button" type="submit">
          <Upload size={16} />
          Upload
        </button>
      </form>

      <div className="repository-column">
        <AssetList
          title="Active datasets"
          assets={activeDatasets.map((item) => ({
            id: item.id,
            name: item.name,
            meta: datasetMeta(item),
            status: item.status,
            canDelete: true,
            onDelete: () => deleteDataset(item)
          }))}
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
        <AssetList
          title="Deleted datasets"
          assets={deletedDatasets.map((item) => ({
            id: item.id,
            name: item.name,
            meta: datasetMeta(item),
            status: item.status
          }))}
        />
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

function shortId(value: string) {
  return value.slice(0, 8);
}

function AnalysisPanel({
  datasets,
  onRefresh,
  setNotice
}: {
  datasets: DataAsset[];
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
}) {
  const [activeAnalysisTab, setActiveAnalysisTab] = useState<"roles" | "browse" | "descriptive" | "visualization">("roles");
  const [datasetId, setDatasetId] = useState("");
  const availableDatasets = useMemo(
    () => datasets.filter((dataset) => dataset.status !== "deleted"),
    [datasets]
  );

  useEffect(() => {
    const nextDatasetId = availableDatasets.some((dataset) => dataset.id === datasetId)
      ? datasetId
      : availableDatasets[0]?.id ?? "";
    if (nextDatasetId !== datasetId) {
      setDatasetId(nextDatasetId);
    }
  }, [availableDatasets, datasetId]);

  return (
    <section className="analysis-workspace">
      <div className="analysis-tabs" role="tablist" aria-label="Analysis sections">
        <button
          className={activeAnalysisTab === "roles" ? "active" : ""}
          onClick={() => setActiveAnalysisTab("roles")}
          type="button"
        >
          <ListChecks size={16} />
          Data Roles
        </button>
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
        />
      )}
      {activeAnalysisTab === "descriptive" && (
        <DescriptiveAnalysisPanel
          datasets={availableDatasets}
          datasetId={datasetId}
          setDatasetId={setDatasetId}
          setNotice={setNotice}
        />
      )}
      {activeAnalysisTab === "visualization" && (
        <AnalysisPlaceholder
          icon={Activity}
          title="Visualization and Trends"
          message="This workspace is reserved for charts, trend exploration, and visual comparison tools."
        />
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
                {dataset.name}
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
type FilterOperator =
  | "contains"
  | "equals"
  | "not_equals"
  | "in"
  | "regex"
  | "starts_with"
  | "ends_with"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "empty"
  | "not_empty";
type ColumnFilterConfig = {
  operator: FilterOperator;
  value: string;
  values?: string[];
};
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
};

type SegmentProfile = {
  columns: string[];
  segment: string;
  count: number;
  targetValue: string;
  baseline: number;
  segmentValue: number;
  lift: number;
  format: "number" | "percent";
};

type TargetTypeSetting = "auto" | "categorical" | "continuous";
type EffectiveTargetType = "categorical" | "continuous";

type ProfilingRangeSettings = {
  includeSummary: boolean;
  includeUnivariate: boolean;
  includeTargetRelations: boolean;
  includeSegments: boolean;
  rowLimit: number;
  maxTargetFeatures: number;
  maxSegmentFeatures: number;
};

const defaultProfilingRangeSettings: ProfilingRangeSettings = {
  includeSummary: true,
  includeUnivariate: true,
  includeTargetRelations: true,
  includeSegments: true,
  rowLimit: 50000,
  maxTargetFeatures: 30,
  maxSegmentFeatures: 4
};

function DescriptiveAnalysisPanel({
  datasets,
  datasetId,
  setDatasetId,
  setNotice
}: {
  datasets: DataAsset[];
  datasetId: string;
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
  const [showIgnoredColumns, setShowIgnoredColumns] = useState(false);
  const [hasProfileRun, setHasProfileRun] = useState(false);
  const [setupCollapsed, setSetupCollapsed] = useState(false);
  const [univariateCollapsed, setUnivariateCollapsed] = useState(false);
  const [targetCollapsed, setTargetCollapsed] = useState(false);
  const [segmentCollapsed, setSegmentCollapsed] = useState(true);
  const [selectedProfileColumns, setSelectedProfileColumns] = useState<string[] | null>(null);
  const [selectedRelationFeatures, setSelectedRelationFeatures] = useState<string[] | null>(null);
  const [profileColumnsModalOpen, setProfileColumnsModalOpen] = useState(false);
  const [relationColumnsModalOpen, setRelationColumnsModalOpen] = useState(false);
  const [profilingRangeModalOpen, setProfilingRangeModalOpen] = useState(false);
  const [profilingRange, setProfilingRange] = useState<ProfilingRangeSettings>(defaultProfilingRangeSettings);
  const profileRequestId = useRef(0);
  const schemaRequestId = useRef(0);
  const selectedDataset = datasets.find((dataset) => dataset.id === datasetId) ?? null;
  const configPreview = preview ?? schemaPreview;
  const columns = configPreview?.columns ?? [];
  const rows = preview?.records ?? [];
  const targetInferenceRows = preview?.records ?? schemaPreview?.records ?? [];
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

  useEffect(() => {
    const schemaRequestIdValue = schemaRequestId.current + 1;
    schemaRequestId.current = schemaRequestIdValue;
    profileRequestId.current += 1;
    setPreview(null);
    setSchemaPreview(null);
    setError("");
    setSchemaError("");
    setIsLoading(false);
    setIsLoadingSchema(Boolean(datasetId));
    setHasProfileRun(false);
    setTargetColumn("");
    setTargetTypeSetting("auto");
    setSelectedProfileColumns(null);
    setSelectedRelationFeatures(null);

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
  }, [datasetId]);

  useEffect(() => {
    if (columns.length === 0) {
      setTargetColumn("");
      return;
    }
    if (!targetColumn || !columns.some((column) => column.name === targetColumn)) {
      setTargetColumn(inferredTargetColumn);
    }
  }, [columns, inferredTargetColumn, targetColumn]);

  const shouldBuildColumnProfiles =
    profilingRange.includeSummary ||
    profilingRange.includeUnivariate ||
    profilingRange.includeTargetRelations;
  const columnProfiles = useMemo(
    () => shouldBuildColumnProfiles
      ? columns.map((column) => buildColumnProfile(column, rows, rolesMetadata))
      : [],
    [columns, rolesMetadata, rows, shouldBuildColumnProfiles]
  );
  const selectableProfiles = showIgnoredColumns
    ? columnProfiles
    : columnProfiles.filter((profile) => !["ignored", "identifier"].includes(profile.role));
  const activeProfileColumns = selectedProfileColumns ?? selectableProfiles.map((profile) => profile.name);
  const visibleProfiles = selectableProfiles.filter((profile) =>
    activeProfileColumns.includes(profile.name)
  );
  const profileByName = new Map(columnProfiles.map((profile) => [profile.name, profile]));
  const targetRelations = useMemo(
    () => profilingRange.includeTargetRelations
      ? buildTargetRelations(rows, columns, rolesMetadata, effectiveTargetColumn, effectiveTargetType).slice(0, profilingRange.maxTargetFeatures)
      : [],
    [columns, effectiveTargetColumn, effectiveTargetType, profilingRange.includeTargetRelations, profilingRange.maxTargetFeatures, rolesMetadata, rows]
  );
  const activeRelationFeatures = selectedRelationFeatures ?? targetRelations.map((relation) => relation.feature);
  const visibleTargetRelations = targetRelations.filter((relation) =>
    activeRelationFeatures.includes(relation.feature)
  );
  const segmentProfile = useMemo(
    () => profilingRange.includeSegments
      ? buildSegmentProfile(rows, columns, rolesMetadata, effectiveTargetColumn, effectiveTargetType, profilingRange.maxSegmentFeatures)
      : null,
    [columns, effectiveTargetColumn, effectiveTargetType, profilingRange.includeSegments, profilingRange.maxSegmentFeatures, rolesMetadata, rows]
  );
  const dataQualityNotes = useMemo(
    () => profilingRange.includeSummary
      ? buildDatasetQualityNotes(columnProfiles, rows.length, rolesMetadata, effectiveTargetColumn)
      : [],
    [columnProfiles, effectiveTargetColumn, profilingRange.includeSummary, rolesMetadata, rows.length]
  );
  const numericProfiles = columnProfiles.filter((profile) => profile.mean !== null);
  const categoricalProfiles = columnProfiles.filter((profile) =>
    ["feature_categorical", "feature_ordinal", "boolean", "target"].includes(profile.role) ||
    ["text", "boolean"].includes(profile.type)
  );
  const featureCount = columns.filter((column) =>
    !["ignored", "identifier", "target"].includes(columnRoleForColumn(column, rolesMetadata))
  ).length;
  const targetSummary = effectiveTargetColumn
    ? profileByName.get(effectiveTargetColumn)
    : undefined;
  const enabledRangeLabels = [
    profilingRange.includeSummary ? "summary" : "",
    profilingRange.includeUnivariate ? "univariate" : "",
    profilingRange.includeTargetRelations ? "target relations" : "",
    profilingRange.includeSegments ? "segments" : ""
  ].filter(Boolean);

  useEffect(() => {
    setSelectedProfileColumns((current) => syncSelectedNames(current, selectableProfiles.map((profile) => profile.name)));
  }, [selectableProfiles]);

  useEffect(() => {
    setSelectedRelationFeatures((current) => syncSelectedNames(current, targetRelations.map((relation) => relation.feature)));
  }, [targetRelations]);

  async function runProfiling() {
    if (!datasetId) {
      setNotice("Choose a dataset first");
      return;
    }

    const requestId = profileRequestId.current + 1;
    profileRequestId.current = requestId;
    setIsLoading(true);
    setError("");
    setHasProfileRun(true);
    setSetupCollapsed(false);
    setNotice("Profiling dataset. This can take a moment.");

    try {
      const result = await api.previewDataset(datasetId, profilingRange.rowLimit);
      if (profileRequestId.current !== requestId) {
        return;
      }
      setPreview(result);
      setNotice(`Profile loaded for ${result.returned_count} of ${result.row_count} rows`);
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
          <span>{isLoading ? "running" : isLoadingSchema ? "loading columns" : hasProfileRun && preview ? "ready" : "not started"}</span>
        </button>

        {!setupCollapsed && (
          <>
            <div className="descriptive-toolbar">
              <label>
                Dataset
                <select value={datasetId} onChange={(event) => updateDataset(event.target.value)}>
                  {datasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {dataset.name}
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
            {!isLoading && !error && preview && preview.row_count === 0 && (
              <div className="empty-state">Dataset is empty</div>
            )}

            {!isLoading && !error && preview && preview.row_count > 0 && (
              <>
                <section className="profile-metrics">
                  <Metric icon={Database} label="Rows profiled" value={preview.returned_count} tone="teal" />
                  <Metric icon={Table2} label="Columns" value={columns.length} tone="blue" />
                  <Metric icon={BarChart3} label="Features" value={featureCount} tone="amber" />
                  <Metric icon={Activity} label="Feature relations" value={targetRelations.length} tone="teal" />
                </section>

                <div className="profile-range-summary">
                  <strong>Profiling range</strong>
                  <span>{enabledRangeLabels.join(", ")} / up to {formatInteger(profilingRange.rowLimit)} rows</span>
                </div>

                {profilingRange.includeSummary && (
                  <section className="profile-overview">
                    <div className="panel-header">
                      <h2>Smart dataset profile</h2>
                      {preview.returned_count < preview.row_count && (
                        <span className="muted-text">Preview limited to {preview.returned_count} rows</span>
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

      {!isLoading && !error && preview && preview.row_count > 0 && (
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
                      {profile.mean !== null ? (
                        <>
                          <MiniHistogram bins={profile.histogram} />
                          <div className="profile-stat-grid">
                            <ProfileFact label="Mean" value={formatNumber(profile.mean)} />
                            <ProfileFact label="Median" value={formatNullableNumber(profile.median)} />
                            <ProfileFact label="Min" value={displayValue(profile.minimum)} />
                            <ProfileFact label="Max" value={displayValue(profile.maximum)} />
                          </div>
                        </>
                      ) : (
                        <div className="top-values">
                          {profile.topValues.slice(0, 4).map((item) => (
                            <div className="top-value-row" key={displayValue(item.value)}>
                              <span>{displayValue(item.value)}</span>
                              <div className="mini-bar" aria-hidden="true">
                                <div style={{ width: `${Math.max(4, item.share * 100)}%` }} />
                              </div>
                              <em>{formatPercent(item.share)}</em>
                            </div>
                          ))}
                        </div>
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
                  {targetRelations.length > 0 && (
                    <ColumnSelectionSummary
                      columns={targetRelations.map((relation) => ({ name: relation.feature, meta: `${columnRoleLabel(relation.role)} / ${relation.kind}` }))}
                      selected={activeRelationFeatures}
                      onOpen={() => setRelationColumnsModalOpen(true)}
                    />
                  )}
                  {!effectiveTargetColumn && (
                    <div className="empty-state">
                      Select a target or set one in Data Roles to rank feature relationships.
                    </div>
                  )}
                  {effectiveTargetColumn && targetRelations.length === 0 && (
                    <div className="empty-state">No eligible feature relationships found for the selected target.</div>
                  )}
                  {effectiveTargetColumn && targetRelations.length > 0 && visibleTargetRelations.length === 0 && (
                    <div className="empty-state">No feature relationships selected.</div>
                  )}
                  {effectiveTargetColumn && visibleTargetRelations.length > 0 && (
                    <div className="relation-list">
                      {visibleTargetRelations.slice(0, 10).map((relation) => (
                        <article className="relation-row" key={relation.feature}>
                          <div>
                            <strong>{relation.feature}</strong>
                            <span>{columnRoleLabel(relation.role)} / {relation.kind}</span>
                          </div>
                          <div className="relation-score">
                            <div className="mini-bar" aria-hidden="true">
                              <div style={{ width: `${Math.max(4, relation.score * 100)}%` }} />
                            </div>
                            <em>{relation.signal}</em>
                          </div>
                          <p>{relation.detail}</p>
                        </article>
                      ))}
                    </div>
                  )}
                </div>

                <aside className="target-context">
                  <div className="panel-header">
                    <h2>Target context</h2>
                  </div>
                  {targetSummary ? (
                    <>
                      <div className="profile-stat-grid">
                        <ProfileFact label="Role" value={columnRoleLabel(targetSummary.role)} />
                        <ProfileFact label="Target type" value={effectiveTargetType} />
                        <ProfileFact label="Type" value={targetSummary.type} />
                        <ProfileFact label="Missing" value={formatPercent(targetSummary.missingRate)} />
                        <ProfileFact label="Unique" value={formatInteger(targetSummary.unique)} />
                      </div>
                      {targetSummary.mean !== null && <MiniHistogram bins={targetSummary.histogram} />}
                      <div className="top-values">
                        {targetSummary.topValues.slice(0, 6).map((item) => (
                          <div className="top-value-row" key={displayValue(item.value)}>
                            <span>{displayValue(item.value)}</span>
                            <div className="mini-bar" aria-hidden="true">
                              <div style={{ width: `${Math.max(4, item.share * 100)}%` }} />
                            </div>
                            <em>{formatPercent(item.share)}</em>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="empty-state compact-empty">Target not selected</div>
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
              segmentProfile ? (
                <div className="segment-scan">
                  <div className="profile-summary-grid">
                    <ProfileFact label="Columns" value={segmentProfile.columns.join(" + ")} />
                    <ProfileFact label="Segment" value={segmentProfile.segment} />
                    <ProfileFact label="Rows" value={formatInteger(segmentProfile.count)} />
                    <ProfileFact label="Target focus" value={segmentProfile.targetValue} />
                  </div>
                  <p>
                    Segment value {formatSegmentMetric(segmentProfile.segmentValue, segmentProfile.format)} vs baseline{" "}
                    {formatSegmentMetric(segmentProfile.baseline, segmentProfile.format)} (
                    {formatSignedSegmentMetric(segmentProfile.lift, segmentProfile.format)} difference).
                  </p>
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
          title="Target relationship columns"
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
    "includeSummary" | "includeUnivariate" | "includeTargetRelations" | "includeSegments"
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
              <h2>Limits</h2>
            </div>
            <div className="range-number-grid">
              <label>
                Row sample limit
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
  setNotice
}: {
  datasets: DataAsset[];
  datasetId: string;
  setDatasetId: (datasetId: string) => void;
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
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
    api
      .previewDataset(datasetId)
      .then((result) => {
        if (!isCurrent) {
          return;
        }
        setPreview(result);
        setNotice(`Loaded ${result.returned_count} of ${result.row_count} rows`);
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
                  {dataset.name}
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
          <button
            className="primary-button toolbar-button"
            disabled={!preview || isSavingView}
            onClick={() => setIsSaveViewOpen(true)}
            type="button"
          >
            <Save size={16} />
            Save View
          </button>
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
  if (type === "number" || type === "date") {
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
  rolesMetadata: DataRolesMetadata
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
    histogram: mean === null ? [] : buildHistogramBins(numericValues),
    examples: present.slice(0, 3),
    notes
  };
}

function buildTargetRelations(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"],
  rolesMetadata: DataRolesMetadata,
  targetColumn: string,
  targetType: EffectiveTargetType
): TargetRelationProfile[] {
  const target = columns.find((column) => column.name === targetColumn);
  if (!target) {
    return [];
  }

  const targetIsNumeric = targetType === "continuous";
  const relations = columns
    .filter((column) => column.name !== target.name)
    .filter((column) => !["ignored", "identifier"].includes(columnRoleForColumn(column, rolesMetadata)))
    .map((feature) => {
      const role = columnRoleForColumn(feature, rolesMetadata);
      const featureIsNumeric = isNumericMeasureColumn(feature, rolesMetadata, rows, false);
      const relationRows = rows.filter((row) =>
        isPresentCell(normalizeCellValue(row[target.name])) &&
        isPresentCell(normalizeCellValue(row[feature.name]))
      );
      if (relationRows.length < 3) {
        return null;
      }

      if (targetIsNumeric && featureIsNumeric) {
        const pairs = relationRows
          .map((row) => [Number(row[feature.name]), Number(row[target.name])] as const)
          .filter(([featureValue, targetValue]) => Number.isFinite(featureValue) && Number.isFinite(targetValue));
        const correlation = pearsonCorrelation(pairs);
        if (correlation === null) {
          return null;
        }
        return {
          feature: feature.name,
          role,
          type: feature.type,
          kind: "numeric correlation",
          score: Math.min(1, Math.abs(correlation)),
          signal: `r ${formatSignedNumber(correlation)}`,
          detail: `${feature.name} moves ${correlation >= 0 ? "with" : "against"} ${target.name} in the loaded sample.`
        };
      }

      if (targetIsNumeric && !featureIsNumeric) {
        return groupedMeanRelation({
          rows: relationRows,
          groupColumn: feature.name,
          numericColumn: target.name,
          feature,
          role,
          kind: "target mean by feature"
        });
      }

      if (!targetIsNumeric && featureIsNumeric) {
        return groupedMeanRelation({
          rows: relationRows,
          groupColumn: target.name,
          numericColumn: feature.name,
          feature,
          role,
          kind: "feature mean by target"
        });
      }

      return categoricalRelation(relationRows, target.name, feature, role);
    })
    .filter((relation): relation is TargetRelationProfile => relation !== null);

  return relations.sort((left, right) => right.score - left.score);
}

function groupedMeanRelation({
  rows,
  groupColumn,
  numericColumn,
  feature,
  role,
  kind
}: {
  rows: Array<Record<string, DatasetCellValue>>;
  groupColumn: string;
  numericColumn: string;
  feature: DatasetPreview["columns"][number];
  role: string;
  kind: string;
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
    .map(([group, values]) => ({
      group,
      count: values.length,
      mean: values.reduce((total, value) => total + value, 0) / values.length
    }))
    .filter((summary) => summary.count >= minimumGroupSize);
  if (summaries.length < 2) {
    return null;
  }

  const allValues = [...groups.values()].flat();
  const spread = standardDeviation(allValues);
  const ordered = summaries.sort((left, right) => right.mean - left.mean);
  const range = ordered[0].mean - ordered.at(-1)!.mean;
  const score = spread === 0 ? 0 : Math.min(1, Math.abs(range) / (spread * 4));
  return {
    feature: feature.name,
    role,
    type: feature.type,
    kind,
    score,
    signal: `effect ${formatNumber(score)}`,
    detail: `${ordered[0].group} has the highest mean (${formatNumber(ordered[0].mean)}), ${ordered.at(-1)!.group} the lowest (${formatNumber(ordered.at(-1)!.mean)}).`
  };
}

function categoricalRelation(
  rows: Array<Record<string, DatasetCellValue>>,
  targetColumn: string,
  feature: DatasetPreview["columns"][number],
  role: string
): TargetRelationProfile | null {
  const targetValues = uniqueDisplayValues(rows, targetColumn);
  const featureValues = uniqueDisplayValues(rows, feature.name);
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
  let strongest = { targetValue: "", featureValue: "", lift: 0 };
  for (const targetValue of targetValues) {
    for (const featureValue of featureValues) {
      const observed = cells.get(`${targetValue}\u0000${featureValue}`) ?? 0;
      const expected = ((rowTotals.get(targetValue) ?? 0) * (columnTotals.get(featureValue) ?? 0)) / rows.length;
      if (expected > 0) {
        chiSquare += ((observed - expected) ** 2) / expected;
        const lift = observed / expected;
        if (Math.abs(lift - 1) > Math.abs(strongest.lift - 1)) {
          strongest = { targetValue, featureValue, lift };
        }
      }
    }
  }

  const denominator = rows.length * Math.max(1, Math.min(targetValues.length - 1, featureValues.length - 1));
  const cramersV = denominator === 0 ? 0 : Math.sqrt(chiSquare / denominator);
  return {
    feature: feature.name,
    role,
    type: feature.type,
    kind: "categorical association",
    score: Math.min(1, cramersV),
    signal: `V ${formatNumber(cramersV)}`,
    detail: `${feature.name}=${strongest.featureValue} is ${formatNumber(strongest.lift)}x expected with target ${strongest.targetValue}.`
  };
}

function buildSegmentProfile(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"],
  rolesMetadata: DataRolesMetadata,
  targetColumn: string,
  targetType: EffectiveTargetType,
  maxSegmentFeatures: number
): SegmentProfile | null {
  const target = columns.find((column) => column.name === targetColumn);
  if (!target) {
    return null;
  }

  const targetIsNumeric = targetType === "continuous";
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

  const selected = candidates.slice(0, 2);
  const groups = new Map<string, Array<Record<string, DatasetCellValue>>>();
  for (const row of rows) {
    if (!isPresentCell(normalizeCellValue(row[targetColumn]))) {
      continue;
    }
    const keyValues = selected.map((column) => displayValue(row[column.name]));
    if (keyValues.some((value) => value === "null")) {
      continue;
    }
    const key = keyValues.join(" / ");
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }

  const minimumGroupSize = Math.max(5, Math.floor(rows.length * 0.03));
  if (targetIsNumeric) {
    const targetValues = rows.map((row) => Number(row[targetColumn])).filter(Number.isFinite);
    const baseline = targetValues.reduce((total, value) => total + value, 0) / targetValues.length;
    let best: SegmentProfile | null = null;
    for (const [segment, groupRows] of groups.entries()) {
      if (groupRows.length < minimumGroupSize) {
        continue;
      }
      const values = groupRows.map((row) => Number(row[targetColumn])).filter(Number.isFinite);
      const segmentValue = values.reduce((total, value) => total + value, 0) / values.length;
      const lift = segmentValue - baseline;
      if (!best || Math.abs(lift) > Math.abs(best.lift)) {
        best = {
          columns: selected.map((column) => column.name),
          segment,
          count: groupRows.length,
          targetValue: `mean ${targetColumn}`,
          baseline,
          segmentValue,
          lift,
          format: "number"
        };
      }
    }
    return best;
  }

  const targetCounts = countTopValues(rows.map((row) => normalizeCellValue(row[targetColumn])).filter(isPresentCell), rows.length);
  let best: SegmentProfile | null = null;
  for (const [segment, groupRows] of groups.entries()) {
    if (groupRows.length < minimumGroupSize) {
      continue;
    }
    for (const targetValue of targetCounts.map((item) => item.value)) {
      const targetLabel = displayValue(targetValue);
      const baseline = targetCounts.find((item) => displayValue(item.value) === targetLabel)?.share ?? 0;
      const segmentValue = groupRows.filter((row) => displayValue(row[targetColumn]) === targetLabel).length / groupRows.length;
      const lift = segmentValue - baseline;
      if (!best || Math.abs(lift) > Math.abs(best.lift)) {
        best = {
          columns: selected.map((column) => column.name),
          segment,
          count: groupRows.length,
          targetValue: targetLabel,
          baseline,
          segmentValue,
          lift,
          format: "percent"
        };
      }
    }
  }
  return best;
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

function syncSelectedNames(current: string[] | null, available: string[]) {
  if (current === null) {
    return null;
  }
  const availableSet = new Set(available);
  return current.filter((name) => availableSet.has(name));
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

function formatSegmentMetric(value: number, format: SegmentProfile["format"]) {
  return format === "percent" ? formatPercent(value) : formatNumber(value);
}

function formatSignedSegmentMetric(value: number, format: SegmentProfile["format"]) {
  const formatted = formatSegmentMetric(Math.abs(value), format);
  return `${value >= 0 ? "+" : "-"}${formatted}`;
}

function AnalysisPlaceholder({
  icon: Icon,
  title,
  message
}: {
  icon: LucideIcon;
  title: string;
  message: string;
}) {
  return (
    <div className="panel analysis-placeholder">
      <Icon size={22} />
      <h2>{title}</h2>
      <p>{message}</p>
    </div>
  );
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

function ModelsPanel({
  datasets,
  models,
  onRefresh,
  setNotice
}: {
  datasets: DataAsset[];
  models: ModelArtifact[];
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
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

function ServingPanel({
  deployments,
  models,
  onRefresh,
  setNotice
}: {
  deployments: Deployment[];
  models: ModelArtifact[];
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
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

function SharePanel({
  datasets,
  models,
  deployments,
  setNotice
}: {
  datasets: DataAsset[];
  models: ModelArtifact[];
  deployments: Deployment[];
  setNotice: (message: string) => void;
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

function AssetList({
  title,
  assets
}: {
  title: string;
  assets: Array<{
    id: string;
    name: string;
    meta: string;
    status: string;
    canDelete?: boolean;
    onDelete?: () => void;
  }>;
}) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
      </div>
      <div className="asset-list">
        {assets.map((asset) => (
          <div className="asset-row" key={asset.id}>
            <div>
              <strong>{asset.name}</strong>
              <span>{asset.meta}</span>
            </div>
            <div className="asset-actions">
              <em>{asset.status}</em>
              {asset.canDelete && asset.onDelete && (
                <button
                  aria-label={`Delete ${asset.name}`}
                  className="icon-button danger-icon"
                  onClick={asset.onDelete}
                  title="Delete dataset"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              )}
            </div>
          </div>
        ))}
        {assets.length === 0 && <div className="empty-state">Nothing registered yet</div>}
      </div>
    </div>
  );
}
