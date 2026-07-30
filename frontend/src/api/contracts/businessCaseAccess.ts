export type BusinessCaseAccessRole =
  | "report_viewer"
  | "reader"
  | "contributor"
  | "manager"
  | "owner";

export type BusinessCaseCatalogEntry = {
  id: string;
  name: string;
  status: string;
  access_role: BusinessCaseAccessRole | "";
  request_status: "pending" | "";
};

export type BusinessCaseAccessRequest = {
  id: string;
  business_case_id: string;
  requester_id: string;
  requested_role: BusinessCaseAccessRole;
  justification: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  decided_at: string | null;
  decided_by: string;
  granted_role: BusinessCaseAccessRole | null;
  decision_note: string;
  business_case_name: string;
  requester_display_name: string;
  requester_email: string;
};
