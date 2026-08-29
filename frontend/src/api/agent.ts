import apiClient from './client';
import type { AgentConfig } from '../types/agent';

export async function listAgents(): Promise<{ agents: AgentConfig[]; total: number }> {
  const res = await apiClient.get('/agents');
  return res.data;
}

export async function getAgent(id: number): Promise<{ agent: AgentConfig }> {
  const res = await apiClient.get(`/agents/${id}`);
  return res.data;
}

export async function createAgent(data: Partial<AgentConfig>): Promise<{ agent: AgentConfig }> {
  const res = await apiClient.post('/agents', data);
  return res.data;
}

export async function updateAgent(id: number, data: Partial<AgentConfig>): Promise<{ agent: AgentConfig }> {
  const res = await apiClient.put(`/agents/${id}`, data);
  return res.data;
}

export async function deleteAgent(id: number): Promise<void> {
  await apiClient.delete(`/agents/${id}`);
}
