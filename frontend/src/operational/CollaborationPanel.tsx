import { KeyRound, Plus, RotateCcw, Shield, Share2, Trash2, UserCog, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api/client";
import type {
  AccessGroup,
  BusinessCase,
  BusinessCaseGrant,
  DataAsset,
  DirectoryUser,
  GroupMembership,
  ResourceGrant,
  UserProfile
} from "../api/client";

type NoticeSetter = (message: string) => void;
type SubjectType = "user" | "group";
type CollaborationTab = "groups" | "sharing" | "password";

export function CollaborationPanel({
  businessCases,
  datasets,
  currentUser,
  onRefresh,
  onRegisterRefresh,
  setNotice
}: {
  businessCases: BusinessCase[];
  datasets: DataAsset[];
  currentUser: UserProfile;
  onRefresh: () => Promise<void>;
  onRegisterRefresh: (handler: (() => Promise<void>) | null) => void;
  setNotice: NoticeSetter;
}) {
  const isAdmin = currentUser.roles.includes("administrator");
  const [users, setUsers] = useState<DirectoryUser[]>([]);
  const [adminUsers, setAdminUsers] = useState<DirectoryUser[]>([]);
  const [groups, setGroups] = useState<AccessGroup[]>([]);
  const [members, setMembers] = useState<GroupMembership[]>([]);
  const [bcGrants, setBcGrants] = useState<BusinessCaseGrant[]>([]);
  const [resourceGrants, setResourceGrants] = useState<ResourceGrant[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [selectedBusinessCaseId, setSelectedBusinessCaseId] = useState("");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [subjectType, setSubjectType] = useState<SubjectType>("group");
  const [subjectId, setSubjectId] = useState("");
  const [bcRole, setBcRole] = useState<BusinessCase["access_role"]>("reader");
  const [resourceRole, setResourceRole] = useState<"reader" | "editor" | "owner">("reader");
  const [groupName, setGroupName] = useState("");
  const [groupDescription, setGroupDescription] = useState("");
  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState<"member" | "manager">("member");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [transferOwnerId, setTransferOwnerId] = useState("");
  const [activeTab, setActiveTab] = useState<CollaborationTab>("groups");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const manageableCases = useMemo(
    () => businessCases.filter((item) => isAdmin || item.access_role === "manager" || item.access_role === "owner"),
    [businessCases, isAdmin]
  );
  const directlyShareable = useMemo(
    () => datasets.filter((item) => isAdmin || item.owner_id === currentUser.user_id),
    [currentUser.user_id, datasets, isAdmin]
  );
  const subjects = subjectType === "group"
    ? groups.map((group) => ({ id: group.id, label: group.name }))
    : users.map((user) => ({ id: user.id, label: user.display_name || user.email }));

  const refreshDirectory = useCallback(async () => {
    const [directory, groupItems] = await Promise.all([api.listDirectoryUsers(), api.listGroups()]);
    setUsers(directory);
    setGroups(groupItems);
    if (isAdmin) setAdminUsers(await api.listAdminUsers());
  }, [isAdmin]);

  const refreshSelectedAccess = useCallback(async (includeAllTabs: boolean) => {
    const selectedDataset = datasets.find((item) => item.id === selectedDatasetId);
    await Promise.all([
      (includeAllTabs || activeTab === "groups") && selectedGroupId
        ? api.listGroupMembers(selectedGroupId).then(setMembers)
        : Promise.resolve(),
      (includeAllTabs || activeTab === "sharing") && selectedBusinessCaseId
        ? api.listBusinessCaseGrants(selectedBusinessCaseId).then(setBcGrants)
        : Promise.resolve(),
      (includeAllTabs || activeTab === "sharing") && selectedDatasetId
        ? api.listResourceGrants(
            selectedDataset?.source_type === "view" ? "data_view" : "dataset",
            selectedDatasetId
          ).then(setResourceGrants)
        : Promise.resolve(),
    ]);
  }, [activeTab, datasets, selectedBusinessCaseId, selectedDatasetId, selectedGroupId]);

  const refreshAllShare = useCallback(async () => {
    await Promise.all([refreshDirectory(), onRefresh(), refreshSelectedAccess(true)]);
  }, [onRefresh, refreshDirectory, refreshSelectedAccess]);

  async function handleRefresh() {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      if (activeTab === "password") {
        setNotice("Password form does not require remote refresh");
      } else {
        await Promise.all([
          refreshDirectory(),
          activeTab === "sharing" ? onRefresh() : Promise.resolve(),
          refreshSelectedAccess(false),
        ]);
        setNotice(`${activeTab === "groups" ? "Groups" : "Sharing"} refreshed`);
      }
    } catch (error) {
      showError(error);
    } finally {
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    onRegisterRefresh(refreshAllShare);
    return () => onRegisterRefresh(null);
  }, [onRegisterRefresh, refreshAllShare]);

  useEffect(() => {
    refreshDirectory().catch(showError);
  }, [refreshDirectory]);

  useEffect(() => {
    if (!selectedGroupId) {
      setMembers([]);
      return;
    }
    api.listGroupMembers(selectedGroupId).then(setMembers).catch(showError);
  }, [selectedGroupId]);

  useEffect(() => {
    if (!selectedBusinessCaseId) {
      setBcGrants([]);
      return;
    }
    api.listBusinessCaseGrants(selectedBusinessCaseId).then(setBcGrants).catch(showError);
  }, [selectedBusinessCaseId]);

  useEffect(() => {
    if (!selectedDatasetId) {
      setResourceGrants([]);
      return;
    }
    const dataset = datasets.find((item) => item.id === selectedDatasetId);
    api.listResourceGrants(dataset?.source_type === "view" ? "data_view" : "dataset", selectedDatasetId)
      .then(setResourceGrants).catch(showError);
  }, [datasets, selectedDatasetId]);

  useEffect(() => {
    if (subjects.length && !subjects.some((item) => item.id === subjectId)) setSubjectId(subjects[0].id);
  }, [subjectType, groups, users]);

  function showError(error: unknown) {
    setNotice(error instanceof Error ? error.message : "Operation failed");
  }

  async function createGroup() {
    try {
      if (!groupName.trim()) return setNotice("Enter a group name");
      const group = await api.createGroup({ name: groupName, description: groupDescription });
      setGroupName("");
      setGroupDescription("");
      await refreshDirectory();
      setSelectedGroupId(group.id);
      setNotice("Group created");
    } catch (error) { showError(error); }
  }

  async function addMember() {
    try {
      if (!selectedGroupId || !memberUserId) return setNotice("Choose a group and user");
      await api.upsertGroupMember(selectedGroupId, { user_id: memberUserId, membership_role: memberRole });
      setMembers(await api.listGroupMembers(selectedGroupId));
      setNotice("Group membership updated");
    } catch (error) { showError(error); }
  }

  async function deleteSelectedGroup() {
    const group = groups.find((item) => item.id === selectedGroupId);
    if (!group) return setNotice("Choose a group to delete");
    if (!window.confirm(`Delete group “${group.name}”? Its access grants will also be removed.`)) return;
    try {
      await api.deleteGroup(group.id);
      setSelectedGroupId("");
      setMembers([]);
      await refreshDirectory();
      setNotice("Group deleted");
    } catch (error) { showError(error); }
  }

  async function grantBusinessCase() {
    try {
      if (!selectedBusinessCaseId || !subjectId) return setNotice("Choose a Business Case and subject");
      await api.grantBusinessCase(selectedBusinessCaseId, {
        subject_type: subjectType, subject_id: subjectId, access_role: bcRole
      });
      setBcGrants(await api.listBusinessCaseGrants(selectedBusinessCaseId));
      setNotice("Business Case access updated");
    } catch (error) { showError(error); }
  }

  async function grantDataset() {
    try {
      if (!selectedDatasetId || !subjectId) return setNotice("Choose a loose object and subject");
      const dataset = datasets.find((item) => item.id === selectedDatasetId);
      await api.grantResource({
        resource_kind: dataset?.source_type === "view" ? "data_view" : "dataset",
        resource_id: selectedDatasetId, subject_type: subjectType, subject_id: subjectId,
        access_role: resourceRole
      });
      setResourceGrants(await api.listResourceGrants(
        dataset?.source_type === "view" ? "data_view" : "dataset", selectedDatasetId
      ));
      setNotice("Direct object access updated");
    } catch (error) { showError(error); }
  }

  async function changePassword() {
    try {
      await api.changePassword({ current_password: currentPassword, new_password: newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setNotice("Password changed. Sign in again with the new password.");
    } catch (error) { showError(error); }
  }

  return (
    <section className="collaboration-screen">
      <div className="catalog-toolbar-actions">
        <button className="secondary-button" type="button" onClick={() => void handleRefresh()} disabled={isRefreshing}>
          <RotateCcw className={isRefreshing ? "run-spinner" : undefined} size={16} />
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <nav className="collaboration-tabs" aria-label="Share settings">
        <TabButton active={activeTab === "groups"} icon={<Users size={17} />} label="Groups" description="Teams and members" onClick={() => setActiveTab("groups")} />
        <TabButton active={activeTab === "sharing"} icon={<Share2 size={17} />} label="Object sharing" description="Business Cases and data" onClick={() => setActiveTab("sharing")} />
        <TabButton active={activeTab === "password"} icon={<KeyRound size={17} />} label="Change password" description="Account security" onClick={() => setActiveTab("password")} />
      </nav>

      {activeTab === "sharing" && <div className="collaboration-tab-content" role="region" aria-label="Object sharing">
      <div className="panel">
        <div className="panel-header"><div><h2>Business Case access</h2><p>Groups are the recommended sharing path.</p></div><Share2 size={18} /></div>
        <div className="collaboration-form-grid">
          <label>Business Case<select value={selectedBusinessCaseId} onChange={(event) => setSelectedBusinessCaseId(event.target.value)}>
            <option value="">Choose a manageable case</option>{manageableCases.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.access_role}</option>)}
          </select></label>
          <SubjectFields type={subjectType} id={subjectId} subjects={subjects} onType={setSubjectType} onId={setSubjectId} />
          <label>Access level<select value={bcRole} onChange={(event) => setBcRole(event.target.value as BusinessCase["access_role"])}>
            <option value="report_viewer">Report viewer</option><option value="reader">Reader</option><option value="contributor">Contributor</option><option value="manager">Manager</option><option value="owner">Owner</option>
          </select></label>
          <button className="primary-button" type="button" onClick={grantBusinessCase}><Share2 size={15} /> Grant access</button>
        </div>
        <GrantList grants={bcGrants} users={users} groups={groups} onRemove={async (grantId) => {
          try { await api.revokeBusinessCaseGrant(selectedBusinessCaseId, grantId); setBcGrants(await api.listBusinessCaseGrants(selectedBusinessCaseId)); setNotice("Grant revoked"); } catch (error) { showError(error); }
        }} />
        {selectedBusinessCaseId && (isAdmin || businessCases.find((item) => item.id === selectedBusinessCaseId)?.access_role === "owner") && <div className="collaboration-form-grid compact ownership-transfer">
          <label>Transfer ownership to<select value={transferOwnerId} onChange={(event) => setTransferOwnerId(event.target.value)}><option value="">Choose new owner</option>{users.map((user) => <option key={user.id} value={user.id}>{user.display_name} · {user.email}</option>)}</select></label>
          <button className="secondary-button" type="button" onClick={async () => {
            try {
              if (!transferOwnerId) return setNotice("Choose the new Business Case owner");
              await api.transferBusinessCaseOwnership(selectedBusinessCaseId, { new_owner_id: transferOwnerId });
              await onRefresh();
              setSelectedBusinessCaseId("");
              setNotice("Business Case ownership transferred; historical lineage was preserved");
            } catch (error) { showError(error); }
          }}><UserCog size={15} /> Transfer ownership</button>
        </div>}
      </div>

      <div className="panel">
          <div className="panel-header"><div><h2>Direct object access</h2><p>Exception path for loose datasets and Data Views only.</p></div><Shield size={18} /></div>
          <div className="collaboration-form-grid">
            <label>Loose object<select value={selectedDatasetId} onChange={(event) => setSelectedDatasetId(event.target.value)}><option value="">Choose dataset or view</option>{directlyShareable.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.source_type}</option>)}</select></label>
            <SubjectFields type={subjectType} id={subjectId} subjects={subjects} onType={setSubjectType} onId={setSubjectId} />
            <label>Access level<select value={resourceRole} onChange={(event) => setResourceRole(event.target.value as typeof resourceRole)}><option value="reader">Reader</option><option value="editor">Editor</option><option value="owner">Owner</option></select></label>
            <button className="secondary-button" type="button" onClick={grantDataset}><Share2 size={15} /> Grant exception</button>
          </div>
          <GrantList grants={resourceGrants} users={users} groups={groups} onRemove={async (grantId) => {
            try { await api.revokeResourceGrant(grantId); setResourceGrants(resourceGrants.filter((item) => item.id !== grantId)); setNotice("Grant revoked"); } catch (error) { showError(error); }
          }} />
      </div>
      </div>}

      {activeTab === "groups" && <div className="collaboration-tab-content" role="region" aria-label="Group management">
      <div className="two-column collaboration-group-layout">
        <div className="panel">
          <div className="panel-header"><div><h2>Groups</h2><p>Create stable teams, then grant access to the team.</p></div><Users size={18} /></div>
          <div className="collaboration-form-grid">
            <label>Name<input value={groupName} onChange={(event) => setGroupName(event.target.value)} /></label>
            <label>Description<input value={groupDescription} onChange={(event) => setGroupDescription(event.target.value)} /></label>
            <button className="primary-button" type="button" onClick={createGroup}><Plus size={15} /> Create group</button>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><div><h2>Group members</h2><p>Select a group to manage members and group managers.</p></div><UserCog size={18} /></div>
          <div className="group-selector-row">
          <label>Manage group<select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
            <option value="">Choose group</option>{groups.map((item) => <option key={item.id} value={item.id}>{item.name}{item.is_active ? "" : " (inactive)"}</option>)}
          </select></label>
          <button className="danger-button" type="button" disabled={!selectedGroupId} onClick={deleteSelectedGroup}><Trash2 size={15} /> Delete group</button>
          </div>
          {selectedGroupId && <>
            <div className="collaboration-form-grid compact">
              <label>User<select value={memberUserId} onChange={(event) => setMemberUserId(event.target.value)}><option value="">Choose user</option>{users.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.email}</option>)}</select></label>
              <label>Membership<select value={memberRole} onChange={(event) => setMemberRole(event.target.value as "member" | "manager")}><option value="member">Member</option><option value="manager">Group manager</option></select></label>
              <button className="secondary-button" type="button" onClick={addMember}>Add / update</button>
            </div>
            <div className="access-list">{members.map((member) => <div key={member.id}><span><strong>{subjectLabel("user", member.user_id, users, groups)}</strong><small>{member.membership_role}</small></span>{member.membership_role !== "owner" && <button className="icon-button" type="button" aria-label="Remove member" onClick={async () => {
              try { await api.removeGroupMember(selectedGroupId, member.user_id); setMembers(await api.listGroupMembers(selectedGroupId)); setNotice("Member removed"); } catch (error) { showError(error); }
            }}><Trash2 size={14} /></button>}</div>)}</div>
          </>}
        </div>

      </div>

      {isAdmin && <AdminUsers users={adminUsers} onRefresh={async () => setAdminUsers(await api.listAdminUsers())} setNotice={setNotice} />}
      </div>}

      {activeTab === "password" && <div className="collaboration-tab-content collaboration-password-content" role="region" aria-label="Change password"><div className="panel">
        <div className="panel-header"><div><h2>Change password</h2><p>Changing the password invalidates existing sessions.</p></div><KeyRound size={18} /></div>
        {currentUser.login_name === "root" && currentUser.uses_initial_password && <div className="warning-banner">The technical root account still uses the known initial password.</div>}
        <div className="collaboration-form-grid compact" data-lpignore="true">
          <label>Current password<input type="text" className="password-manager-isolated-input" name="account-security-current" autoComplete="off" autoCapitalize="none" spellCheck={false} data-lpignore="true" data-form-type="other" data-1p-ignore="true" data-bwignore="true" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
          <label>New password<input type="text" className="password-manager-isolated-input" name="account-security-next" autoComplete="off" autoCapitalize="none" spellCheck={false} data-lpignore="true" data-form-type="other" data-1p-ignore="true" data-bwignore="true" minLength={6} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>
          <button className="primary-button" type="button" onClick={changePassword}><KeyRound size={15} /> Change password</button>
        </div>
      </div></div>}
    </section>
  );
}

