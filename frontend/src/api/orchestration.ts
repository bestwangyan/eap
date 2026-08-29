import apiClient from './client';

export interface SubAgentInfo {
  id: number;
  tenant_id: number;
  parent_agent_id: number;
  name: string;
  role_prompt: string;
  tools: string[];
  model?: string;
  mode: 'inline' | 'compiled' | 'async';
  is_active: boolean;
}

export interface CreateSubAgentData {
  name: string;
  role_prompt: string;
  tools?: string[];
  model?: string;
  mode?: 'inline' | 'compiled' | 'async';
}

export async function listSubAgents(agentId: number): Promise<{ sub_agents: SubAgentInfo[] }> {
  const res = await apiClient.get(`/agents/${agentId}/sub-agents`);
  return res.data;
}

export async function createSubAgent(agentId: number, data: CreateSubAgentData): Promise<{ sub_agent: SubAgentInfo }> {
  const res = await apiClient.post(`/agents/${agentId}/sub-agents`, data);
  return res.data;
}

export async function deleteSubAgent(agentId: number, subId: number): Promise<void> {
  await apiClient.delete(`/agents/${agentId}/sub-agents/${subId}`);
}

export async function testOrchestration(agentId: number, message: string): Promise<{
  prompt: string;
  decision: { worker?: string; reason?: string };
  available_workers: string[];
}> {
  const res = await apiClient.post('/orchestration/test', { agent_id: agentId, message });
  return res.data;
}
