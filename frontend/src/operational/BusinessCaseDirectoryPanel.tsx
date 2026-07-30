import { KeyRound, Search, Send, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCaseAccessRole,
  BusinessCaseCatalogEntry
} from "../api/client";
import { PaginationControls } from "../components/PaginationControls";

type RequestableRole = Exclude<BusinessCaseAccessRole, "owner">;

export function BusinessCaseDirectoryPanel({
  setNotice
}: {
  setNotice: (message: string) => void;
}) {
  const [items, setItems] = useState<BusinessCaseCatalogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selected, setSelected] = useState<BusinessCaseCatalogEntry | null>(null);
  const [requestedRole, setRequestedRole] = useState<RequestableRole>("reader");
  const [justification, setJustification] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true);
      api.pageBusinessCaseCatalog({
        limit: 30,
        offset,
        search: search.trim()
      }).then((page) => {
        setItems(page.items);
        setTotal(page.total);
        if (page.total > 0 && page.offset >= page.total) {
          setOffset(Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit));
        }
      }).catch((error) => {
        setNotice(error instanceof Error ? error.message : "Could not load the Business Case directory");
      }).finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [offset, refreshKey, search, setNotice]);

  useEffect(() => setOffset(0), [search]);

  function openRequest(item: BusinessCaseCatalogEntry) {
    setSelected(item);
    setRequestedRole("reader");
    setJustification("");
  }

  async function submitRequest() {
    if (!selected || !justification.trim()) {
      setNotice("Describe why you need access");
      return;
    }
    setSubmitting(true);
    try {
      await api.requestBusinessCaseAccess(selected.id, {
        requested_role: requestedRole,
        justification: justification.trim()
      });
      setSelected(null);
      setRefreshKey((value) => value + 1);
      setNotice(`Access request sent for ${selected.name}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not submit the access request");
    } finally {
      setSubmitting(false);
    }
  }

  return <>
    <div className="catalog-toolbar">
      <div>
        <h2>Organization directory</h2>
        <p>{total} Business Cases · names and lifecycle status only</p>
      </div>
    </div>
    <label className="search-field">
      <Search size={16} />
      <input
        aria-label="Search the organization Business Case directory"
        placeholder="Search Business Cases by name"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
    </label>
    <div className="bc-directory-list" aria-busy={loading}>
      {items.map((item) => {
        const requestable = !item.access_role
          && item.request_status !== "pending"
          && item.status !== "archived";
        return <div className="bc-directory-row" key={item.id}>
          <span>
            <strong>{item.name}</strong>
            <small>BC {item.id.slice(0, 8)} · {item.status}</small>
          </span>
          <span className="bc-directory-state">
            {item.access_role
              ? <em className="status-pill active">Access: {item.access_role}</em>
              : item.request_status === "pending"
                ? <em className="status-pill queued">Request pending</em>
                : item.status === "archived"
                  ? <em className="status-pill archived">Archived</em>
                  : <em className="status-pill">No access</em>}
            <button
              className="secondary-button compact-button"
              type="button"
              disabled={!requestable}
              onClick={() => openRequest(item)}
            >
              <KeyRound size={14} />
              Request access
            </button>
          </span>
        </div>;
      })}
      {!loading && items.length === 0 && (
        <div className="catalog-empty">No Business Cases match this name.</div>
      )}
    </div>
    <PaginationControls
      total={total}
      limit={30}
      offset={offset}
      onOffsetChange={setOffset}
      disabled={loading}
      label="directory Business Cases"
    />

    {selected && (
      <div
        className="modal-backdrop"
        role="presentation"
        onMouseDown={(event) => event.target === event.currentTarget && setSelected(null)}
      >
        <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="access-request-title">
          <div className="modal-header">
            <div>
              <h2 id="access-request-title">Request access to {selected.name}</h2>
              <p>The Business Case owner and managers can review this request.</p>
            </div>
            <button className="icon-button" type="button" aria-label="Close" onClick={() => setSelected(null)}>
              <X size={18} />
            </button>
          </div>
          <div className="form-panel">
            <label>
              Requested access
              <select
                value={requestedRole}
                onChange={(event) => setRequestedRole(event.target.value as RequestableRole)}
              >
                <option value="report_viewer">Report viewer</option>
                <option value="reader">Reader</option>
                <option value="contributor">Contributor</option>
                <option value="manager">Manager</option>
              </select>
            </label>
            <label>
              Justification
              <textarea
                autoFocus
                className="compact-textarea"
                maxLength={2000}
                value={justification}
                onChange={(event) => setJustification(event.target.value)}
                placeholder="Describe the work you need to perform"
              />
            </label>
          </div>
          <div className="modal-actions">
            <button className="secondary-button" type="button" onClick={() => setSelected(null)}>Cancel</button>
            <button
              className="primary-button"
              type="button"
              disabled={submitting || !justification.trim()}
              onClick={() => void submitRequest()}
            >
              <Send size={15} />
              {submitting ? "Sending…" : "Send request"}
            </button>
          </div>
        </div>
      </div>
    )}
  </>;
}
