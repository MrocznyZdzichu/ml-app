import {
  Activity,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Database,
  Filter,
  Play,
  Table2
} from "lucide-react";
import { lazy, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../api/client";
import type { DataAsset, DatasetPreview } from "../../api/client";
import { DeferredPanel } from "../../components/DeferredPanel";
import { Metric } from "../../workspace/Overview";
import { readRolesMetadata } from "../../analysis/dataRoles";
import { datasetVersionLabel } from "../catalog/DatasetCatalogPanel";
import { defaultProfilingRangeSettings } from "../profile/contracts";
import type {
  DescriptiveComputedProfile,
  DescriptiveProfileCacheEntry,
  EffectiveTargetType,
  ProfilingRangeSettings,
  TargetRelationProfile,
  TargetTypeSetting
} from "../profile/contracts";
import {
  columnRoleForColumn,
  columnRoleLabel,
  displayValue
} from "../dataValueFormatters";

const TimeSeriesWorkbench = lazy(() =>
  import("../../analysis/TimeSeriesWorkbench").then((module) => ({
    default: module.TimeSeriesWorkbench
  }))
);
import {
  ColumnSelectionModal,
  ColumnSelectionSummary,
  MiniDiscreteDistribution,
  MiniHistogram,
  ProfileFact,
  ProfilingRangeModal,
  SegmentScanResults,
  TargetRelationCard,
  formatNullableNumber,
  formatNumber,
  formatPercent,
  formatInteger,
  inferTargetColumn,
  inferTargetType,
  relationCardKey,
  syncSelectedNames,
  usesDiscreteDistribution
} from "./DescriptiveProfileDetails";


export function DescriptiveAnalysisPanel({
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

  const columnProfiles = useMemo(
    () => restoredComputedProfile?.columnProfiles ?? [],
    [restoredComputedProfile]
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
    () => restoredComputedProfile?.targetRelations ?? [],
    [restoredComputedProfile]
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
    () => restoredComputedProfile?.segmentProfile ?? null,
    [restoredComputedProfile]
  );
  const dataQualityNotes = useMemo(
    () => restoredComputedProfile?.dataQualityNotes ?? [],
    [restoredComputedProfile]
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
