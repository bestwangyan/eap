import apiClient from './client';

export interface SkillInfo {
  id: number;
  tenant_id: number;
  name: string;
  description: string;
  version: string;
  author: string;
  tools: string[];
  tags: string[];
  trigger_keywords: string[];
  original_filename: string;
  is_active: boolean;
  mode?: 'prompt' | 'agent';
  created_at: string;
  skill_content?: string;
  prompt?: string;
}

export interface CreateSkillData {
  name: string;
  description?: string;
  version?: string;
  author?: string;
  tools?: string[];
  tags?: string[];
  trigger_keywords?: string[];
  prompt?: string;
  mode?: 'prompt' | 'agent';
}

export async function createSkill(data: CreateSkillData): Promise<{ skill: SkillInfo; message: string }> {
  const res = await apiClient.post('/skills', data);
  return res.data;
}

export async function listSkills(): Promise<{ skills: SkillInfo[] }> {
  const res = await apiClient.get('/skills');
  return res.data;
}

export async function getSkill(id: number): Promise<{ skill: SkillInfo & { skill_content: string; prompt: string } }> {
  const res = await apiClient.get(`/skills/${id}`);
  return res.data;
}

export async function uploadSkill(file: File): Promise<{ skill: SkillInfo; message: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post('/skills/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
  return res.data;
}

export async function updateSkill(id: number, data: Partial<SkillInfo>): Promise<{ skill: SkillInfo }> {
  const res = await apiClient.put(`/skills/${id}`, data);
  return res.data;
}

export async function deleteSkill(id: number): Promise<void> {
  await apiClient.delete(`/skills/${id}`);
}

export async function toggleSkill(id: number, isActive: boolean): Promise<void> {
  await apiClient.post(`/skills/${id}/toggle`, { is_active: isActive });
}
