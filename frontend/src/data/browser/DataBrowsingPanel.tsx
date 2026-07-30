import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  Database,
  Drill,
  Filter,
  ListChecks,
  RotateCcw,
  Search,
  Save,
  Table2
} from "lucide-react";
import { lazy, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../api/client";
import type { DataAsset, DatasetPreview } from "../../api/client";
import { DeferredPanel } from "../../components/DeferredPanel";
import { readRolesMetadata } from "../../analysis/dataRoles";
import {
  browserFiltersFromVisualizationDrill,
  type VisualizationDrillRequest
} from "../../analysis/drillContext";
import { datasetVersionLabel } from "../catalog/DatasetCatalogPanel";
import type { DatasetCellValue } from "../profile/contracts";
import {
  cellKind,
  columnRoleForColumn,
  columnRoleLabel,
  displayValue,
  valueToSearchText
} from "../dataValueFormatters";

const TimeSeriesWorkbench = lazy(() =>
  import("../../analysis/TimeSeriesWorkbench").then((module) => ({
    default: module.TimeSeriesWorkbench
  }))
);
import {
  DATA_BROWSER_DRILL_PREVIEW_LIMIT,
  aggregationFunctionLabels,
  filterOperatorLabels,
  groupingRoleOptions
} from "./contracts";
import type {
  AggregatedColumn,
  AggregationFunction,
  ColumnFilterConfig,
  FilterOperator,
  GroupingColumnConfig,
  GroupingRole,
  SortRule
} from "./contracts";
import {
  aggregationFunctionsForColumn,
  buildAggregationResult,
  buildColumnValueOptions,
  buildDataViewDefinition,
  defaultAggregationFunction,
  defaultFilterOperator,
  filterOperatorsForColumn,
  matchesFilter,
  operatorDoesNotNeedValue,
  orderAggregatedColumns,
  sortLabel,
  sortRecords
} from "./browserDataUtils";
import {
  CustomSqlModal,
  DrilldownModal,
  SaveViewModal,
  SortDirectionToggle
} from "./BrowserDialogs";


export function DataBrowsingPanel({
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
