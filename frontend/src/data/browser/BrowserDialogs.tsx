import {
  Database,
  Filter,
  ListChecks,
  Play,
  RotateCcw,
  Search,
  Save,
  Table2,
  X
} from "lucide-react";
import type { FormEvent, KeyboardEvent } from "react";
import { useMemo, useRef, useState } from "react";

import type { DataAsset, DatasetPreview } from "../../api/client";
import { datasetVersionLabel } from "../catalog/DatasetCatalogPanel";
import type { DatasetCellValue } from "../profile/contracts";
import {
  cellKind,
  displayValue,
  valueToSearchText
} from "../dataValueFormatters";
import { filterOperatorLabels } from "./contracts";
import type {
  ColumnFilterConfig,
  FilterOperator,
  SortDirection,
  SortRule
} from "./contracts";
import {
  buildColumnValueOptions,
  defaultFilterOperator,
  filterOperatorsForColumn,
  matchesFilter,
  operatorDoesNotNeedValue,
  quoteSqlIdentifier,
  sortLabel,
  sortRecords
} from "./browserDataUtils";


export function SortDirectionToggle({
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

export function SaveViewModal({
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

export function CustomSqlModal({
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

export function DrilldownModal({
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
