export interface AgentConfig {
  id: number;
  tenant_id: number;
  name: string;
  description: string;
  model: string;
  model_provider_id?: number | null;
  system_prompt: string;
  tools_config: string[];
  skills: string[];
  mcp_servers: string[];
  knowledge_collections: number[];
  permission_mode: 'default' | 'acceptEdits' | 'dontAsk';
  backend?: 'local' | 'container';
  max_turns: number;
  is_active: boolean;
  created_at: string;
}
