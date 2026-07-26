import {
  BarChart3,
  Brain,
  Database,
  Filter,
  History,
  GitBranch,
  ListChecks,
  Play,
  Plus,
  RotateCcw,
  Rocket,
  Search,
  Share2,
  Save,
  Trash2,
  X
} from "lucide-react";
import type { FormEvent } from "react";
import { lazy, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCase,
  BusinessCaseDataAttachment,
  DataAsset,
  Deployment,
  ModelArtifact,
  Pipeline,
  PipelineRun,
  PipelineVersion,
  ScoringReport
} from "../api/client";
import { AssetList } from "../components/AssetList";
import { DeferredPanel } from "../components/DeferredPanel";
import { PaginationControls } from "../components/PaginationControls";
import { PagedCatalogSelect } from "../components/PagedCatalogSelect";
import { useVersionedResourceNavigation } from "../components/dialogNavigation";
import { ArtifactDependenciesDialog } from "../operational/ArtifactDependenciesDialog";
import {
  DatasetVersionHistoryDialog,
  datasetVersionGroups,
  isDataView
} from "../data/DataWorkspacePanels";
import { ArtifactFilters } from "../components/ArtifactFilters";
import {
  canonicalizeWorkflowDatasetIds,
  normalizeWorkflowDefinition
} from "../pipelines/workflowContract";
import {
  PipelineVersionHistoryDialog,
  PipelineRunDetailsDialog,
  PipelineRunHistoryDialog
} from "../pipelines/PipelineRunDialogs";
import {
  businessCaseDataRoleOptions,
  requiresRuntimeDatasetSelection
} from "../pipelines/dataContractOptions";
import {
  resolvePipelineRunInputs,
  resolvePipelineRunModels,
  type PipelineRunInput,
  type PipelineRunModel
} from "../pipelines/pipelineRunInputs";
import { formatDateTime, shortId } from "../shared/formatters";
import {
  PipelineRunDatasetInputSelector,
  PipelineRunModelSelector
} from "../pipelines/PipelineRunSelectors";
import { businessCaseName, pipelineName } from "../shared/catalogLabels";

const ModelDetailsDialog = lazy(() =>
  import("../operational/LifecyclePanels").then((module) => ({ default: module.ModelDetailsDialog }))
);
const ModelVersionHistoryDialog = lazy(() =>
  import("../operational/LifecyclePanels").then((module) => ({ default: module.ModelVersionHistoryDialog }))
);
const ScoringReportDialog = lazy(() =>
  import("../operational/ScoringReportsPanel").then((module) => ({ default: module.ScoringReportDialog }))
);
const ScoringReportHistoryDialog = lazy(() =>
  import("../operational/ScoringReportsPanel").then((module) => ({ default: module.ScoringReportHistoryDialog }))
);

