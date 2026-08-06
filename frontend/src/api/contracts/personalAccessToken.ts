export type PersonalAccessToken = {
  id: string;
  user_id: string;
  name: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
};

export type CreatedPersonalAccessToken = PersonalAccessToken & {
  token: string;
};
