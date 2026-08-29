import apiClient from './client';

// ============ 模型供应商管理 ============

export interface ModelProviderInfo {
  id: number;
  name: string;
  provider: string;
  api_key?: string;
  api_base?: string;
  model_name: string;
  description: string;
  is_active: boolean;
  is_default: boolean;
  sort_order: number;
}

export interface AvailableModel {
  id: number;
  name: string;
  provider: string;
  model_name: string;
  description: string;
  is_default: boolean;
}

export async function listModelProviders(): Promise<{ models: ModelProviderInfo[] }> {
  const res = await apiClient.get('/admin/models');
  return res.data;
}

export async function createModelProvider(data: Partial<ModelProviderInfo>): Promise<{ model: ModelProviderInfo }> {
  const res = await apiClient.post('/admin/models', data);
  return res.data;
}

export async function updateModelProvider(id: number, data: Partial<ModelProviderInfo>): Promise<{ model: ModelProviderInfo }> {
  const res = await apiClient.put(`/admin/models/${id}`, data);
  return res.data;
}

export async function deleteModelProvider(id: number): Promise<void> {
  await apiClient.delete(`/admin/models/${id}`);
}

// ============ 公开接口 ============

export async function listAvailableModels(): Promise<{ models: AvailableModel[]; default_id: number | null }> {
  const res = await apiClient.get('/models/available');
  return res.data;
}
