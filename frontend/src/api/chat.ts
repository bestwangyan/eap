import type { SSEEvent, TokenUsage } from '../types/chat';

export function streamChat(
  message: string,
  threadId: string,
  modelProviderId: number | null,
  agentId: number | null,
  callbacks: {
    onThreadId: (threadId: string) => void;
    onToken: (text: string) => void;
    onToolStart: (toolName: string, input: string) => void;
    onToolEnd: (toolName: string, output: string) => void;
    onError: (error: string) => void;
    onGuardrail: (message: string) => void;
    onDone: (meta?: { usage?: TokenUsage; traceId?: string }) => void;
  }
): AbortController {
  const controller = new AbortController();
  const token = localStorage.getItem('access_token');

  const body: Record<string, unknown> = { message, thread_id: threadId };
  if (modelProviderId) body.model_provider_id = modelProviderId;
  if (agentId) body.agent_id = agentId;

  fetch('/eap/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`HTTP ${response.status}: ${text}`);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: SSEEvent = JSON.parse(line.slice(6));
              switch (event.type) {
                case 'thread_id':
                  if (event.thread_id) callbacks.onThreadId(event.thread_id);
                  break;
                case 'token':
                  if (event.content) callbacks.onToken(event.content);
                  break;
                case 'tool_start':
                  callbacks.onToolStart(event.tool || 'unknown', event.input || '');
                  break;
                case 'tool_end':
                  callbacks.onToolEnd(event.tool || 'unknown', event.output || '');
                  break;
                case 'error':
                  callbacks.onError(event.message || 'Unknown error');
                  break;
                case 'guardrail':
                  callbacks.onGuardrail(event.message || '触发安全拦截');
                  break;
                case 'done':
                  callbacks.onDone({ usage: event.usage, traceId: event.trace_id });
                  break;
              }
            } catch {
              // 忽略解析错误的行
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError(err.message);
      }
    });

  return controller;
}