function TabButton({ active, icon, label, description, onClick }: { active: boolean; icon: ReactNode; label: string; description: string; onClick: () => void }) {
  return <button type="button" className={active ? "active" : ""} onClick={onClick} aria-current={active ? "page" : undefined}>{icon}<span>{label}</span><small>{description}</small></button>;
}

function SubjectFields({ type, id, subjects, onType, onId }: {
  type: SubjectType; id: string; subjects: Array<{ id: string; label: string }>;
  onType: (value: SubjectType) => void; onId: (value: string) => void;
}) {
  return <><label>Subject type<select value={type} onChange={(event) => onType(event.target.value as SubjectType)}><option value="group">Group</option><option value="user">User</option></select></label>
    <label>Subject<select value={id} onChange={(event) => onId(event.target.value)}><option value="">Choose subject</option>{subjects.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label></>;
}

function GrantList({ grants, users, groups, onRemove }: {
  grants: Array<BusinessCaseGrant | ResourceGrant>; users: DirectoryUser[]; groups: AccessGroup[];
  onRemove: (grantId: string) => void;
}) {
  if (!grants.length) return <div className="empty-state">No explicit grants for the selected scope.</div>;
  return <div className="access-list">{grants.map((grant) => <div key={grant.id}><span><strong>{subjectLabel(grant.subject_type, grant.subject_id, users, groups)}</strong><small>{grant.subject_type} · {grant.access_role}{grant.expires_at ? ` · expires ${new Date(grant.expires_at).toLocaleString()}` : ""}</small></span><button className="icon-button" type="button" aria-label="Revoke grant" onClick={() => onRemove(grant.id)}><Trash2 size={14} /></button></div>)}</div>;
}

function AdminUsers({ users, onRefresh, setNotice }: { users: DirectoryUser[]; onRefresh: () => Promise<void>; setNotice: NoticeSetter }) {
  async function save(user: DirectoryUser, roles: string[], active: boolean) {
    try { await api.updateAdminUser(user.user_id ?? user.id, { roles, is_active: active }); await onRefresh(); setNotice("User permissions updated; existing sessions were invalidated"); }
    catch (error) { setNotice(error instanceof Error ? error.message : "User update failed"); }
  }
  return <div className="panel"><div className="panel-header"><div><h2>Application administration</h2><p>All registered users and platform roles.</p></div><UserCog size={18} /></div>
    <div className="admin-user-list">{users.map((user) => <AdminUserRow key={user.user_id ?? user.id} user={user} onSave={save} setNotice={setNotice} />)}</div>
  </div>;
}

function AdminUserRow({ user, onSave, setNotice }: { user: DirectoryUser; onSave: (user: DirectoryUser, roles: string[], active: boolean) => Promise<void>; setNotice: NoticeSetter }) {
  const [admin, setAdmin] = useState(user.roles?.includes("administrator") ?? false);
  const [steward, setSteward] = useState(user.roles?.includes("governance_steward") ?? false);
  const [active, setActive] = useState(user.is_active);
  const [resetPassword, setResetPassword] = useState("");
  const userId = user.user_id ?? user.id;
  return <div className="admin-user-row"><span><strong>{user.display_name}</strong><small>{user.login_name} · {user.email}{user.is_technical ? " · technical" : ""}</small></span>
    <label><input type="checkbox" checked={steward} onChange={(event) => setSteward(event.target.checked)} /> Governance steward</label>
    <label><input type="checkbox" checked={admin} disabled={userId === "root"} onChange={(event) => setAdmin(event.target.checked)} /> Administrator</label>
    <label><input type="checkbox" checked={active} disabled={userId === "root"} onChange={(event) => setActive(event.target.checked)} /> Active</label>
    <button className="secondary-button compact-button" type="button" onClick={() => onSave(user, ["user", ...(steward ? ["governance_steward"] : []), ...(admin ? ["administrator"] : [])], active)}>Save</button>
    <div className="password-reset"><input type="password" minLength={6} placeholder="New password" value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} /><button className="secondary-button compact-button" type="button" onClick={async () => {
      try { await api.resetUserPassword(userId, resetPassword); setResetPassword(""); setNotice("Password reset; existing sessions were invalidated"); } catch (error) { setNotice(error instanceof Error ? error.message : "Password reset failed"); }
    }}>Reset</button></div>
  </div>;
}

function subjectLabel(type: string, id: string, users: DirectoryUser[], groups: AccessGroup[]) {
  return type === "group"
    ? groups.find((item) => item.id === id)?.name ?? id
    : users.find((item) => item.id === id || item.user_id === id)?.display_name ?? id;
}
