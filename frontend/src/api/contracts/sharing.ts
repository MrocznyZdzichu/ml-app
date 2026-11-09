import type { BusinessCase } from "./businessCases";

export type DirectoryUser = {
  id: string;
  user_id?: string;
  login_name: string;
  email: string;
  display_name: string;
  roles?: string[];
  is_active: boolean;
  is_technical?: boolean;
  session_version?: number;
  created_at?: string;
};

export type AccessGroup = {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  owner_id: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type GroupMembership = {
  id: string;
  group_id: string;
  user_id: string;
  membership_role: "member" | "manager" | "owner";
  added_by: string;
  created_at: string;
};

export type BusinessCaseGrant = {
  id: string;
  business_case_id: string;
  subject_type: "user" | "group";
  subject_id: string;
  access_role: BusinessCase["access_role"];
  granted_by: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  subject_name: string;
  subject_email: string;
  business_case_name: string;
};

export type ResourceGrant = {
  id: string;
  resource_kind: "dataset" | "data_view" | "analysis" | "report";
  resource_id: string;
  subject_type: "user" | "group";
  subject_id: string;
  access_role: "reader" | "editor" | "owner";
  granted_by: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
};
