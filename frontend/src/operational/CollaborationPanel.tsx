import { Inbox, KeyRound, Plus, RotateCcw, Search, Shield, Share2, Trash2, UserCog, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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
import { PagedCatalogSelect } from "../components/PagedCatalogSelect";
import { PaginationControls } from "../components/PaginationControls";
import { PermissionRequestsPanel } from "./PermissionRequestsPanel";

type NoticeSetter = (message: string) => void;
type SubjectType = "user" | "group";
type CollaborationTab = "groups" | "sharing" | "password" | "permissions";

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
  const [groups, setGroups] = useState<AccessGroup[]>([]);
  const [directorySearch, setDirectorySearch] = useState("");
  const [directoryTotal, setDirectoryTotal] = useState(0);
  const [directoryOffset, setDirectoryOffset] = useState(0);
  const [groupSearch, setGroupSearch] = useState("");
  const [groupTotal, setGroupTotal] = useState(0);
  const [groupOffset, setGroupOffset] = useState(0);
  const [members, setMembers] = useState<GroupMembership[]>([]);
  const [memberTotal, setMemberTotal] = useState(0);
  const [memberOffset, setMemberOffset] = useState(0);
  const [bcGrants, setBcGrants] = useState<BusinessCaseGrant[]>([]);
  const [bcGrantTotal, setBcGrantTotal] = useState(0);
  const [bcGrantOffset, setBcGrantOffset] = useState(0);
  const [resourceGrants, setResourceGrants] = useState<ResourceGrant[]>([]);
  const [resourceGrantTotal, setResourceGrantTotal] = useState(0);
  const [resourceGrantOffset, setResourceGrantOffset] = useState(0);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [selectedGroupSnapshot, setSelectedGroupSnapshot] = useState<AccessGroup | null>(null);
  const [selectedBusinessCaseId, setSelectedBusinessCaseId] = useState("");
  const [selectedBusinessCaseSnapshot, setSelectedBusinessCaseSnapshot] = useState<BusinessCase | undefined>();
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [selectedDatasetSnapshot, setSelectedDatasetSnapshot] = useState<DataAsset | undefined>();
  const [subjectType, setSubjectType] = useState<SubjectType>("group");
  const [subjectId, setSubjectId] = useState("");
  const [selectedSubjectSnapshot, setSelectedSubjectSnapshot] = useState<{ id: string; label: string } | undefined>();
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
  const [sharingScope, setSharingScope] = useState<"business-case" | "direct-object">("business-case");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [permissionRequestsReloadKey, setPermissionRequestsReloadKey] = useState(0);

  const refreshDirectory = useCallback(async () => {
    const [directoryPage, groupPage] = await Promise.all([
      api.pageDirectoryUsers({ limit: 30, offset: directoryOffset, search: directorySearch.trim() }),
      api.pageGroups({ limit: 30, offset: groupOffset, search: groupSearch.trim() })
    ]);
    setUsers(directoryPage.items);
    setDirectoryTotal(directoryPage.total);
    setGroups(groupPage.items);
    setGroupTotal(groupPage.total);
  }, [directoryOffset, directorySearch, groupOffset, groupSearch]);

  useEffect(() => {
    setDirectoryOffset(0);
  }, [directorySearch]);

  useEffect(() => {
    setGroupOffset(0);
  }, [groupSearch]);

  const refreshSelectedAccess = useCallback(async (includeAllTabs: boolean) => {
    const selectedDataset = datasets.find((item) => item.id === selectedDatasetId)
      ?? selectedDatasetSnapshot;
    await Promise.all([
      (includeAllTabs || activeTab === "groups") && selectedGroupId
        ? api.pageGroupMembers(selectedGroupId, { limit: 30, offset: memberOffset }).then((page) => {
            setMembers(page.items);
            setMemberTotal(page.total);
          })
        : Promise.resolve(),
      (includeAllTabs || activeTab === "sharing") && selectedBusinessCaseId
        ? api.pageBusinessCaseGrants(selectedBusinessCaseId, {
            limit: 30,
            offset: bcGrantOffset
          }).then((page) => {
            setBcGrants(page.items);
            setBcGrantTotal(page.total);
          })
        : Promise.resolve(),
      (includeAllTabs || activeTab === "sharing") && selectedDatasetId
        ? api.pageResourceGrants(
            selectedDataset?.source_type === "view" ? "data_view" : "dataset",
            selectedDatasetId,
            { limit: 30, offset: resourceGrantOffset }
          ).then((page) => {
            setResourceGrants(page.items);
            setResourceGrantTotal(page.total);
          })
        : Promise.resolve(),
    ]);
  }, [activeTab, bcGrantOffset, datasets, memberOffset, resourceGrantOffset, selectedBusinessCaseId, selectedDatasetId, selectedDatasetSnapshot, selectedGroupId]);

  const refreshAllShare = useCallback(async () => {
    await Promise.all([refreshDirectory(), onRefresh(), refreshSelectedAccess(true)]);
  }, [onRefresh, refreshDirectory, refreshSelectedAccess]);

  async function handleRefresh() {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      if (activeTab === "password") {
        setNotice("Password form does not require remote refresh");
      } else if (activeTab === "permissions") {
        setPermissionRequestsReloadKey((value) => value + 1);
        setNotice("Permission requests refreshed");
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
    const timer = window.setTimeout(() => {
      refreshDirectory().catch(showError);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [refreshDirectory]);

  useEffect(() => {
    if (!selectedGroupId) {
      setMembers([]);
      setMemberTotal(0);
      return;
    }
    api.pageGroupMembers(selectedGroupId, { limit: 30, offset: memberOffset })
      .then((page) => {
        setMembers(page.items);
        setMemberTotal(page.total);
      })
      .catch(showError);
  }, [memberOffset, selectedGroupId]);

  useEffect(() => setMemberOffset(0), [selectedGroupId]);

  useEffect(() => {
    if (!selectedBusinessCaseId) {
      setBcGrants([]);
      setBcGrantTotal(0);
      return;
    }
    api.pageBusinessCaseGrants(selectedBusinessCaseId, {
      limit: 30,
      offset: bcGrantOffset
    }).then((page) => {
      setBcGrants(page.items);
      setBcGrantTotal(page.total);
    }).catch(showError);
  }, [bcGrantOffset, selectedBusinessCaseId]);

  useEffect(() => setBcGrantOffset(0), [selectedBusinessCaseId]);

  useEffect(() => {
    if (!selectedDatasetId) {
      setResourceGrants([]);
      setResourceGrantTotal(0);
      return;
    }
    const dataset = datasets.find((item) => item.id === selectedDatasetId)
      ?? selectedDatasetSnapshot;
    api.pageResourceGrants(
      dataset?.source_type === "view" ? "data_view" : "dataset",
      selectedDatasetId,
      { limit: 30, offset: resourceGrantOffset }
    )
      .then((page) => {
        setResourceGrants(page.items);
        setResourceGrantTotal(page.total);
      }).catch(showError);
  }, [datasets, resourceGrantOffset, selectedDatasetId, selectedDatasetSnapshot]);

  useEffect(() => setResourceGrantOffset(0), [selectedDatasetId]);

  useEffect(() => {
    setSubjectId("");
    setSelectedSubjectSnapshot(undefined);
  }, [subjectType]);

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
      setSelectedGroupSnapshot(group);
      setNotice("Group created");
    } catch (error) { showError(error); }
  }

  async function addMember() {
    try {
      if (!selectedGroupId || !memberUserId) return setNotice("Choose a group and user");
      await api.upsertGroupMember(selectedGroupId, { user_id: memberUserId, membership_role: memberRole });
      const page = await api.pageGroupMembers(selectedGroupId, { limit: 30, offset: memberOffset });
      setMembers(page.items);
      setMemberTotal(page.total);
      setNotice("Group membership updated");
    } catch (error) { showError(error); }
  }

  async function deleteSelectedGroup() {
    const group = groups.find((item) => item.id === selectedGroupId)
      ?? selectedGroupSnapshot;
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
      setBcGrantOffset(0);
      const page = await api.pageBusinessCaseGrants(selectedBusinessCaseId, {
        limit: 30,
        offset: 0
      });
      setBcGrants(page.items);
      setBcGrantTotal(page.total);
      setNotice("Business Case access updated");
    } catch (error) { showError(error); }
  }

  async function grantDataset() {
    try {
      if (!selectedDatasetId || !subjectId) return setNotice("Choose a loose object and subject");
      const dataset = datasets.find((item) => item.id === selectedDatasetId)
        ?? selectedDatasetSnapshot;
      await api.grantResource({
        resource_kind: dataset?.source_type === "view" ? "data_view" : "dataset",
        resource_id: selectedDatasetId, subject_type: subjectType, subject_id: subjectId,
        access_role: resourceRole
      });
      setResourceGrantOffset(0);
      const page = await api.pageResourceGrants(
        dataset?.source_type === "view" ? "data_view" : "dataset",
        selectedDatasetId,
        { limit: 30, offset: 0 }
      );
      setResourceGrants(page.items);
      setResourceGrantTotal(page.total);
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
        <TabButton active={activeTab === "permissions"} icon={<Inbox size={17} />} label="Permission requests" description="Incoming and submitted" onClick={() => setActiveTab("permissions")} />
      </nav>

      {(activeTab === "groups" || activeTab === "sharing") && (
        <div className="panel collaboration-directory-navigation">
          <div>
            <label className="search-field">
              <Search size={16} />
              <input
                aria-label="Search people directory"
                placeholder="Search people by name, login or email"
                value={directorySearch}
                onChange={(event) => setDirectorySearch(event.target.value)}
              />
            </label>
            <PaginationControls
              total={directoryTotal}
              limit={30}
              offset={directoryOffset}
              onOffsetChange={setDirectoryOffset}
              label="people"
            />
          </div>
          <div>
            <label className="search-field">
              <Search size={16} />
              <input
                aria-label="Search access groups"
                placeholder="Search groups"
                value={groupSearch}
                onChange={(event) => setGroupSearch(event.target.value)}
              />
            </label>
            <PaginationControls
              total={groupTotal}
              limit={30}
              offset={groupOffset}
              onOffsetChange={setGroupOffset}
              label="groups"
            />
          </div>
        </div>
      )}

      {activeTab === "sharing" && <div className="collaboration-tab-content" role="region" aria-label="Object sharing">
      <nav className="sharing-scope-tabs" aria-label="Access scope" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={sharingScope === "business-case"}
          className={sharingScope === "business-case" ? "active" : ""}
          onClick={() => setSharingScope("business-case")}
        >
          <Share2 size={17} />
          <span>Business Case access</span>
          <small>Governed roles for a complete Business Case</small>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={sharingScope === "direct-object"}
          className={sharingScope === "direct-object" ? "active" : ""}
          onClick={() => setSharingScope("direct-object")}
        >
          <Shield size={17} />
          <span>Direct object access</span>
          <small>Exceptions for loose datasets and Data Views</small>
        </button>
      </nav>
      {sharingScope === "business-case" && (
      <div className="panel">
        <div className="panel-header"><div><h2>Business Case access</h2><p>Groups are the recommended sharing path.</p></div><Share2 size={18} /></div>
        <div className="collaboration-form-grid">
          <label>Business Case<PagedCatalogSelect
            value={selectedBusinessCaseId}
            onChange={(value, item) => {
              setSelectedBusinessCaseId(value);
              setSelectedBusinessCaseSnapshot(item);
            }}
            loadPage={(query) => api.pageBusinessCases({ ...query, manageable_only: true })}
            getId={(item) => item.id}
            getLabel={(item) => `${item.name} · ${item.access_role}`}
            selectedItem={selectedBusinessCaseSnapshot}
            emptyLabel="Choose a manageable case"
            searchPlaceholder="Search Business Cases"
          /></label>
          <SubjectFields type={subjectType} id={subjectId} selectedItem={selectedSubjectSnapshot} onType={setSubjectType} onId={(value, item) => {
            setSubjectId(value);
            setSelectedSubjectSnapshot(item);
          }} />
          <label>Access level<select value={bcRole} onChange={(event) => setBcRole(event.target.value as BusinessCase["access_role"])}>
            <option value="report_viewer">Report viewer</option><option value="reader">Reader</option><option value="contributor">Contributor</option><option value="manager">Manager</option><option value="owner">Owner</option>
          </select></label>
          <button className="primary-button" type="button" onClick={grantBusinessCase}><Share2 size={15} /> Grant access</button>
        </div>
        <GrantList
          grants={bcGrants}
          users={users}
          groups={groups}
          targetName={(businessCases.find((item) => item.id === selectedBusinessCaseId) ?? selectedBusinessCaseSnapshot)?.name}
          targetKind="Business Case"
          onRemove={async (grantId) => {
          try {
            await api.revokeBusinessCaseGrant(selectedBusinessCaseId, grantId);
            setBcGrants((current) => current.filter((item) => item.id !== grantId));
            setBcGrantTotal((current) => Math.max(0, current - 1));
            setNotice("Grant revoked");
          } catch (error) { showError(error); }
          }}
        />
        <PaginationControls total={bcGrantTotal} limit={30} offset={bcGrantOffset} onOffsetChange={setBcGrantOffset} label="Business Case grants" />
        {selectedBusinessCaseId && (isAdmin || (businessCases.find((item) => item.id === selectedBusinessCaseId) ?? selectedBusinessCaseSnapshot)?.access_role === "owner") && <div className="collaboration-form-grid compact ownership-transfer">
          <label>Transfer ownership to<PagedCatalogSelect
            value={transferOwnerId}
            onChange={setTransferOwnerId}
            loadPage={(query) => api.pageDirectoryUsers(query)}
            getId={(user) => user.id}
            getLabel={(user) => `${user.display_name} · ${user.email}`}
            emptyLabel="Choose new owner"
            searchPlaceholder="Search users"
          /></label>
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
      )}

      {sharingScope === "direct-object" && (
      <div className="panel">
          <div className="panel-header"><div><h2>Direct object access</h2><p>Exception path for loose datasets and Data Views only.</p></div><Shield size={18} /></div>
          <div className="collaboration-form-grid">
            <label>Loose object<PagedCatalogSelect
              value={selectedDatasetId}
              onChange={(value, item) => {
                setSelectedDatasetId(value);
                setSelectedDatasetSnapshot(item);
              }}
              loadPage={(query) => api.pageDatasets({
                ...query,
                summary: true,
                families: true,
                include_deleted: false,
                owned_only: !isAdmin
              })}
              getId={(item) => item.id}
              getLabel={(item) => `${item.name} · ${item.source_type}`}
              selectedItem={selectedDatasetSnapshot}
              emptyLabel="Choose dataset or view"
              searchPlaceholder="Search loose data objects"
            /></label>
            <SubjectFields type={subjectType} id={subjectId} selectedItem={selectedSubjectSnapshot} onType={setSubjectType} onId={(value, item) => {
              setSubjectId(value);
              setSelectedSubjectSnapshot(item);
            }} />
            <label>Access level<select value={resourceRole} onChange={(event) => setResourceRole(event.target.value as typeof resourceRole)}><option value="reader">Reader</option><option value="editor">Editor</option><option value="owner">Owner</option></select></label>
            <button className="secondary-button" type="button" onClick={grantDataset}><Share2 size={15} /> Grant exception</button>
          </div>
          <GrantList
            grants={resourceGrants}
            users={users}
            groups={groups}
            targetName={(datasets.find((item) => item.id === selectedDatasetId) ?? selectedDatasetSnapshot)?.name}
            targetKind={(datasets.find((item) => item.id === selectedDatasetId) ?? selectedDatasetSnapshot)?.source_type === "view" ? "Data View" : "Dataset"}
            onRemove={async (grantId) => {
            try {
              await api.revokeResourceGrant(grantId);
              setResourceGrants((current) => current.filter((item) => item.id !== grantId));
              setResourceGrantTotal((current) => Math.max(0, current - 1));
              setNotice("Grant revoked");
            } catch (error) { showError(error); }
            }}
          />
          <PaginationControls total={resourceGrantTotal} limit={30} offset={resourceGrantOffset} onOffsetChange={setResourceGrantOffset} label="direct resource grants" />
      </div>
      )}
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
          <label>Manage group<PagedCatalogSelect
            value={selectedGroupId}
            onChange={(value, item) => {
              setSelectedGroupId(value);
              setSelectedGroupSnapshot(item ?? null);
            }}
            loadPage={(query) => api.pageGroups(query)}
            getId={(item) => item.id}
            getLabel={(item) => `${item.name}${item.is_active ? "" : " (inactive)"}`}
            selectedItem={selectedGroupSnapshot ?? undefined}
            emptyLabel="Choose group"
            searchPlaceholder="Search groups"
          /></label>
          <button className="danger-button" type="button" disabled={!selectedGroupId} onClick={deleteSelectedGroup}><Trash2 size={15} /> Delete group</button>
          </div>
          {selectedGroupId && <>
            <div className="collaboration-form-grid compact">
              <label>User<PagedCatalogSelect
                value={memberUserId}
                onChange={setMemberUserId}
                loadPage={(query) => api.pageDirectoryUsers(query)}
                getId={(item) => item.id}
                getLabel={(item) => `${item.display_name} · ${item.email}`}
                emptyLabel="Choose user"
                searchPlaceholder="Search users"
              /></label>
              <label>Membership<select value={memberRole} onChange={(event) => setMemberRole(event.target.value as "member" | "manager")}><option value="member">Member</option><option value="manager">Group manager</option></select></label>
              <button className="secondary-button" type="button" onClick={addMember}>Add / update</button>
            </div>
            <div className="access-list">{members.map((member) => <div key={member.id}><span><strong>{subjectLabel("user", member.user_id, users, groups)}</strong><small>{member.membership_role}</small></span>{member.membership_role !== "owner" && <button className="icon-button" type="button" aria-label="Remove member" onClick={async () => {
              try {
                await api.removeGroupMember(selectedGroupId, member.user_id);
                const page = await api.pageGroupMembers(selectedGroupId, { limit: 30, offset: memberOffset });
                setMembers(page.items);
                setMemberTotal(page.total);
                setNotice("Member removed");
              } catch (error) { showError(error); }
            }}><Trash2 size={14} /></button>}</div>)}</div>
            <PaginationControls total={memberTotal} limit={30} offset={memberOffset} onOffsetChange={setMemberOffset} label="members" />
          </>}
        </div>

      </div>

      {isAdmin && <AdminUsers setNotice={setNotice} />}
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
      {activeTab === "permissions" && (
        <div className="collaboration-tab-content" role="region" aria-label="Permission requests">
          <PermissionRequestsPanel
            setNotice={setNotice}
            reloadKey={permissionRequestsReloadKey}
          />
        </div>
      )}
    </section>
  );
}

function TabButton({ active, icon, label, description, onClick }: { active: boolean; icon: ReactNode; label: string; description: string; onClick: () => void }) {
  return <button type="button" className={active ? "active" : ""} onClick={onClick} aria-current={active ? "page" : undefined}>{icon}<span>{label}</span><small>{description}</small></button>;
}

function SubjectFields({ type, id, selectedItem, onType, onId }: {
  type: SubjectType;
  id: string;
  selectedItem?: { id: string; label: string };
  onType: (value: SubjectType) => void;
  onId: (value: string, item?: { id: string; label: string }) => void;
}) {
  return <><label>Subject type<select value={type} onChange={(event) => onType(event.target.value as SubjectType)}><option value="group">Group</option><option value="user">User</option></select></label>
    <label>Subject<PagedCatalogSelect
      value={id}
      onChange={onId}
      loadPage={async (query) => {
        if (type === "group") {
          const page = await api.pageGroups(query);
          return {
            ...page,
            items: page.items.map((item) => ({ id: item.id, label: item.name }))
          };
        }
        const page = await api.pageDirectoryUsers(query);
        return {
          ...page,
          items: page.items.map((item) => ({
            id: item.id,
            label: item.display_name || item.email
          }))
        };
      }}
      getId={(item) => item.id}
      getLabel={(item) => item.label}
      selectedItem={selectedItem}
      emptyLabel="Choose subject"
      searchPlaceholder={type === "group" ? "Search groups" : "Search users"}
      reloadKey={type}
    /></label></>;
}

function GrantList({ grants, users, groups, targetName, targetKind, onRemove }: {
  grants: Array<BusinessCaseGrant | ResourceGrant>; users: DirectoryUser[]; groups: AccessGroup[];
  targetName?: string;
  targetKind: string;
  onRemove: (grantId: string) => void;
}) {
  if (!grants.length) return <div className="empty-state">No explicit grants for the selected scope.</div>;
  return <div className="access-list">{grants.map((grant) => {
    const isBusinessCaseGrant = "business_case_name" in grant;
    const resolvedSubjectName = isBusinessCaseGrant && grant.subject_name
      ? grant.subject_name
      : subjectLabel(grant.subject_type, grant.subject_id, users, groups);
    const resolvedTargetName = isBusinessCaseGrant
      ? grant.business_case_name || targetName
      : targetName;
    const subjectDetail = isBusinessCaseGrant && grant.subject_email
      ? grant.subject_email
      : grant.subject_type === "group" ? "Access group" : "User";
    return <div className="access-grant-row" key={grant.id}>
      <span className="access-grant-subject">
        <small>{grant.subject_type === "group" ? "Group" : "User"}</small>
        <strong>{resolvedSubjectName}</strong>
        <small>{subjectDetail}</small>
      </span>
      <span className="access-grant-arrow" aria-hidden="true">→</span>
      <span className="access-grant-permission">
        <small>Has access as</small>
        <strong>{formatAccessRole(grant.access_role)}</strong>
        <small>{targetKind}{resolvedTargetName ? ` · ${resolvedTargetName}` : ""}{grant.expires_at ? ` · expires ${new Date(grant.expires_at).toLocaleString()}` : ""}</small>
      </span>
      <button className="icon-button" type="button" aria-label={`Revoke ${grant.access_role} access for ${resolvedSubjectName}`} onClick={() => onRemove(grant.id)}><Trash2 size={14} /></button>
    </div>;
  })}</div>;
}

function AdminUsers({ setNotice }: { setNotice: NoticeSetter }) {
  const [users, setUsers] = useState<DirectoryUser[]>([]);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true);
      api.pageAdminUsers({ limit: 20, offset, search: query.trim() })
        .then((page) => {
          setUsers(page.items);
          setTotal(page.total);
        })
        .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load users"))
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [offset, query, refreshKey, setNotice]);

  useEffect(() => setOffset(0), [query]);

  async function save(user: DirectoryUser, roles: string[], active: boolean) {
    try { await api.updateAdminUser(user.user_id ?? user.id, { roles, is_active: active }); setRefreshKey((value) => value + 1); setNotice("User permissions updated; existing sessions were invalidated"); }
    catch (error) { setNotice(error instanceof Error ? error.message : "User update failed"); }
  }
  return <div className="panel"><div className="panel-header"><div><h2>Application administration</h2><p>All registered users and platform roles.</p></div><UserCog size={18} /></div>
    <label className="search-field"><Search size={16} /><input aria-label="Search registered users" placeholder="Search users" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
    <div className="admin-user-list">{users.map((user) => <AdminUserRow key={user.user_id ?? user.id} user={user} onSave={save} setNotice={setNotice} />)}</div>
    <PaginationControls total={total} limit={20} offset={offset} onOffsetChange={setOffset} disabled={loading} label="users" />
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

function formatAccessRole(role: string) {
  return role
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
