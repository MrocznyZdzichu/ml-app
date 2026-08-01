import { Check, Clock3, Inbox, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCaseAccessRequest,
  BusinessCaseAccessRole
} from "../api/client";
import { PaginationControls } from "../components/PaginationControls";

type RequestRole = Exclude<BusinessCaseAccessRole, "owner">;
type CurrentRequestBox = "incoming" | "mine";
type HistoryRequestBox = "submitted_history" | "handled";
type RequestBox = CurrentRequestBox | HistoryRequestBox;
type RequestStatus = BusinessCaseAccessRequest["status"];

export function PermissionRequestsPanel({
  setNotice,
  reloadKey = 0,
  businessCaseId
}: {
  setNotice: (message: string) => void;
  reloadKey?: number;
  businessCaseId?: string;
}) {
  const [mode, setMode] = useState<"current" | "history">("current");
  const [currentBox, setCurrentBox] = useState<CurrentRequestBox>("incoming");
  const [historyBox, setHistoryBox] = useState<HistoryRequestBox>("submitted_history");
  const [historyStatus, setHistoryStatus] = useState<RequestStatus | "">("");
  const [items, setItems] = useState<BusinessCaseAccessRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [roles, setRoles] = useState<Record<string, RequestRole>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState("");
  const box: RequestBox = mode === "current" ? currentBox : historyBox;
  const statusFilter = mode === "current" ? "pending" : historyStatus;
  const isIncomingCurrent = mode === "current" && (
    businessCaseId !== undefined || currentBox === "incoming"
  );
  const showRequester = businessCaseId !== undefined || isIncomingCurrent || historyBox === "handled";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const page = businessCaseId === undefined
        ? await api.pageBusinessCaseAccessRequests({
          box,
          status: statusFilter || undefined,
          limit: 30,
          offset
        })
        : await api.pageBusinessCaseAccessRequestsForBusinessCase(businessCaseId, {
          history: mode === "history",
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
  }, [box, businessCaseId, mode, offset, setNotice, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey, reloadKey]);

  useEffect(() => setOffset(0), [mode, currentBox, historyBox, historyStatus]);

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
        <h2>{businessCaseId ? "Access requests" : "Permission requests"}</h2>
        <p>{businessCaseId
          ? "Review open requests and completed decisions for this Business Case."
          : "Review current requests and your submitted or handled request history."}
        </p>
      </div>
      <button className="secondary-button compact-button" type="button" disabled={loading} onClick={() => void refresh()}>
        <RotateCcw className={loading ? "run-spinner" : undefined} size={15} />
        Refresh
      </button>
    </div>

    <div className="permission-request-toolbar">
      <div className="segmented-control" role="group" aria-label="Permission request mailbox">
        <button type="button" className={mode === "current" ? "active" : ""} onClick={() => setMode("current")}>
          <Inbox size={15} /> Current
        </button>
        <button type="button" className={mode === "history" ? "active" : ""} onClick={() => setMode("history")}>
          <Clock3 size={15} /> History
        </button>
      </div>
      {businessCaseId === undefined ? (
        mode === "current" ? (
          <div className="segmented-control" role="group" aria-label="Current permission requests">
            <button type="button" className={currentBox === "incoming" ? "active" : ""} onClick={() => setCurrentBox("incoming")}>
              <Inbox size={15} /> Incoming
            </button>
            <button type="button" className={currentBox === "mine" ? "active" : ""} onClick={() => setCurrentBox("mine")}>
              <Clock3 size={15} /> My requests
            </button>
          </div>
        ) : (
          <>
            <div className="segmented-control" role="group" aria-label="Permission request history">
              <button type="button" className={historyBox === "submitted_history" ? "active" : ""} onClick={() => setHistoryBox("submitted_history")}>
                <Clock3 size={15} /> Submitted by me
              </button>
              <button type="button" className={historyBox === "handled" ? "active" : ""} onClick={() => setHistoryBox("handled")}>
                <Check size={15} /> Handled by me
              </button>
            </div>
            <HistoryStatusFilter value={historyStatus} onChange={setHistoryStatus} />
          </>
        )
      ) : mode === "history" ? (
        <HistoryStatusFilter value={historyStatus} onChange={setHistoryStatus} />
      ) : null}
    </div>

    <div className="permission-request-list" aria-busy={loading}>
      {items.map((item) => <article className="permission-request-card" key={item.id}>
        <div className="permission-request-summary">
          <span>
            <strong>{item.business_case_name}</strong>
            <small>
              {showRequester
                ? `${item.requester_display_name} · ${item.requester_email}`
                : `Requested ${item.requested_role}`}
              {" · "}{mode === "history" && item.decided_at
                ? `Decided ${new Date(item.decided_at).toLocaleString()}`
                : new Date(item.created_at).toLocaleString()}
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
        {isIncomingCurrent && item.status === "pending" && (
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
        <div className="empty-state">
          {mode === "history" ? "No permission requests in this history." : "No current permission requests in this view."}
        </div>
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

function HistoryStatusFilter({
  value,
  onChange
}: {
  value: RequestStatus | "";
  onChange: (value: RequestStatus | "") => void;
}) {
  return <label>
    Status
    <select value={value} onChange={(event) => onChange(event.target.value as RequestStatus | "")}>
      <option value="">All decisions</option>
      <option value="approved">Approved</option>
      <option value="rejected">Rejected</option>
    </select>
  </label>;
}
