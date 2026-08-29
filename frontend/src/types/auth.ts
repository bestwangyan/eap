export interface UserInfo {
  id: number;
  username: string;
  email: string;
  tenant: string;
  tenant_name?: string;
  roles: string[];
  permissions: string[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserInfo;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  tenant_name: string;
}
