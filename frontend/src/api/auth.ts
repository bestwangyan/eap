import apiClient from './client';
import type { LoginRequest, LoginResponse, RegisterRequest } from '../types/auth';

export async function login(data: LoginRequest): Promise<LoginResponse> {
  const res = await apiClient.post('/auth/login', data);
  return res.data;
}

export async function register(data: RegisterRequest): Promise<{ message: string }> {
  const res = await apiClient.post('/auth/register', data);
  return res.data;
}

export async function refreshToken(refreshToken: string): Promise<LoginResponse> {
  const res = await apiClient.post('/auth/refresh', { refresh_token: refreshToken });
  return res.data;
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
}

export async function getMe() {
  const res = await apiClient.get('/auth/me');
  return res.data;
}
