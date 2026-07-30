import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Filter,
  History,
  Pencil,
  Play,
  Plus,
  Search,
  Save,
  Trash2,
  X
} from "lucide-react";
import type { FormEvent } from "react";
import { lazy, useEffect, useMemo, useRef, useState } from "react";

import { api, temporaryPipelineOutputId } from "../api/client";
import type {
  BusinessCase,
  BusinessCaseDataAttachment,
  DataAsset,
  ModelArtifact,
  Pipeline,
  PipelineRun,
  PipelineStepRun,
  PipelineVersion
} from "../api/client";
import { AssetList } from "../components/AssetList";
import { DeferredPanel } from "../components/DeferredPanel";
import { PaginationControls } from "../components/PaginationControls";
import { PagedCatalogSelect } from "../components/PagedCatalogSelect";
import {
  AnalysisPanel,
  latestLogicalDatasetAliases,
  type DescriptiveProfileCacheEntry
} from "../data/DataWorkspacePanels";
import {
  canonicalizeWorkflowDatasetIds,
  emptyWorkflowDefinition,
  normalizeWorkflowDefinition,
  validateWorkflowConfiguration,
  workflowTemplateDefinition
} from "../pipelines/workflowContract";
import type { PipelineTemplate, WorkflowDefinition } from "../pipelines/workflowContract";
import {
  browsableDryRunOutputs,
  DryRunPreview,
  PipelineVersionHistoryDialog,
  PipelineRunDetailsDialog,
  PipelineRunHistoryDialog
} from "../pipelines/PipelineRunDialogs";
import {
  clearPipelineWorkingDraft,
  readPipelineWorkingDraft,
  writePipelineWorkingDraft
} from "../pipelines/pipelineDraftStorage";
import { requiresRuntimeDatasetSelection } from "../pipelines/dataContractOptions";
import {
  resolvePipelineRunInputs,
  resolvePipelineRunModels,
  type PipelineRunInput,
  type PipelineRunModel
} from "../pipelines/pipelineRunInputs";
import {
  PipelineRunDatasetInputSelector,
  PipelineRunModelSelector
} from "../pipelines/PipelineRunSelectors";
import { businessCaseName } from "../shared/catalogLabels";
import { formatDateTime, shortId } from "../shared/formatters";


const WorkflowEditor = lazy(() =>
  import("../pipelines/WorkflowEditor").then((module) => ({ default: module.WorkflowEditor }))
);

