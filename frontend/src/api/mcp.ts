import apiClient from './client';

export interface MCPServerInfo {
  id: number;
  tenant_id: number;
  name: string;
  description: string;
  transport: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  sse_url: string;
  sse_headers: Record<string, string>;
  is_active: boolean;
  connection_status: string;
  last_connected_at: string | null;
  created_at: string;
}

export async function listServers(): Promise<{ servers: MCPServerInfo[] }> {
  const res = await apiClient.get('/mcp/servers');
  return res.data;
}

export async function getServer(id: number): Promise<{ server: MCPServerInfo }> {
  const res = await apiClient.get(`/mcp/servers/${id}`);
  return res.data;
}

export async function createServer(data: Partial<MCPServerInfo>): Promise<{ server: MCPServerInfo }> {
  const res = await apiClient.post('/mcp/servers', data);
  return res.data;
}

export async function updateServer(id: number, data: Partial<MCPServerInfo>): Promise<{ server: MCPServerInfo }> {
  const res = await apiClient.put(`/mcp/servers/${id}`, data);
  return res.data;
}

export async function deleteServer(id: number): Promise<void> {
  await apiClient.delete(`/mcp/servers/${id}`);
}

export async function testConnection(id: number): Promise<{ status: string; message: string }> {
  const res = await apiClient.post(`/mcp/servers/${id}/test`);
  return res.data;
}
