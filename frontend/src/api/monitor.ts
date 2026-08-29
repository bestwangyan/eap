import apiClient from './client';

export interface TraceEvent {
  id: number;
  trace_id: string;
  parent_run_id?: string;
  run_id: string;
  event_type: string;
  event_name: string;
  thread_id?: string;
  input_data?: Record<string, any>;
  output_data?: Record<string, any>;
  metadata_json?: Record<string, any>;
  error?: string;
  started_at?: string;
  ended_at?: string;
  duration_ms?: number;
  created_at?: string;
}

export interface TraceDetail {
  trace_id: string;
  thread_id?: string;
  total_events: number;
  events: TraceEvent[];
  summary: {
    llm_calls: number;
    tool_calls: number;
    total_duration_ms: number;
    errors: string[];
    total_tokens: number;
  };
}

export async function listTraces(limit = 20): Promise<{ traces: TraceEvent[] }> {
  const res = await apiClient.get('/admin/monitor/traces', { params: { limit } });
  return res.data;
}

export async function getTraceDetail(traceId: string): Promise<TraceDetail> {
  const res = await apiClient.get(`/admin/monitor/traces/${traceId}`);
  return res.data;
}
