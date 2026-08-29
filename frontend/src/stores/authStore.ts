import { create } from 'zustand';
import type { UserInfo, LoginRequest } from '../types/auth';
import * as authApi from '../api/auth';

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: UserInfo | null;
  permissions: string[];
  loading: boolean;
  initialized: boolean;

  login: (data: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  init: () => Promise<void>;
  hasPermission: (codename: string) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('access_token'),
  refreshToken: localStorage.getItem('refresh_token'),
  user: null,
  permissions: [],
  loading: false,
  initialized: false,

  login: async (data: LoginRequest) => {
    set({ loading: true });
    try {
      const result = await authApi.login(data);
      localStorage.setItem('access_token', result.access_token);
      localStorage.setItem('refresh_token', result.refresh_token);
      set({
        token: result.access_token,
        refreshToken: result.refresh_token,
        user: result.user,
        permissions: result.user.permissions,
        loading: false,
        initialized: true,
      });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  logout: async () => {
    try {
      await authApi.logout();
    } catch {
      // ignore
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    set({
      token: null,
      refreshToken: null,
      user: null,
      permissions: [],
      initialized: true,
    });
  },

  init: async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      set({ initialized: true });
      return;
    }
    try {
      const userInfo = await authApi.getMe();
      set({
        user: userInfo,
        permissions: userInfo.permissions,
        initialized: true,
      });
    } catch {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      set({
        token: null,
        refreshToken: null,
        user: null,
        permissions: [],
        initialized: true,
      });
    }
  },

  hasPermission: (codename: string) => {
    const { permissions } = get();
    return permissions.includes('*:*') || permissions.includes(codename);
  },
}));