export function BusinessCasesPanel({
  businessCases,
  datasets,
  pipelines,
  models,
  deployments,
  scoringReports,
  onRefresh,
  onEditPipeline,
  onOpenModels,
  onOpenScoringReports,
  onOpenServing,
  onOpenDataset,
  setNotice
}: {
  businessCases: BusinessCase[];
  datasets: DataAsset[];
  pipelines: Pipeline[];
  models: ModelArtifact[];
  deployments: Deployment[];
  scoringReports: ScoringReport[];
  onRefresh: () => Promise<void>;
  onEditPipeline: (pipelineId: string) => void;
  onOpenModels: (businessCaseId: string) => void;
  onOpenScoringReports: (businessCaseId: string) => void;
  onOpenServing: (deploymentId: string) => void;
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
  const [selectedBusinessCaseSnapshot, setSelectedBusinessCaseSnapshot] = useState<BusinessCase | undefined>();
  const [selectedDataAssetId, setSelectedDataAssetId] = useState("");
  const [selectedDataAssetSnapshot, setSelectedDataAssetSnapshot] = useState<DataAsset | undefined>();
  const [selectedRole, setSelectedRole] = useState("training");
  const [contextNote, setContextNote] = useState("");
  const [primaryKeyColumn, setPrimaryKeyColumn] = useState("");
  const [mappingTargetColumn, setMappingTargetColumn] = useState("");
  const [attachments, setAttachments] = useState<BusinessCaseDataAttachment[]>([]);
  const [attachmentTotal, setAttachmentTotal] = useState(0);
  const [attachmentOffset, setAttachmentOffset] = useState(0);
  const [attachmentSearch, setAttachmentSearch] = useState("");
  const [deletedAttachments, setDeletedAttachments] = useState<BusinessCaseDataAttachment[]>([]);
  const [deletedAttachmentTotal, setDeletedAttachmentTotal] = useState(0);
  const [deletedAttachmentOffset, setDeletedAttachmentOffset] = useState(0);
  const [attachmentRefreshKey, setAttachmentRefreshKey] = useState(0);
  const [businessCaseSearch, setBusinessCaseSearch] = useState("");
  const [businessCasePage, setBusinessCasePage] = useState<BusinessCase[]>(businessCases);
  const [businessCaseTotal, setBusinessCaseTotal] = useState(businessCases.length);
  const [businessCaseOffset, setBusinessCaseOffset] = useState(0);
  const [businessCasePageLoading, setBusinessCasePageLoading] = useState(false);
  const [businessCasePageRefresh, setBusinessCasePageRefresh] = useState(0);
  const [isRefreshingWorkspace, setIsRefreshingWorkspace] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isMappingFormOpen, setIsMappingFormOpen] = useState(false);
  const [editingAttachmentId, setEditingAttachmentId] = useState("");
  const [activeWorkspace, setActiveWorkspace] = useState<"details" | "data" | "pipelines" | "models" | "services" | "reports" | null>(null);
  const bcModelNavigation = useVersionedResourceNavigation<ModelArtifact>();
  const bcReportNavigation = useVersionedResourceNavigation<ScoringReport>();
  const [bcDatasetHistory, setBcDatasetHistory] = useState<DataAsset | null>(null);
  const [bcPipelineHistory, setBcPipelineHistory] = useState<Pipeline | null>(null);
  const [bcRunDialog, setBcRunDialog] = useState<{
    sessionId: string;
    pipeline: Pipeline;
    version: PipelineVersion;
    inputs: PipelineRunInput[];
    models: PipelineRunModel[];
  } | null>(null);
  const [bcRunSelections, setBcRunSelections] = useState<Record<string, string>>({});
  const [bcRunModelSelections, setBcRunModelSelections] = useState<Record<string, string>>({});
  const [bcRunResults, setBcRunResults] = useState<Record<string, PipelineRun>>({});
  const [bcRunSubmittingSessions, setBcRunSubmittingSessions] = useState<Record<string, boolean>>({});
  const [bcSelectedRunDetails, setBcSelectedRunDetails] = useState<PipelineRun | null>(null);
  const [bcRunsPipelineId, setBcRunsPipelineId] = useState<string | null>(null);
  const [bcRunsRefreshKey, setBcRunsRefreshKey] = useState(0);
  const [bcDataPurposeFilter, setBcDataPurposeFilter] = useState("");
  const [bcDataPipelineFilter, setBcDataPipelineFilter] = useState("");
  const [bcDataRoleFilter, setBcDataRoleFilter] = useState("");
  const [bcUploadedOnly, setBcUploadedOnly] = useState(false);
  const [bcModelPurposeFilter, setBcModelPurposeFilter] = useState("");
  const [bcModelPipelineFilter, setBcModelPipelineFilter] = useState("");
  const [bcReportPurposeFilter, setBcReportPurposeFilter] = useState("");
  const [bcReportPipelineFilter, setBcReportPipelineFilter] = useState("");
  const [bcPipelineTypeFilter, setBcPipelineTypeFilter] = useState("");
  const [bcPipelineStatusFilter, setBcPipelineStatusFilter] = useState("");
  const [bcWorkspacePipelines, setBcWorkspacePipelines] = useState<Pipeline[]>([]);
  const [bcWorkspacePipelineTotal, setBcWorkspacePipelineTotal] = useState(0);
  const [bcWorkspacePipelineOffset, setBcWorkspacePipelineOffset] = useState(0);
  const [bcWorkspaceModels, setBcWorkspaceModels] = useState<ModelArtifact[]>([]);
  const [bcWorkspaceModelTotal, setBcWorkspaceModelTotal] = useState(0);
  const [bcWorkspaceModelOffset, setBcWorkspaceModelOffset] = useState(0);
  const [bcWorkspaceDeployments, setBcWorkspaceDeployments] = useState<Deployment[]>([]);
  const [bcWorkspaceDeploymentTotal, setBcWorkspaceDeploymentTotal] = useState(0);
  const [bcWorkspaceDeploymentOffset, setBcWorkspaceDeploymentOffset] = useState(0);
  const [bcWorkspaceReports, setBcWorkspaceReports] = useState<ScoringReport[]>([]);
  const [bcWorkspaceReportTotal, setBcWorkspaceReportTotal] = useState(0);
  const [bcWorkspaceReportOffset, setBcWorkspaceReportOffset] = useState(0);
  const [dependencyTarget, setDependencyTarget] = useState<{ referenceId: string; artifactType: string; title: string } | null>(null);

  const selectedBusinessCase = (
    businessCasePage.find((item) => item.id === selectedBusinessCaseId)
    ?? businessCases.find((item) => item.id === selectedBusinessCaseId)
    ?? selectedBusinessCaseSnapshot
  );
  const datasetById = useMemo(
    () => new Map(datasets.map((dataset) => [dataset.id, dataset])),
    [datasets]
  );
  const activeDatasetGroups = useMemo(
    () => datasetVersionGroups(datasets.filter((dataset) => dataset.status !== "deleted")),
    [datasets]
  );
  const latestDatasetByLogicalId = useMemo(
    () => new Map(activeDatasetGroups.map((group) => [group.logicalId, group.latest])),
    [activeDatasetGroups]
  );
  const availableDataAssets = useMemo(
    () => activeDatasetGroups.map((group) => group.latest),
    [activeDatasetGroups]
  );
  const attachedDataset = (dataAssetId: string) => {
    const attachedVersion = datasetById.get(dataAssetId);
    if (!attachedVersion) return undefined;
    return latestDatasetByLogicalId.get(attachedVersion.logical_id) ?? attachedVersion;
  };
  const activeAttachments = attachments;
  const selectedBusinessCasePipelines = useMemo(
    () => selectedBusinessCase
      ? pipelines.filter((pipeline) => pipeline.business_case_id === selectedBusinessCase.id)
      : [],
    [pipelines, selectedBusinessCase]
  );
  const businessCasePipelineTypes = useMemo(
    () => [...new Set([
      "data_preparation",
      "feature_engineering",
      "training",
      "automl",
      "batch_scoring",
      "monitoring",
      "custom",
      ...bcWorkspacePipelines.map((pipeline) => pipeline.type)
    ])]
      .sort((left, right) => left.localeCompare(right)),
    [bcWorkspacePipelines]
  );
  const businessCasePipelineStatuses = useMemo(
    () => [...new Set([
      "draft",
      "published",
      "deprecated",
      "archived",
      ...bcWorkspacePipelines.map((pipeline) => pipeline.status)
    ])]
      .sort((left, right) => left.localeCompare(right)),
    [bcWorkspacePipelines]
  );
  const visibleBusinessCasePipelines = bcWorkspacePipelines;
  const selectedBusinessCaseModels = bcWorkspaceModels;
  const selectedBusinessCaseReports = bcWorkspaceReports;
  const selectedBusinessCaseDeployments = bcWorkspaceDeployments;
  const visibleAttachments = activeAttachments;
  const visibleBusinessCaseModels = selectedBusinessCaseModels;
  const visibleBusinessCaseReports = selectedBusinessCaseReports;
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setBusinessCasePageLoading(true);
      api.pageBusinessCases({
        limit: 30,
        offset: businessCaseOffset,
        search: businessCaseSearch.trim()
      })
        .then((page) => {
          setBusinessCasePage(page.items);
          setBusinessCaseTotal(page.total);
          if (page.total > 0 && page.offset >= page.total) {
            setBusinessCaseOffset(Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit));
          }
        })
        .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load Business Cases"))
        .finally(() => setBusinessCasePageLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [businessCaseOffset, businessCasePageRefresh, businessCaseSearch, setNotice]);

  useEffect(() => {
    setBusinessCaseOffset(0);
  }, [businessCaseSearch]);

  useEffect(() => {
    const current = (
      businessCasePage.find((item) => item.id === selectedBusinessCaseId)
      ?? businessCases.find((item) => item.id === selectedBusinessCaseId)
    );
    if (current) setSelectedBusinessCaseSnapshot(current);
  }, [businessCasePage, businessCases, selectedBusinessCaseId]);

  useEffect(() => {
    setBcWorkspacePipelineOffset(0);
    setBcWorkspaceModelOffset(0);
    setBcWorkspaceDeploymentOffset(0);
    setBcWorkspaceReportOffset(0);
  }, [selectedBusinessCaseId]);

  useEffect(() => {
    if (!selectedBusinessCase || activeWorkspace !== "pipelines") return;
    api.pagePipelines({
      limit: 20,
      offset: bcWorkspacePipelineOffset,
      business_case_id: selectedBusinessCase.id,
      pipeline_type: bcPipelineTypeFilter,
      status: bcPipelineStatusFilter,
      include_deprecated: true
    })
      .then((page) => {
        setBcWorkspacePipelines(page.items);
        setBcWorkspacePipelineTotal(page.total);
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load Business Case pipelines"));
  }, [
    activeWorkspace,
    bcPipelineStatusFilter,
    bcPipelineTypeFilter,
    bcWorkspacePipelineOffset,
    pipelines,
    selectedBusinessCase,
    setNotice
  ]);

  useEffect(() => {
    setBcWorkspacePipelineOffset(0);
  }, [bcPipelineStatusFilter, bcPipelineTypeFilter]);

  useEffect(() => {
    if (!selectedBusinessCase || activeWorkspace !== "models") return;
    api.pageModels({
      limit: 20,
      offset: bcWorkspaceModelOffset,
      business_case_id: selectedBusinessCase.id,
      pipeline_id: bcModelPipelineFilter,
      pipeline_type: bcModelPurposeFilter
    })
      .then((page) => {
        setBcWorkspaceModels(page.items.map((family) => family.latest));
        setBcWorkspaceModelTotal(page.total);
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load Business Case models"));
  }, [
    activeWorkspace,
    bcModelPipelineFilter,
    bcModelPurposeFilter,
    bcWorkspaceModelOffset,
    models,
    selectedBusinessCase,
    setNotice
  ]);

  useEffect(() => {
    setBcWorkspaceModelOffset(0);
  }, [bcModelPipelineFilter, bcModelPurposeFilter]);

  useEffect(() => {
    if (!selectedBusinessCase || activeWorkspace !== "services") return;
    api.pageDeployments({
      limit: 12,
      offset: bcWorkspaceDeploymentOffset,
      business_case_id: selectedBusinessCase.id
    })
      .then((page) => {
        setBcWorkspaceDeployments(page.items);
        setBcWorkspaceDeploymentTotal(page.total);
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load Business Case services"));
  }, [
    activeWorkspace,
    bcWorkspaceDeploymentOffset,
    deployments,
    selectedBusinessCase,
    setNotice
  ]);

  useEffect(() => {
    if (!selectedBusinessCase || activeWorkspace !== "reports") return;
    api.pageScoringReports({
      limit: 20,
      offset: bcWorkspaceReportOffset,
      business_case_id: selectedBusinessCase.id,
      pipeline_id: bcReportPipelineFilter,
      pipeline_type: bcReportPurposeFilter
    })
      .then((page) => {
        setBcWorkspaceReports(page.items.map((family) => family.latest));
        setBcWorkspaceReportTotal(page.total);
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load Business Case reports"));
  }, [
    activeWorkspace,
    bcReportPipelineFilter,
    bcReportPurposeFilter,
    bcWorkspaceReportOffset,
    scoringReports,
    selectedBusinessCase,
    setNotice
  ]);

  useEffect(() => {
    setBcWorkspaceReportOffset(0);
  }, [bcReportPipelineFilter, bcReportPurposeFilter]);

  useEffect(() => {
    setAttachmentOffset(0);
  }, [
    attachmentSearch,
    bcDataPipelineFilter,
    bcDataPurposeFilter,
    bcDataRoleFilter,
    bcUploadedOnly,
    selectedBusinessCaseId
  ]);

  useEffect(() => {
    if (!selectedBusinessCase || activeWorkspace !== "data") return;
    const timer = window.setTimeout(() => {
      api.pageBusinessCaseDataAttachments(selectedBusinessCase.id, {
        limit: 20,
        offset: attachmentOffset,
        search: attachmentSearch.trim(),
        role: bcDataRoleFilter,
        pipeline_id: bcDataPipelineFilter,
        pipeline_type: bcDataPurposeFilter,
        uploaded_only: bcUploadedOnly
      })
        .then((page) => {
          setAttachments(page.items);
          setAttachmentTotal(page.total);
        })
        .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load BC data attachments"));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [
    activeWorkspace,
    attachmentOffset,
    attachmentRefreshKey,
    attachmentSearch,
    bcDataPipelineFilter,
    bcDataPurposeFilter,
    bcDataRoleFilter,
    bcUploadedOnly,
    selectedBusinessCase,
    setNotice
  ]);

  useEffect(() => {
    if (!selectedBusinessCase || activeWorkspace !== "data") return;
    api.pageBusinessCaseDataAttachments(selectedBusinessCase.id, {
      limit: 20,
      offset: deletedAttachmentOffset,
      deleted_only: true
    })
      .then((page) => {
        setDeletedAttachments(page.items);
        setDeletedAttachmentTotal(page.total);
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load deleted BC data attachments"));
  }, [
    activeWorkspace,
    attachmentRefreshKey,
    deletedAttachmentOffset,
    selectedBusinessCase,
    setNotice
  ]);

  useEffect(() => {
    setBcDataPurposeFilter("");
    setBcDataPipelineFilter("");
    setBcUploadedOnly(false);
    setBcModelPurposeFilter("");
    setBcModelPipelineFilter("");
    setBcReportPurposeFilter("");
    setBcReportPipelineFilter("");
    setBcPipelineTypeFilter("");
    setBcPipelineStatusFilter("");
    if (!selectedBusinessCase) {
      setAttachments([]);
      setAttachmentTotal(0);
      setDeletedAttachments([]);
      setDeletedAttachmentTotal(0);
      return;
    }
    resetBusinessCaseEditForm(selectedBusinessCase);
    resetDataMappingForm();
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
    setSelectedBusinessCaseSnapshot(created);
    setSelectedBusinessCaseId(created.id);
    setName("");
    setDescription("");
    setTargetColumn("");
    setBusinessGoal("");
    setSuccessCriteria("");
    setIsCreateOpen(false);
    setActiveWorkspace("details");
    await onRefresh();
    setBusinessCasePageRefresh((value) => value + 1);
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
      setAttachmentRefreshKey((value) => value + 1);
      return;
    }
    const dataAsset = (
      availableDataAssets.find((item) => item.id === selectedDataAssetId)
      ?? selectedDataAssetSnapshot
      ?? availableDataAssets[0]
    );
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
    setAttachmentRefreshKey((value) => value + 1);
  }

  function startAddingAttachment() {
    resetDataMappingForm();
    setIsMappingFormOpen(true);
  }

  function startEditingAttachment(attachment: BusinessCaseDataAttachment) {
    setSelectedDataAssetId(attachment.data_asset_id);
    setSelectedDataAssetSnapshot(attachedDataset(attachment.data_asset_id));
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
    setSelectedDataAssetSnapshot(undefined);
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
    const label = (
      attachment.data_asset_name
      || attachedDataset(attachment.data_asset_id)?.name
      || attachment.data_asset_id
    );
    const confirmed = window.confirm(`Delete mapping for ${label}? The dataset itself will not be deleted.`);
    if (!confirmed) {
      return;
    }
    await api.deleteBusinessCaseDataAttachment(selectedBusinessCase.id, attachment.id);
    if (editingAttachmentId === attachment.id) {
      resetDataMappingForm();
    }
    setNotice(`Deleted mapping for ${label}`);
    setAttachmentRefreshKey((value) => value + 1);
  }

  async function openBcPipelineRun(pipeline: Pipeline) {
    try {
      const versionPage = await api.pagePipelineVersions(pipeline.id, {
        limit: 1,
        offset: 0,
        status: "published"
      });
      const published = versionPage.items[0];
      if (!published) {
        setNotice("This pipeline has no published version");
        return;
      }
      const normalized = canonicalizeWorkflowDatasetIds(
        normalizeWorkflowDefinition(published.definition),
        datasets
      );
      const inputs = resolvePipelineRunInputs(normalized, datasets);
      const runModels = resolvePipelineRunModels(normalized, models);
      setBcRunSelections({});
      setBcRunModelSelections(Object.fromEntries(runModels.map((model) => [model.key, model.versions[0]?.id ?? ""])));
      setBcRunResults((current) => Object.fromEntries(
        Object.entries(current).filter(([, run]) => ["queued", "running"].includes(run.status))
      ));
      setBcRunDialog({
        sessionId: crypto.randomUUID(),
        pipeline,
        version: published,
        inputs,
        models: runModels
      });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not prepare pipeline run");
    }
  }

  async function submitBcPipelineRun(event: FormEvent) {
    event.preventDefault();
    if (!bcRunDialog) return;
    const dialog = bcRunDialog;
    const sessionId = dialog.sessionId;
    const missing = dialog.inputs.find(
      (input) => requiresRuntimeDatasetSelection(input.policy)
        && !bcRunSelections[input.key]
    );
    if (missing) {
      setNotice(`Select a version for ${missing.name}`);
      return;
    }
    setBcRunSubmittingSessions((current) => ({ ...current, [sessionId]: true }));
    try {
      let run = await api.runPipeline(dialog.pipeline.id, {
        pipeline_version_id: dialog.version.id,
        trigger_type: "manual",
        is_dry_run: false,
        runtime_parameters: {},
        input_versions: bcRunSelections,
        model_versions: bcRunModelSelections
      });
      setBcRunResults((current) => ({ ...current, [sessionId]: run }));
      setNotice(`Pipeline run ${shortId(run.id)} queued`);
      while (["queued", "running"].includes(run.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        const runStatus = await api.getPipelineRunStatus(dialog.pipeline.id, run.id);
        run = { ...run, ...runStatus };
        if (!["queued", "running"].includes(run.status)) {
          run = await api.getPipelineRun(dialog.pipeline.id, run.id);
        }
        setBcRunResults((current) => ({ ...current, [sessionId]: run }));
      }
      await onRefresh();
      setBusinessCasePageRefresh((value) => value + 1);
      setNotice(
        run.status === "succeeded"
          ? `Pipeline run ${shortId(run.id)} completed`
          : `Pipeline run ${shortId(run.id)} failed: ${run.error_message || "unknown error"}`
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not start pipeline run");
    } finally {
      setBcRunSubmittingSessions((current) => ({ ...current, [sessionId]: false }));
    }
  }

  const currentBcRunResult = bcRunDialog ? bcRunResults[bcRunDialog.sessionId] ?? null : null;
  const currentBcRunSubmitting = bcRunDialog
    ? Boolean(bcRunSubmittingSessions[bcRunDialog.sessionId])
    : false;

  async function handleWorkspaceRefresh() {
    setIsRefreshingWorkspace(true);
    setNotice("Refreshing workspace data…");
    try {
      await onRefresh();
      setBusinessCasePageRefresh((value) => value + 1);
      setNotice("Workspace data refreshed");
    } catch {
      // refreshWorkspace already exposes the actionable API error in the notice bar.
    } finally {
      setIsRefreshingWorkspace(false);
    }
  }

  return (
    <section className="business-case-screen">
      <div className="panel business-case-catalog">
        <div className="catalog-toolbar">
          <div>
            <h2>Business cases</h2>
            <p>{businessCaseTotal} cases</p>
          </div>
          <div className="catalog-toolbar-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => void handleWorkspaceRefresh()}
              disabled={isRefreshingWorkspace}
              aria-label="Refresh workspace data"
              title="Reload Business Cases and related workspace resources"
            >
              <RotateCcw className={isRefreshingWorkspace ? "run-spinner" : undefined} size={16} />
              {isRefreshingWorkspace ? "Refreshing…" : "Refresh"}
            </button>
            <button className="primary-button" type="button" onClick={() => setIsCreateOpen(true)}>
              <Plus size={16} />
              Create BC
            </button>
          </div>
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
          {businessCasePage.map((item) => (
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
                <button className="secondary-button compact-button" type="button" onClick={() => {
                  setSelectedBusinessCaseId(item.id);
                  setBcRunsPipelineId("all");
                }}>
                  <History size={14} /> Runs
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
                    setActiveWorkspace("services");
                  }}
                >
                  <Rocket size={14} />
                  Services
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
          {!businessCasePageLoading && businessCasePage.length === 0 && <div className="catalog-empty">No business cases match this search.</div>}
        </div>
        <PaginationControls
          total={businessCaseTotal}
          limit={30}
          offset={businessCaseOffset}
          onOffsetChange={setBusinessCaseOffset}
          disabled={businessCasePageLoading}
          label="business cases"
        />
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
              <button className="secondary-button compact-button" type="button" onClick={() => setBcRunsPipelineId("all")}>
                <History size={14} /> Runs
              </button>
              <button className={`secondary-button compact-button${activeWorkspace === "models" ? " active" : ""}`} type="button" onClick={() => setActiveWorkspace("models")}>
                <Brain size={14} />
                Models
              </button>
              <button className={`secondary-button compact-button${activeWorkspace === "services" ? " active" : ""}`} type="button" onClick={() => setActiveWorkspace("services")}>
                <Rocket size={14} />
                Services
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
                  <p>{attachmentTotal} active mappings in this filtered catalog</p>
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
              <label className="search-field">
                <Search size={16} />
                <input
                  aria-label="Search mapped data"
                  placeholder="Search dataset, ID, role or context"
                  value={attachmentSearch}
                  onChange={(event) => setAttachmentSearch(event.target.value)}
                />
              </label>
              <ArtifactFilters
                pipelines={selectedBusinessCasePipelines}
                purpose={bcDataPurposeFilter}
                pipelineId={bcDataPipelineFilter}
                onPurposeChange={setBcDataPurposeFilter}
                onPipelineChange={setBcDataPipelineFilter}
                businessCaseId={selectedBusinessCase.id}
                role={bcDataRoleFilter}
                roleOptions={businessCaseDataRoleOptions}
                onRoleChange={setBcDataRoleFilter}
                uploadedOnly={bcUploadedOnly}
                onUploadedOnlyChange={(value) => {
                  setBcUploadedOnly(value);
                  if (value) {
                    setBcDataPurposeFilter("");
                    setBcDataPipelineFilter("");
                  }
                }}
              />
              <div className="asset-list">
                {visibleAttachments.map((item) => {
                  const assetName = (
                    item.data_asset_name
                    || attachedDataset(item.data_asset_id)?.name
                    || item.data_asset_id
                  );
                  return (
                    <div className={`asset-row${editingAttachmentId === item.id ? " selected" : ""}`} key={item.id}>
                      <div>
                        <strong>{assetName}</strong>
                        <span>{item.data_asset_kind} / key: {item.primary_key_column || "not set"} / target: {item.target_column || "not set"} / {item.context_note || "no note"}</span>
                      </div>
                      <div className="asset-actions">
                        <em>{item.role}</em>
                        <button className="secondary-button compact-button" type="button"
                          onClick={() => void api.getDataset(item.data_asset_id).then(async (dataset) => {
                            setBcDatasetHistory(dataset);
                          })}>
                          <History size={14} /> Versions
                        </button>
                        <button className="secondary-button compact-button" type="button"
                          onClick={() => setDependencyTarget({ referenceId: item.data_asset_id, artifactType: "dataset", title: assetName })}>
                          <GitBranch size={14} /> Dependencies
                        </button>
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
                {!visibleAttachments.length && (
                  <div className="empty-state">
                    {attachmentTotal ? "No mapped datasets match these filters." : "No data mapped to this business case yet"}
                  </div>
                )}
              </div>
              <PaginationControls
                total={attachmentTotal}
                limit={20}
                offset={attachmentOffset}
                onOffsetChange={setAttachmentOffset}
                label="Business Case data mappings"
              />
            </div>

            {isMappingFormOpen && (
              <div className="modal-backdrop" role="presentation"
                onMouseDown={(event) => event.target === event.currentTarget && resetDataMappingForm()}>
              <form className="modal-dialog form-panel bc-mapping-form" onSubmit={attachData}
                onMouseDown={(event) => event.stopPropagation()}>
                <div className="modal-header">
                  <div>
                    <span className="builder-kicker">Business Case data</span>
                    <h2>{editingAttachmentId ? "Edit data mapping" : "Add data mapping"}</h2>
                    <p>
                      {editingAttachmentId
                        ? "Update the role and context of this mapping."
                        : "Connect a dataset or Data View to this business case."}
                    </p>
                  </div>
                  <button className="icon-button" type="button" onClick={resetDataMappingForm}
                    aria-label="Close data mapping"><X size={17} /></button>
                </div>
                <label>
                  Dataset/Data View
                  <PagedCatalogSelect
                    value={selectedDataAssetId}
                    onChange={(value, item) => {
                      setSelectedDataAssetId(value);
                      setSelectedDataAssetSnapshot(item);
                    }}
                    loadPage={(query) => api.pageDatasets({
                      ...query,
                      families: true,
                      include_deleted: false,
                      summary: true
                    })}
                    getId={(item) => item.id}
                    getLabel={(item) => `${item.name} · v${item.version_number}`}
                    selectedItem={selectedDataAssetSnapshot}
                    emptyLabel="Choose dataset or Data View"
                    searchPlaceholder="Search datasets and Data Views"
                    disabled={Boolean(editingAttachmentId)}
                  />
                </label>
                <label>
                  Role
                  <select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>
                    {businessCaseDataRoleOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
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
              </div>
            )}

            {deletedAttachmentTotal > 0 && (
              <details className="panel editor-details deleted-assets-panel">
                <summary>Deleted BC mappings <span>{deletedAttachmentTotal}</span></summary>
                <AssetList title="" assets={deletedAttachments.map((item) => ({
                  id: item.id,
                  name: item.data_asset_name || attachedDataset(item.data_asset_id)?.name || item.data_asset_id,
                  meta: `${item.data_asset_kind} / key: ${item.primary_key_column || "not set"} / ${item.context_note || "no note"}`,
                  status: item.role
                }))} />
                <PaginationControls
                  total={deletedAttachmentTotal}
                  limit={20}
                  offset={deletedAttachmentOffset}
                  onOffsetChange={setDeletedAttachmentOffset}
                  label="deleted Business Case mappings"
                />
              </details>
            )}
          </>
        )}

        {selectedBusinessCase && activeWorkspace === "pipelines" && (
          <div className="panel">
            <div className="panel-header">
              <div><h2>Mapped pipelines</h2><p>{bcWorkspacePipelineTotal} workflows in this filtered catalog.</p></div>
              <button className="secondary-button compact-button" type="button"
                onClick={() => setBcRunsPipelineId("all")}>
                <History size={15} /> Runs
              </button>
            </div>
            <div className="pipeline-catalog-filters" aria-label="Business Case pipeline filters">
              <label>
                <span><Filter size={14} /> Pipeline type</span>
                <select
                  aria-label="Filter Business Case pipelines by type"
                  value={bcPipelineTypeFilter}
                  onChange={(event) => setBcPipelineTypeFilter(event.target.value)}
                >
                  <option value="">All pipeline types</option>
                  {businessCasePipelineTypes.map((type) => (
                    <option key={type} value={type}>{type.replaceAll("_", " ")}</option>
                  ))}
                </select>
              </label>
              <label>
                <span><Filter size={14} /> Status</span>
                <select
                  aria-label="Filter Business Case pipelines by status"
                  value={bcPipelineStatusFilter}
                  onChange={(event) => setBcPipelineStatusFilter(event.target.value)}
                >
                  <option value="">All statuses</option>
                  {businessCasePipelineStatuses.map((status) => (
                    <option key={status} value={status}>{status.replaceAll("_", " ")}</option>
                  ))}
                </select>
              </label>
              <span className="pipeline-filter-summary">
                {bcWorkspacePipelineTotal} workflows
              </span>
            </div>
          <AssetList title="" assets={visibleBusinessCasePipelines.map((item) => ({
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
                label: "Runs",
                icon: "versions",
                onClick: () => setBcRunsPipelineId(item.id)
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
              },
              {
                label: "Dependencies",
                icon: "dependencies",
                onClick: () => setDependencyTarget({ referenceId: item.id, artifactType: "pipeline", title: item.name })
              }
            ]
          }))} />
          <PaginationControls
            total={bcWorkspacePipelineTotal}
            limit={20}
            offset={bcWorkspacePipelineOffset}
            onOffsetChange={setBcWorkspacePipelineOffset}
            label="Business Case pipelines"
          />
          </div>
        )}
        {selectedBusinessCase && activeWorkspace === "models" && (
          <div className="panel">
            <div className="panel-header">
              <div><h2>Models</h2><p>{bcWorkspaceModelTotal} model families in this filtered catalog</p></div>
              <button className="secondary-button compact-button" type="button"
                onClick={() => onOpenModels(selectedBusinessCase.id)}>Open model registry</button>
            </div>
            <ArtifactFilters
              pipelines={selectedBusinessCasePipelines}
              purpose={bcModelPurposeFilter}
              pipelineId={bcModelPipelineFilter}
              onPurposeChange={setBcModelPurposeFilter}
              onPipelineChange={setBcModelPipelineFilter}
              businessCaseId={selectedBusinessCase.id}
            />
            <AssetList title="" assets={visibleBusinessCaseModels.map((item) => ({
              id: item.id,
              name: `${item.name} · ${item.version}`,
              meta: `${item.algorithm} · ${item.problem_type} · ${businessCaseName(businessCases, item.business_case_id)}`,
              status: item.stage,
              actions: [
                { label: "Versions", icon: "versions", onClick: () => bcModelNavigation.openHistory(item) },
                { label: "View", icon: "view", onClick: () => void api.getModel(item.id).then(bcModelNavigation.openDirect) },
                { label: "Dependencies", icon: "dependencies", onClick: () => setDependencyTarget({ referenceId: item.id, artifactType: "model_version", title: item.name }) }
              ]
            }))} />
            <PaginationControls
              total={bcWorkspaceModelTotal}
              limit={20}
              offset={bcWorkspaceModelOffset}
              onOffsetChange={setBcWorkspaceModelOffset}
              label="Business Case model families"
            />
          </div>
        )}
        {selectedBusinessCase && activeWorkspace === "services" && (
          <div className="panel bc-services-panel">
            <div className="panel-header">
              <div>
                <h2>Model services</h2>
                <p>{bcWorkspaceDeploymentTotal} stable {bcWorkspaceDeploymentTotal === 1 ? "endpoint" : "endpoints"} in this business case</p>
              </div>
            </div>
            {selectedBusinessCaseDeployments.length === 0 ? (
              <div className="empty-state">No model services have been created for this business case.</div>
            ) : (
              <div className="bc-service-grid">
                {selectedBusinessCaseDeployments.map((deployment) => {
                  const assignments = deployment.active_revision?.assignments ?? [];
                  return (
                    <article className="bc-service-card" key={deployment.id}>
                      <div className="bc-service-card-header">
                        <div>
                          <span className={`pipeline-status ${deployment.status}`}>{deployment.status}</span>
                          <h3>{deployment.name}</h3>
                          <code>{deployment.endpoint_url ?? "Endpoint unavailable"}</code>
                        </div>
                        <button className="secondary-button compact-button" type="button" onClick={() => onOpenServing(deployment.id)}>
                          <Rocket size={14} /> Open service
                        </button>
                      </div>
                      <div className="bc-service-meta">
                        <span>Active revision <strong>v{deployment.active_revision?.version_number ?? "—"}</strong></span>
                        <span>Retention <strong>{deployment.retention_days} days</strong></span>
                        <span>Updated <strong>{formatDateTime(deployment.updated_at)}</strong></span>
                      </div>
                      <div className="bc-service-assignments">
                        {assignments.map((assignment) => {
                          const assignedModel = models.find((item) => item.id === assignment.model_id);
                          return (
                            <div key={`${deployment.id}-${assignment.model_id}`}>
                              <span className="bc-service-role">{assignment.role}</span>
                              <strong>{assignedModel ? `${assignedModel.name} · ${assignedModel.version}` : assignment.model_id}</strong>
                              <small>model stage: {assignedModel?.stage ?? "unavailable"}</small>
                            </div>
                          );
                        })}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
            <PaginationControls
              total={bcWorkspaceDeploymentTotal}
              limit={12}
              offset={bcWorkspaceDeploymentOffset}
              onOffsetChange={setBcWorkspaceDeploymentOffset}
              label="Business Case model services"
            />
          </div>
        )}
        {selectedBusinessCase && activeWorkspace === "reports" && (
          <div className="panel">
            <div className="panel-header">
              <div><h2>Scoring reports</h2><p>{bcWorkspaceReportTotal} report families in this filtered catalog</p></div>
              <button className="secondary-button compact-button" type="button"
                onClick={() => onOpenScoringReports(selectedBusinessCase.id)}>Open report registry</button>
            </div>
            <ArtifactFilters
              pipelines={selectedBusinessCasePipelines}
              purpose={bcReportPurposeFilter}
              pipelineId={bcReportPipelineFilter}
              onPurposeChange={setBcReportPurposeFilter}
              onPipelineChange={setBcReportPipelineFilter}
              businessCaseId={selectedBusinessCase.id}
            />
            <AssetList title="" assets={visibleBusinessCaseReports.map((item) => ({
              id: item.id,
              name: `${item.name} · v${item.version_number}`,
              meta: `${pipelineName(pipelines, item.pipeline_id)} · ${item.problem_type} · ${item.evaluated_row_count.toLocaleString()} rows`,
              status: "ready",
              actions: [
                { label: "Versions", icon: "versions", onClick: () => bcReportNavigation.openHistory(item) },
                { label: "View", icon: "view", onClick: () => void api.getScoringReport(item.id).then(bcReportNavigation.openDirect) },
                { label: "Dependencies", icon: "dependencies", onClick: () => setDependencyTarget({ referenceId: item.id, artifactType: "report", title: item.name }) }
              ]
            }))} />
            <PaginationControls
              total={bcWorkspaceReportTotal}
              limit={20}
              offset={bcWorkspaceReportOffset}
              onOffsetChange={setBcWorkspaceReportOffset}
              label="Business Case report families"
            />
          </div>
        )}
      </div>
      )}
      {bcModelNavigation.selected && (
        <DeferredPanel>
          <ModelDetailsDialog
            model={bcModelNavigation.selected}
            businessCaseName={businessCaseName(businessCases, bcModelNavigation.selected.business_case_id)}
            pipelineName={pipelineName(pipelines, bcModelNavigation.selected.pipeline_id)}
            onOpenDataset={onOpenDataset}
            onClose={bcModelNavigation.closeAll}
            onBack={bcModelNavigation.hasBack ? bcModelNavigation.back : undefined}
          />
        </DeferredPanel>
      )}
      {bcReportNavigation.selected && (
        <DeferredPanel>
          <ScoringReportDialog
            report={bcReportNavigation.selected}
            onOpenDataset={onOpenDataset}
            onClose={bcReportNavigation.closeAll}
            onBack={bcReportNavigation.hasBack ? bcReportNavigation.back : undefined}
          />
        </DeferredPanel>
      )}
      {bcDatasetHistory && (
        <DatasetVersionHistoryDialog
          dataset={bcDatasetHistory}
          onClose={() => {
            setBcDatasetHistory(null);
          }}
          onOpen={(datasetId) => {
            setBcDatasetHistory(null);
            onOpenDataset(datasetId);
          }}
        />
      )}
      {dependencyTarget && (
        <ArtifactDependenciesDialog
          {...dependencyTarget}
          onClose={() => setDependencyTarget(null)}
          onOpenDataset={onOpenDataset}
        />
      )}
      {bcModelNavigation.showHistory && bcModelNavigation.history && (
        <DeferredPanel>
          <ModelVersionHistoryDialog
            model={bcModelNavigation.history}
            businessCaseName={businessCaseName(businessCases, bcModelNavigation.history.business_case_id)}
            pipelineName={pipelineName(pipelines, bcModelNavigation.history.pipeline_id)}
            onClose={bcModelNavigation.closeHistory}
            onView={async (version) => {
              const fullModel = await api.getModel(version.id);
              bcModelNavigation.openVersion(fullModel);
            }}
          />
        </DeferredPanel>
      )}
      {bcReportNavigation.showHistory && bcReportNavigation.history && (
        <DeferredPanel>
          <ScoringReportHistoryDialog
            report={bcReportNavigation.history}
            onClose={bcReportNavigation.closeHistory}
            onView={async (version) => {
              const fullReport = await api.getScoringReport(version.id);
              bcReportNavigation.openVersion(fullReport);
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
      {bcRunsPipelineId && selectedBusinessCase && (
        <PipelineRunHistoryDialog
          pipelines={selectedBusinessCasePipelines}
          businessCases={businessCases}
          refreshKey={bcRunsRefreshKey}
          includeDryRuns={false}
          initialPipelineId={bcRunsPipelineId}
          title={`${selectedBusinessCase.name} runs`}
          description="Official pipeline runs in this business case. Dry-runs remain available in Jobs and the pipeline editor."
          onClose={() => setBcRunsPipelineId(null)}
          onDetails={setBcSelectedRunDetails}
          onExamineDataset={onOpenDataset}
        />
      )}
      {bcRunDialog && (
        <div className="modal-backdrop" role="presentation"
          onMouseDown={(event) => event.target === event.currentTarget && setBcRunDialog(null)}>
          <form className="modal-dialog form-panel" onSubmit={submitBcPipelineRun}>
            <div className="modal-header">
              <div><span className="builder-kicker">Business Case manual run</span>
                <h2>{bcRunDialog.pipeline.name}</h2></div>
              <button className="icon-button" type="button"
                onClick={() => setBcRunDialog(null)} aria-label="Close run dialog"><X size={17} /></button>
            </div>
            {bcRunDialog.inputs.map((input) => (
              <PipelineRunDatasetInputSelector
                key={input.key}
                input={input}
                businessCaseId={bcRunDialog.pipeline.business_case_id}
                value={bcRunSelections[input.key] ?? ""}
                onChange={(value) => setBcRunSelections((current) => ({
                  ...current,
                  [input.key]: value
                }))}
              />
            ))}
            {bcRunDialog.models.map((model) => (
              <PipelineRunModelSelector
                key={model.key}
                model={model}
                value={bcRunModelSelections[model.key] ?? ""}
                onChange={(value) => setBcRunModelSelections((current) => ({
                  ...current,
                  [model.key]: value
                }))}
              />
            ))}
            {currentBcRunResult && (
              <div className={`catalog-run-monitor ${currentBcRunResult.status}`}>
                <div><strong>{currentBcRunResult.status}</strong>
                  <span>Run {shortId(currentBcRunResult.id)} · {currentBcRunResult.processed_row_count ?? 0} processed rows</span></div>
              </div>
            )}
            {currentBcRunResult && (
              <button className="secondary-button" type="button" onClick={() => setBcSelectedRunDetails(currentBcRunResult)}>
                <History size={15} /> Logs, details and cancel
              </button>
            )}
            <div className="modal-actions">
              <button className="secondary-button" type="button"
                onClick={() => setBcRunDialog(null)}>{currentBcRunSubmitting ? "Run in background" : "Close"}</button>
              {!currentBcRunResult && (
                <button className="primary-button" type="submit" disabled={currentBcRunSubmitting}>
                  <Play size={15} /> {currentBcRunSubmitting ? "Starting…" : "Run published version"}
                </button>
              )}
            </div>
          </form>
        </div>
      )}
      {bcSelectedRunDetails && (
        <PipelineRunDetailsDialog
          run={bcSelectedRunDetails}
          onBack={bcRunsPipelineId ? () => setBcSelectedRunDetails(null) : undefined}
          onClose={() => {
            setBcSelectedRunDetails(null);
            setBcRunsPipelineId(null);
          }}
          onChanged={async () => {
            setBcRunsRefreshKey((current) => current + 1);
            await onRefresh();
          }}
        />
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