export function PipelinesPanel({
  businessCases,
  datasets,
  pipelines,
  models,
  openRequest,
  onOpenRequestConsumed,
  onRefresh,
  onExamineDataset,
  setNotice
}: {
  businessCases: BusinessCase[];
  datasets: DataAsset[];
  pipelines: Pipeline[];
  models: ModelArtifact[];
  openRequest: { pipelineId: string; requestId: number } | null;
  onOpenRequestConsumed: () => void;
  onRefresh: () => Promise<void>;
  onExamineDataset: (datasetId: string) => void;
  setNotice: (message: string) => void;
}) {
  const [businessCaseId, setBusinessCaseId] = useState("");
  const [createBusinessCase, setCreateBusinessCase] = useState<BusinessCase | undefined>();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [pipelineType, setPipelineType] = useState("custom");
  const [pipelineTemplate, setPipelineTemplate] = useState<PipelineTemplate>("custom");
  const [createPipelineError, setCreatePipelineError] = useState("");
  const [isCreatingPipeline, setIsCreatingPipeline] = useState(false);
  const [catalogBusinessCaseFilter, setCatalogBusinessCaseFilter] = useState("");
  const [catalogPipelineTypeFilter, setCatalogPipelineTypeFilter] = useState("");
  const [catalogPipelineSearch, setCatalogPipelineSearch] = useState("");
  const [activePipelines, setActivePipelines] = useState<Pipeline[]>([]);
  const [activePipelineTotal, setActivePipelineTotal] = useState(0);
  const [activePipelineOffset, setActivePipelineOffset] = useState(0);
  const [deprecatedPipelines, setDeprecatedPipelines] = useState<Pipeline[]>([]);
  const [deprecatedPipelineTotal, setDeprecatedPipelineTotal] = useState(0);
  const [deprecatedPipelineOffset, setDeprecatedPipelineOffset] = useState(0);
  const [pipelineCatalogLoading, setPipelineCatalogLoading] = useState(false);
  const [selectedPipelineId, setSelectedPipelineId] = useState("");
  const [selectedPipelineSnapshot, setSelectedPipelineSnapshot] = useState<Pipeline | undefined>();
  const [isCreatePipelineOpen, setIsCreatePipelineOpen] = useState(false);
  const [copyPipelineTarget, setCopyPipelineTarget] = useState<Pipeline | null>(null);
  const [copyPipelineName, setCopyPipelineName] = useState("");
  const [deletePipelineTarget, setDeletePipelineTarget] = useState<Pipeline | null>(null);
  const [isPipelineMutationSubmitting, setIsPipelineMutationSubmitting] = useState(false);
  const [isPipelineEditorOpen, setIsPipelineEditorOpen] = useState(false);
  const [catalogRunDialog, setCatalogRunDialog] = useState<{
    pipeline: Pipeline;
    version: PipelineVersion;
    inputs: PipelineRunInput[];
    models: PipelineRunModel[];
  } | null>(null);
  const [catalogRunSelections, setCatalogRunSelections] = useState<Record<string, string>>({});
  const [catalogRunModelSelections, setCatalogRunModelSelections] = useState<Record<string, string>>({});
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
  const [draftValidationError, setDraftValidationError] = useState("");
  const [versions, setVersions] = useState<PipelineVersion[]>([]);
  const [versionTotal, setVersionTotal] = useState(0);
  const [hydratedPipelineId, setHydratedPipelineId] = useState("");
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [activeStepRuns, setActiveStepRuns] = useState<PipelineStepRun[]>([]);
  const [selectedRunDetails, setSelectedRunDetails] = useState<PipelineRun | null>(null);
  const [activeRunMonitor, setActiveRunMonitor] = useState<PipelineRun | null>(null);
  const [isRunHistoryOpen, setIsRunHistoryOpen] = useState(false);
  const [runHistoryPipelineId, setRunHistoryPipelineId] = useState("all");
  const [versionHistoryPipeline, setVersionHistoryPipeline] = useState<Pipeline | null>(null);
  const [runHistoryRefreshKey, setRunHistoryRefreshKey] = useState(0);
  const [pipelineDataAttachments, setPipelineDataAttachments] = useState<BusinessCaseDataAttachment[]>([]);
  const catalogPipelineTypes = useMemo(
    () => ["automl", "batch_scoring", "custom", "data_preparation", "feature_engineering", "monitoring", "training"],
    []
  );
  const filteredActivePipelines = activePipelines;
  const filteredDeprecatedPipelines = deprecatedPipelines;
  const hasCatalogFilters = Boolean(
    catalogBusinessCaseFilter
    || catalogPipelineTypeFilter
    || catalogPipelineSearch
  );
  // Do not fall back to another pipeline while a freshly created/copied item is
  // being added to the refreshed catalog. Rendering that fallback with the new
  // selected ID can persist the previous workflow under the new pipeline.
  const selectedPipeline = activePipelines.find((item) => item.id === selectedPipelineId)
    ?? pipelines.find((item) => item.id === selectedPipelineId)
    ?? selectedPipelineSnapshot
    ?? (!selectedPipelineId ? activePipelines[0] : undefined);
  const selectedPipelineIdValue = selectedPipeline?.id ?? "";
  const selectedBusinessCaseIdValue = selectedPipeline?.business_case_id ?? "";
  const workflowValidationIssues = useMemo(
    () => validateWorkflowConfiguration(workflowDefinition),
    [workflowDefinition]
  );

  useEffect(() => {
    if (!businessCaseId && businessCases[0]) {
      setBusinessCaseId(businessCases[0].id);
    }
  }, [businessCaseId, businessCases]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPipelineCatalogLoading(true);
      const common = {
        limit: 20,
        search: catalogPipelineSearch.trim(),
        business_case_id: catalogBusinessCaseFilter,
        pipeline_type: catalogPipelineTypeFilter
      };
      Promise.all([
        api.pagePipelines({
          ...common,
          offset: activePipelineOffset,
          include_deprecated: false
        }),
        api.pagePipelines({
          ...common,
          offset: deprecatedPipelineOffset,
          status: "deprecated"
        })
      ])
        .then(([activePage, deprecatedPage]) => {
          setActivePipelines(activePage.items);
          setActivePipelineTotal(activePage.total);
          setDeprecatedPipelines(deprecatedPage.items);
          setDeprecatedPipelineTotal(deprecatedPage.total);
        })
        .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load pipelines"))
        .finally(() => setPipelineCatalogLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [
    activePipelineOffset,
    catalogBusinessCaseFilter,
    catalogPipelineSearch,
    catalogPipelineTypeFilter,
    deprecatedPipelineOffset,
    pipelines,
    setNotice
  ]);

  useEffect(() => {
    setActivePipelineOffset(0);
    setDeprecatedPipelineOffset(0);
  }, [catalogBusinessCaseFilter, catalogPipelineSearch, catalogPipelineTypeFilter]);

  useEffect(() => {
    if (!selectedPipelineId && pipelines[0]) {
      setSelectedPipelineId(pipelines[0].id);
    }
  }, [pipelines, selectedPipelineId]);

  useEffect(() => {
    const current = (
      activePipelines.find((item) => item.id === selectedPipelineId)
      ?? pipelines.find((item) => item.id === selectedPipelineId)
    );
    if (current) setSelectedPipelineSnapshot(current);
  }, [activePipelines, pipelines, selectedPipelineId]);

  useEffect(() => {
    if (!openRequest) return;
    let active = true;
    const cached = [...activePipelines, ...pipelines].find(
      (item) => item.id === openRequest.pipelineId
    );
    (cached ? Promise.resolve(cached) : api.getPipeline(openRequest.pipelineId))
      .then((requestedPipeline) => {
        if (!active) return;
        setActivePipelines((current) => current.some((item) => item.id === requestedPipeline.id)
          ? current
          : [requestedPipeline, ...current]);
        setSelectedPipelineSnapshot(requestedPipeline);
        setSelectedPipelineId(requestedPipeline.id);
        setRunFeedback(null);
        setIsPipelineEditorOpen(true);
      })
      .catch(() => {
        if (active) setNotice("The requested pipeline is no longer available");
      })
      .finally(() => {
        if (active) onOpenRequestConsumed();
      });
    return () => { active = false; };
  }, [activePipelines, openRequest, onOpenRequestConsumed, pipelines, setNotice]);

  useEffect(() => {
    setPipelineNameDraft(selectedPipeline?.name ?? "");
    setPipelineDescriptionDraft(selectedPipeline?.description ?? "");
    setPipelineTypeDraft(selectedPipeline?.type ?? "custom");
    setIsRenamingPipeline(false);
  }, [selectedPipeline?.description, selectedPipeline?.id, selectedPipeline?.name, selectedPipeline?.type]);

  useEffect(() => {
    setHydratedPipelineId("");
    setVersions([]);
    setVersionTotal(0);
    setRuns([]);
    setActiveStepRuns([]);
    setPipelineDataAttachments([]);
    if (!selectedPipelineIdValue) {
      setDraftValidationError("");
      return;
    }
    let active = true;
    Promise.all([
      api.pagePipelineVersions(selectedPipelineIdValue, { limit: 20, offset: 0 }),
      api.listPipelineRuns(selectedPipelineIdValue, 8),
      api.pageBusinessCaseDataAttachments(selectedBusinessCaseIdValue, {
        limit: 100,
        offset: 0
      })
    ])
      .then(([versionPage, runItems, attachmentPage]) => {
        if (!active) return;
        const versionItems = [...versionPage.items].reverse();
        setVersions(versionItems);
        setVersionTotal(versionPage.total);
        setRuns(runItems);
        setPipelineDataAttachments(attachmentPage.items);
        const draftVersion = versionItems.find((item) => item.status === "draft");
        const selectedVersion = draftVersion ?? versionItems.at(-1);
        if (selectedVersion) {
          // A cached definition is only valid while its editable server-side
          // draft exists. Otherwise stale browser state makes a published
          // version look dirty and points dry-run at a draft that is gone.
          const workingDraft = draftVersion
            ? readPipelineWorkingDraft(selectedPipelineIdValue, draftVersion.id)
            : null;
          if (!draftVersion) clearPipelineWorkingDraft(selectedPipelineIdValue);
          const normalized = canonicalizeWorkflowDatasetIds(
            normalizeWorkflowDefinition(workingDraft ?? selectedVersion.definition),
            datasets
          );
          setWorkflowDefinition(normalized);
          setDefinitionText(JSON.stringify(normalized, null, 2));
          setIsDefinitionDirty(Boolean(workingDraft));
          setDraftValidationError("");
          setHydratedPipelineId(selectedPipelineIdValue);
          if (workingDraft) setNotice("Recovered unsaved pipeline changes from this browser tab");
        } else {
          const empty = emptyWorkflowDefinition();
          setWorkflowDefinition(empty);
          setDefinitionText(JSON.stringify(empty, null, 2));
          setIsDefinitionDirty(false);
          setHydratedPipelineId(selectedPipelineIdValue);
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
    setCreatePipelineError("");
    if (!businessCaseId) {
      setCreatePipelineError("Create or select a business case first");
      return;
    }
    setIsCreatingPipeline(true);
    try {
      const created = await api.createPipeline({
        business_case_id: businessCaseId,
        name,
        description,
        type: pipelineType,
        definition: workflowTemplateDefinition(
          pipelineTemplate,
          createBusinessCase?.target_column
            ?? businessCases.find((item) => item.id === businessCaseId)?.target_column
            ?? ""
        )
      });
      setNotice(`Pipeline created: ${created.name}`);
      setSelectedPipelineSnapshot(created);
      setSelectedPipelineId(created.id);
      setIsCreatePipelineOpen(false);
      setIsPipelineEditorOpen(true);
      setName("");
      setDescription("");
      setPipelineTemplate(suggestedPipelineTemplate(pipelineType));
      await onRefresh();
    } catch (error) {
      setCreatePipelineError(error instanceof Error ? error.message : "Could not create pipeline");
    } finally {
      setIsCreatingPipeline(false);
    }
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
      clearPipelineWorkingDraft(copied.id);
      const empty = emptyWorkflowDefinition();
      setHydratedPipelineId("");
      setVersions([]);
      setWorkflowDefinition(empty);
      setDefinitionText(JSON.stringify(empty, null, 2));
      setIsDefinitionDirty(false);
      setCopyPipelineTarget(null);
      setCopyPipelineName("");
      setSelectedPipelineSnapshot(copied);
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
      const message = "Pipeline definition is not valid JSON";
      setDraftValidationError(message);
      setNotice(message);
      return null;
    }
    try {
      const saved = await api.updateDraftPipelineVersion(selectedPipeline.id, parsed);
      clearPipelineWorkingDraft(selectedPipeline.id);
      setIsDefinitionDirty(false);
      setDraftValidationError("");
      if (showNotice) setNotice("Draft version saved");
      const versionPage = await api.pagePipelineVersions(selectedPipeline.id, {
        limit: 20,
        offset: 0
      });
      setVersions([...versionPage.items].reverse());
      setVersionTotal(versionPage.total);
      await onRefresh();
      return saved;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Draft validation failed";
      setDraftValidationError(message);
      if (showNotice) setNotice(message);
      return null;
    }
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
    try {
      await api.publishDraftPipelineVersion(selectedPipeline.id);
      setDraftValidationError("");
      setNotice("Draft version published");
      const versionPage = await api.pagePipelineVersions(selectedPipeline.id, {
        limit: 20,
        offset: 0
      });
      setVersions([...versionPage.items].reverse());
      setVersionTotal(versionPage.total);
      await onRefresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Draft publish validation failed";
      setDraftValidationError(message);
      setNotice(message);
    }
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
    const versionPage = await api.pagePipelineVersions(selectedPipeline.id, {
      limit: 20,
      offset: 0
    });
    setVersions([...versionPage.items].reverse());
    setVersionTotal(versionPage.total);
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
    setActiveRunMonitor(null);
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
      setActiveRunMonitor(run);
      setRunFeedback({ status: "running", title: `${action} in progress`, detail: `Worker accepted ${target} run ${shortId(run.id)}.` });
      while (run.status === "queued" || run.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        const runStatus = await api.getPipelineRunStatus(selectedPipeline.id, run.id);
        run = { ...run, ...runStatus };
        if (run.status !== "queued" && run.status !== "running") {
          run = await api.getPipelineRun(selectedPipeline.id, run.id);
        }
        setActiveRunMonitor(run);
      }
      setRuns(await api.listPipelineRuns(selectedPipeline.id, 8));
      setActiveStepRuns(await api.listPipelineStepRuns(selectedPipeline.id, run.id));
      const scope = run.output_manifest[0]?.data_scope ?? "unknown";
      const counts = `${run.input_row_count ?? 0} input rows → ${run.output_row_count ?? 0} output rows`;
      const failed = run.status === "failed";
      const cancelled = run.status === "cancelled";
      const title = failed ? `${action} failed` : cancelled ? `${action} cancelled` : `${action} completed`;
      const fittedTransform = run.output_manifest.find((item) => item.artifact_type === "feature_transform");
      const fittedDetail = fittedTransform?.artifact_id
        ? ` · fitted transform ${fittedTransform.artifact_id}`
        : "";
      const detail = failed
        ? run.error_message
        : cancelled
          ? "Run cancellation was accepted; inspect the monitor log for the last completed worker event."
        : `${target} finished successfully · ${scope} scope · ${counts}${fittedDetail}`;
      setRunFeedback({ status: failed || cancelled ? "failed" : "succeeded", title, detail });
      setNotice(`${title}: ${detail}`);
      if (!failed && !cancelled && isDryRun) setDryRunResult(run);
      if (!failed && !cancelled && !isDryRun) {
        await onRefresh();
      }
      setActiveRunMonitor(run);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Pipeline execution could not be started";
      setRunFeedback({ status: "failed", title: `${action} failed`, detail });
    }
  }

  async function openCatalogRunDialog(pipeline: Pipeline) {
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
      setCatalogRunSelections({});
      setCatalogRunModelSelections(Object.fromEntries(runModels.map((model) => [model.key, model.versions[0]?.id ?? ""])));
      setCatalogRunResult(null);
      setCatalogRunDialog({ pipeline, version: published, inputs, models: runModels });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not prepare pipeline run");
    }
  }

  async function submitCatalogRun(event: FormEvent) {
    event.preventDefault();
    if (!catalogRunDialog) return;
    const missing = catalogRunDialog.inputs.find(
      (input) => requiresRuntimeDatasetSelection(input.policy)
        && !catalogRunSelections[input.key]
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
        input_versions: catalogRunSelections,
        model_versions: catalogRunModelSelections
      });
      setNotice(`Pipeline run ${shortId(run.id)} queued`);
      setCatalogRunResult(run);
      setSelectedPipelineId(catalogRunDialog.pipeline.id);
      while (run.status === "queued" || run.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        const runStatus = await api.getPipelineRunStatus(
          catalogRunDialog.pipeline.id,
          run.id,
        );
        run = { ...run, ...runStatus };
        if (run.status !== "queued" && run.status !== "running") {
          run = await api.getPipelineRun(catalogRunDialog.pipeline.id, run.id);
        }
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
    const draftVersion = versions.find((item) => item.status === "draft");
    if (!selectedPipeline || hydratedPipelineId !== selectedPipeline.id || !draftVersion) return;
    setWorkflowDefinition(definition);
    setDefinitionText(JSON.stringify(definition, null, 2));
    setIsDefinitionDirty(true);
    setDraftValidationError("");
    writePipelineWorkingDraft(selectedPipeline.id, draftVersion.id, definition);
  }

  function updateDefinitionText(value: string) {
    const draftVersion = versions.find((item) => item.status === "draft");
    if (!selectedPipeline || hydratedPipelineId !== selectedPipeline.id || !draftVersion) return;
    setDefinitionText(value);
    setIsDefinitionDirty(true);
    try {
      const parsed = JSON.parse(value);
      setWorkflowDefinition(canonicalizeWorkflowDatasetIds(
        normalizeWorkflowDefinition(parsed),
        datasets
      ));
      writePipelineWorkingDraft(selectedPipeline.id, draftVersion.id, parsed);
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
          <button className="secondary-button compact-button" type="button" onClick={() => {
            setRunHistoryPipelineId(item.id);
            setIsRunHistoryOpen(true);
          }}>
            <History size={14} /> Runs
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
              <button className="secondary-button" type="button" onClick={() => {
                setRunHistoryPipelineId("all");
                setIsRunHistoryOpen(true);
              }}>
                <History size={16} /> Runs history
              </button>
              <button className="primary-button" type="button" onClick={() => {
                setCreatePipelineError("");
                setIsCreatePipelineOpen(true);
              }}>
                <Plus size={16} /> New pipeline
              </button>
            </div>
          </div>
          <div className="pipeline-catalog-filters" aria-label="Pipeline filters">
            <label className="search-field">
              <Search size={16} />
              <input
                aria-label="Search pipelines"
                placeholder="Search name, description or type"
                value={catalogPipelineSearch}
                onChange={(event) => setCatalogPipelineSearch(event.target.value)}
              />
            </label>
            <label>
              <span><Filter size={14} /> Business case</span>
              <PagedCatalogSelect
                value={catalogBusinessCaseFilter}
                onChange={(value) => setCatalogBusinessCaseFilter(value)}
                loadPage={api.pageBusinessCases}
                getId={(item) => item.id}
                getLabel={(item) => item.name}
                emptyLabel="All business cases"
                searchPlaceholder="Search Business Cases"
              />
            </label>
            <label>
              <span><Filter size={14} /> Pipeline type</span>
              <select
                aria-label="Filter pipelines by type"
                value={catalogPipelineTypeFilter}
                onChange={(event) => setCatalogPipelineTypeFilter(event.target.value)}
              >
                <option value="">All pipeline types</option>
                {catalogPipelineTypes.map((type) => (
                  <option key={type} value={type}>{type.replaceAll("_", " ")}</option>
                ))}
              </select>
            </label>
            <span className="pipeline-filter-summary">
              {activePipelineTotal} active workflows
            </span>
          </div>
          <div className="pipeline-table" role="table" aria-label="Pipelines">
            <div className="pipeline-table-row head" role="row">
              <span>Name</span><span>Business case</span><span>Purpose</span><span>Version</span><span>Status</span><span>Updated</span><span />
            </div>
            {filteredActivePipelines.map((item) => renderPipelineRow(item))}
            {!filteredActivePipelines.length && (
              <div className="catalog-empty">
                {hasCatalogFilters
                  ? "No active pipelines match the selected filters."
                  : "No active pipelines. Create a workflow or copy one from the deprecated section."}
              </div>
            )}
          </div>
          <PaginationControls
            total={activePipelineTotal}
            limit={20}
            offset={activePipelineOffset}
            onOffsetChange={setActivePipelineOffset}
            disabled={pipelineCatalogLoading}
            label="pipelines"
          />
        </section>
        {deprecatedPipelineTotal > 0 && (
          <details className="panel deprecated-pipelines-panel">
            <summary>
              <span>
                <strong>Deprecated pipelines</strong>
                <small>Preserved for audit and lineage. They cannot be edited or run.</small>
              </span>
              <i>{deprecatedPipelineTotal}</i>
            </summary>
            <div className="pipeline-table" role="table" aria-label="Deprecated pipelines">
              <div className="pipeline-table-row head" role="row">
                <span>Name</span><span>Business case</span><span>Purpose</span><span>Version</span><span>Status</span><span>Updated</span><span />
              </div>
              {filteredDeprecatedPipelines.map((item) => renderPipelineRow(item, true))}
              {!filteredDeprecatedPipelines.length && (
                <div className="catalog-empty">No deprecated pipelines match the selected filters.</div>
              )}
            </div>
            <PaginationControls
              total={deprecatedPipelineTotal}
              limit={20}
              offset={deprecatedPipelineOffset}
              onOffsetChange={setDeprecatedPipelineOffset}
              disabled={pipelineCatalogLoading}
              label="deprecated pipelines"
            />
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
                <PagedCatalogSelect
                  value={businessCaseId}
                  onChange={(value, item) => {
                    setBusinessCaseId(value);
                    setCreateBusinessCase(item);
                  }}
                  loadPage={api.pageBusinessCases}
                  getId={(item) => item.id}
                  getLabel={(item) => item.name}
                  emptyLabel="Choose BC"
                  searchPlaceholder="Search Business Cases"
                />
              </label>
              <label>Name<input value={name} onChange={(event) => setName(event.target.value)} autoFocus required /></label>
              <label>Purpose
                <select value={pipelineType} onChange={(event) => {
                  const purpose = event.target.value;
                  setPipelineType(purpose);
                  setPipelineTemplate(suggestedPipelineTemplate(purpose));
                }}>
                  <option value="custom">Custom workflow</option>
                  <option value="training">Training workflow</option>
                  <option value="automl">AutoML workflow</option>
                  <option value="batch_scoring">Batch scoring</option>
                  <option value="monitoring">Monitoring workflow</option>
                </select>
              </label>
              <label>Template
                <select value={pipelineTemplate}
                  onChange={(event) => setPipelineTemplate(event.target.value as PipelineTemplate)}>
                  <option value="custom">Empty custom workflow</option>
                  <option value="training">Training · DE, FE, Training, Test Scoring</option>
                  <option value="automl">AutoML · DE, model-aware search and champion</option>
                  <option value="batch_scoring">Batch scoring · DE, FE Transform, Batch Scoring</option>
                  <option value="monitoring">Monitoring · Target Join, Performance Report</option>
                </select>
                <small>
                  Suggested from purpose. The template initializes an editable draft; purpose remains metadata.
                </small>
              </label>
              {pipelineType === "monitoring" && (
                <div className="form-note">
                  Creates an editable Target Join and model-performance monitoring workflow.
                </div>
              )}
              <label>Description<textarea className="compact-textarea" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
              {createPipelineError && <div className="form-warning" role="alert">{createPipelineError}</div>}
              <div className="modal-actions">
                <button className="secondary-button" type="button" disabled={isCreatingPipeline} onClick={() => setIsCreatePipelineOpen(false)}>Cancel</button>
                <button className="primary-button" type="submit" disabled={isCreatingPipeline}>
                  <Plus size={16} /> {isCreatingPipeline ? "Creating…" : "Create pipeline"}
                </button>
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
            initialPipelineId={runHistoryPipelineId}
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
            onBack={isRunHistoryOpen ? () => setSelectedRunDetails(null) : undefined}
            onClose={() => {
              setSelectedRunDetails(null);
              setIsRunHistoryOpen(false);
            }}
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
              {!catalogRunResult && catalogRunDialog.inputs.map((input) => (
                <PipelineRunDatasetInputSelector
                  key={input.key}
                  input={input}
                  businessCaseId={catalogRunDialog.pipeline.business_case_id}
                  value={catalogRunSelections[input.key] ?? ""}
                  onChange={(value) => setCatalogRunSelections((current) => ({
                    ...current,
                    [input.key]: value
                  }))}
                />
              ))}
              {!catalogRunResult && catalogRunDialog.models.map((model) => (
                <PipelineRunModelSelector
                  key={model.key}
                  model={model}
                  value={catalogRunModelSelections[model.key] ?? ""}
                  onChange={(value) => setCatalogRunModelSelections((current) => ({
                    ...current,
                    [model.key]: value
                  }))}
                />
              ))}
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
              <option value="automl">AutoML</option>
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
          {activeRunMonitor && (
            <button
              className="secondary-button compact-button"
              type="button"
              onClick={() => setSelectedRunDetails(activeRunMonitor)}
            >
              <Activity size={14} /> Monitor
            </button>
          )}
          {!isRunActive && <button className="icon-button" type="button" onClick={() => setRunFeedback(null)} aria-label="Dismiss"><X size={15} /></button>}
        </div>
      )}
      {(draftValidationError || workflowValidationIssues.length > 0) && (
        <div className="inline-run-feedback failed validation-feedback" role="alert" aria-live="polite">
          <span className="run-result-icon"><AlertTriangle size={16} /></span>
          <div>
            <strong>{draftValidationError ? "Pipeline validation failed" : "Pipeline settings need attention"}</strong>
            {draftValidationError && <span>{draftValidationError}</span>}
            {!draftValidationError && workflowValidationIssues.slice(0, 5).map((issue) => (
              <span key={issue}>{issue}</span>
            ))}
            {!draftValidationError && workflowValidationIssues.length > 5 && (
              <span>And {workflowValidationIssues.length - 5} more validation issue(s).</span>
            )}
          </div>
          {draftValidationError && (
            <button className="icon-button" type="button" onClick={() => setDraftValidationError("")} aria-label="Dismiss validation message">
              <X size={15} />
            </button>
          )}
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
          onBack={isRunHistoryOpen ? () => setSelectedRunDetails(null) : undefined}
          onClose={() => {
            setSelectedRunDetails(null);
            setIsRunHistoryOpen(false);
          }}
          onChanged={async () => {
            setRuns(await api.listPipelineRuns(selectedPipeline.id, 8));
            setRunHistoryRefreshKey((current) => current + 1);
          }}
        />
      )}

      <div className="panel pipeline-canvas-panel">
        {hydratedPipelineId !== selectedPipeline?.id ? (
          <p>Loading pipeline definitionâ€¦</p>
        ) : <DeferredPanel>
          <WorkflowEditor
            key={`${selectedPipeline.id}:${versions.find((item) => item.status === "draft")?.id ?? versions.at(-1)?.id ?? "empty"}`}
            definition={workflowDefinition}
            businessCase={businessCases.find((item) => item.id === selectedBusinessCaseIdValue)}
            datasets={latestLogicalDatasetAliases(datasets)}
            models={models}
            pipelines={pipelines}
            dataAttachments={pipelineDataAttachments.map((attachment) => {
              const dataset = datasets.find((item) => item.id === attachment.data_asset_id);
              return dataset ? { ...attachment, data_asset_id: dataset.logical_id } : attachment;
            })}
            pipelineId={selectedPipeline?.id}
            outputNameSuggestion={selectedPipeline?.name ?? "result"}
            pipelineType={selectedPipeline?.type ?? pipelineTypeDraft}
            onChange={updateWorkflowDefinition}
            disabled={!hasDraft}
          />
        </DeferredPanel>}
      </div>

      <div className="editor-lower-grid">
        <details className="panel editor-details">
          <summary>Recent versions <span>{versionTotal}</span></summary>
          <AssetList title="" assets={versions.map((item) => ({
            id: item.id,
            name: `v${item.version_number}`,
            meta: `hash ${item.definition_hash.slice(0, 12)} · ${item.published_at ? formatDateTime(item.published_at) : "not published"}`,
            status: item.status
          }))} />
          {versionTotal > versions.length && selectedPipeline && (
            <button
              className="secondary-button compact-button"
              type="button"
              onClick={() => setVersionHistoryPipeline(selectedPipeline)}
            >
              <History size={14} /> Open paginated history
            </button>
          )}
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
            {!catalogRunResult && catalogRunDialog.inputs.map((input) => (
              <PipelineRunDatasetInputSelector
                key={input.key}
                input={input}
                businessCaseId={catalogRunDialog.pipeline.business_case_id}
                value={catalogRunSelections[input.key] ?? ""}
                onChange={(value) => setCatalogRunSelections((current) => ({
                  ...current,
                  [input.key]: value
                }))}
              />
            ))}
            {!catalogRunResult && catalogRunDialog.models.map((model) => (
              <PipelineRunModelSelector
                key={model.key}
                model={model}
                value={catalogRunModelSelections[model.key] ?? ""}
                onChange={(value) => setCatalogRunModelSelections((current) => ({
                  ...current,
                  [model.key]: value
                }))}
              />
            ))}
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

function suggestedPipelineTemplate(purpose: string): PipelineTemplate {
  if (purpose === "training") return "training";
  if (purpose === "automl") return "automl";
  if (purpose === "batch_scoring") return "batch_scoring";
  if (purpose === "monitoring") return "monitoring";
  return "custom";
}
