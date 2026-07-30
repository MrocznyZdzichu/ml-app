import { Check, Clock3, Inbox, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCaseAccessRequest,
  BusinessCaseAccessRole
} from "../api/client";
import { PaginationControls } from "../components/PaginationControls";

type RequestRole = Exclude<BusinessCaseAccessRole, "owner">;
type RequestBox = "incoming" | "mine";
type RequestStatus = BusinessCaseAccessRequest["status"];

export function PermissionRequestsPanel({
  setNotice,
  reloadKey = 0
}: {
  setNotice: (message: string) => void;
  reloadKey?: number;
}) {
  const [box, setBox] = useState<RequestBox>("incoming");
  const [statusFilter, setStatusFilter] = useState<RequestStatus | "">("pending");
  const [items, setItems] = useState<BusinessCaseAccessRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [roles, setRoles] = useState<Record<string, RequestRole>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.pageBusinessCaseAccessRequests({
        box,
        status: statusFilter || undefined,
        limit: 30,
        offset
      });
      setItems(page.items);
      setTotal(page.total);
      if (page.total > 0 && page.offset >= page.total) {
        setOffset(Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit));
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load permission requests");
    } finally {
      setLoading(false);
    }
  }, [box, offset, setNotice, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey, reloadKey]);

  useEffect(() => setOffset(0), [box, statusFilter]);

  async function approve(item: BusinessCaseAccessRequest) {
    setBusyId(item.id);
    try {
      await api.approveBusinessCaseAccessRequest(item.id, {
        access_role: roles[item.id] ?? item.requested_role as RequestRole,
        decision_note: notes[item.id]?.trim() ?? ""
      });
      setNotice(`Access to ${item.business_case_name} approved`);
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not approve the request");
    } finally {
      setBusyId("");
    }
  }

  async function reject(item: BusinessCaseAccessRequest) {
    setBusyId(item.id);
    try {
      await api.rejectBusinessCaseAccessRequest(item.id, {
        decision_note: notes[item.id]?.trim() ?? ""
      });
      setNotice(`Access request for ${item.business_case_name} rejected`);
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not reject the request");
    } finally {
      setBusyId("");
    }
  }

  return <div className="panel permission-requests-panel">
    <div className="panel-header">
      <div>
        <h2>Permission requests</h2>
        <p>Owners and effective Business Case managers can decide incoming requests.</p>
      </div>
      <button className="secondary-button compact-button" type="button" disabled={loading} onClick={() => void refresh()}>
        <RotateCcw className={loading ? "run-spinner" : undefined} size={15} />
        Refresh
      </button>
    </div>

    <div className="permission-request-toolbar">
      <div className="segmented-control" role="group" aria-label="Permission request mailbox">
        <button type="button" className={box === "incoming" ? "active" : ""} onClick={() => setBox("incoming")}>
          <Inbox size={15} /> Incoming
        </button>
        <button type="button" className={box === "mine" ? "active" : ""} onClick={() => setBox("mine")}>
          <Clock3 size={15} /> My requests
        </button>
      </div>
      <label>
        Status
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as RequestStatus | "")}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
      </label>
    </div>

    <div className="permission-request-list" aria-busy={loading}>
      {items.map((item) => <article className="permission-request-card" key={item.id}>
        <div className="permission-request-summary">
          <span>
            <strong>{item.business_case_name}</strong>
            <small>
              {box === "incoming"
                ? `${item.requester_display_name} · ${item.requester_email}`
                : `Requested ${item.requested_role}`}
              {" · "}{new Date(item.created_at).toLocaleString()}
            </small>
          </span>
          <em className={`status-pill ${item.status}`}>{item.status}</em>
        </div>
        <p>{item.justification}</p>
        {item.status !== "pending" && (
          <small className="permission-request-decision">
            {item.granted_role ? `Granted ${item.granted_role}` : "No access granted"}
            {item.decision_note ? ` · ${item.decision_note}` : ""}
          </small>
        )}
        {box === "incoming" && item.status === "pending" && (
          <div className="permission-request-actions">
            <label>
              Grant role
              <select
                value={roles[item.id] ?? item.requested_role}
                onChange={(event) => setRoles((current) => ({
                  ...current,
                  [item.id]: event.target.value as RequestRole
                }))}
              >
                <option value="report_viewer">Report viewer</option>
                <option value="reader">Reader</option>
                <option value="contributor">Contributor</option>
                <option value="manager">Manager</option>
              </select>
            </label>
            <label>
              Decision note
              <input
                maxLength={2000}
                value={notes[item.id] ?? ""}
                onChange={(event) => setNotes((current) => ({
                  ...current,
                  [item.id]: event.target.value
                }))}
                placeholder="Optional note"
              />
            </label>
            <button className="primary-button compact-button" type="button" disabled={busyId === item.id} onClick={() => void approve(item)}>
              <Check size={15} /> Approve
            </button>
            <button className="secondary-button danger-button compact-button" type="button" disabled={busyId === item.id} onClick={() => void reject(item)}>
              <X size={15} /> Reject
            </button>
          </div>
        )}
      </article>)}
      {!loading && items.length === 0 && (
        <div className="empty-state">No permission requests in this view.</div>
      )}
    </div>
    <PaginationControls
      total={total}
      limit={30}
      offset={offset}
      onOffsetChange={setOffset}
      disabled={loading}
      label="permission requests"
    />
  </div>;
}
