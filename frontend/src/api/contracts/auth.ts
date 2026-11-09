export type AuthResponse = {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  login_name: string;
};

export type UserProfile = {
  user_id: string;
  email: string;
  display_name: string;
  roles: string[];
  login_name: string;
  is_active: boolean;
  uses_initial_password: boolean;
};
