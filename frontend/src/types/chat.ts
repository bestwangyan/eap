export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  toolName?: string;
  toolInput?: string;
  toolOutput?: string;
  timestamp: string;
  isStreaming?: boolean;
  // 遥测数据（done 事件携带）：trace_id + token 用量
  traceId?: string;
  usage?: TokenUsage;
}

export interface ChatThread {
  id: number;
  thread_id: string;
  title: string;
  agent_id?: number;
  agent_name?: string;
  message_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface SSEEvent {
  type: 'token' | 'tool_start' | 'tool_end' | 'error' | 'done' | 'thread_id' | 'guardrail';
  content?: string;
  tool?: string;
  input?: string;
  output?: string;
  message?: string;
  thread_id?: string;
  full_thread_id?: string;
  usage?: TokenUsage;
  trace_id?: string;
}
