import { create } from 'zustand';
import type { ChatMessage, ChatThread } from '../types/chat';
import { streamChat } from '../api/chat';
import apiClient from '../api/client';

interface ChatState {
  messages: Record<string, ChatMessage[]>;
  currentThreadId: string | null;
  isStreaming: boolean;
  abortController: AbortController | null;
  selectedModelId: number | null;
  selectedAgentId: number | null;
  threads: ChatThread[];

  sendMessage: (content: string, threadId: string, modelId?: number | null, agentId?: number | null) => Promise<void>;
  cancelStream: () => void;
  setThreadId: (threadId: string) => void;
  loadMessages: (threadId: string, messages: ChatMessage[]) => void;
  setModelId: (modelId: number | null) => void;
  setAgentId: (agentId: number | null) => void;
  fetchThreads: () => Promise<void>;
  loadThreadHistory: (threadId: string) => Promise<void>;
  clearThread: (threadId: string) => Promise<void>;
}

let msgId = 0;
function genId(): string { return `msg_${++msgId}_${Date.now()}`; }

export const useChatStore = create<ChatState>((set, get) => ({
  messages: {}, currentThreadId: null, isStreaming: false,
  abortController: null, selectedModelId: null, selectedAgentId: null,
  threads: [],

  fetchThreads: async () => {
    try {
      const res = await apiClient.get('/chat/threads');
      set({ threads: res.data.threads });
    } catch { /* ignore */ }
  },

  sendMessage: async (content, threadId, modelId, agentId) => {
    const userMsg: ChatMessage = { id: genId(), role: 'user', content, timestamp: new Date().toISOString() };
    const assistantMsg: ChatMessage = { id: genId(), role: 'assistant', content: '', timestamp: new Date().toISOString(), isStreaming: true };

    set((s) => {
      const existing = s.messages[threadId] || [];
      return { messages: { ...s.messages, [threadId]: [...existing, userMsg, assistantMsg] }, currentThreadId: threadId, isStreaming: true };
    });

    // 使用函数来获取当前有效的 threadId（新对话时会在收到 thread_id 事件后更新）
    const _tid = () => get().currentThreadId || threadId;

    const ctrl = streamChat(content, threadId, modelId ?? get().selectedModelId, agentId ?? get().selectedAgentId, {
      onThreadId: (newThreadId) => {
        if (newThreadId && newThreadId !== threadId) {
          set((s) => {
            const msgs = { ...s.messages };
            if (msgs[threadId]) {
              msgs[newThreadId] = msgs[threadId];
              delete msgs[threadId];
            }
            return { messages: msgs, currentThreadId: newThreadId };
          });
        }
      },
      onToken: (text) => set((s) => {
        const tid = _tid();
        const msgs = [...(s.messages[tid] || [])];
        const last = msgs[msgs.length - 1];
        if (last?.isStreaming) msgs[msgs.length - 1] = { ...last, content: last.content + text };
        return { messages: { ...s.messages, [tid]: msgs } };
      }),
      onToolStart: (toolName, input) => set((s) => {
        const tid = _tid();
        const msgs = [...(s.messages[tid] || [])];
        msgs.push({ id: genId(), role: 'tool', content: `调用工具: ${toolName}`, toolName, toolInput: input, timestamp: new Date().toISOString() });
        return { messages: { ...s.messages, [tid]: msgs } };
      }),
      onToolEnd: (toolName, output) => set((s) => {
        const tid = _tid();
        const msgs = [...(s.messages[tid] || [])];
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'tool' && msgs[i].toolName === toolName) {
            msgs[i] = { ...msgs[i], toolOutput: output, content: `工具完成: ${toolName}` }; break;
          }
        }
        return { messages: { ...s.messages, [tid]: msgs } };
      }),
      onError: (error) => set((s) => {
        const tid = _tid();
        const msgs = [...(s.messages[tid] || [])];
        // 丢弃空内容的流式助手占位消息（如输入被安全围栏拦截，LLM 未启动）
        const last = msgs[msgs.length - 1];
        if (last?.isStreaming && !last.content) msgs.pop();
        msgs.push({ id: genId(), role: 'system', content: `错误: ${error}`, timestamp: new Date().toISOString() });
        return { messages: { ...s.messages, [tid]: msgs }, isStreaming: false, abortController: null };
      }),
      onGuardrail: (message) => set((s) => {
        const tid = _tid();
        const msgs = [...(s.messages[tid] || []), { id: genId(), role: 'system', content: message, timestamp: new Date().toISOString() }];
        return { messages: { ...s.messages, [tid]: msgs } };
      }),
      onDone: (meta) => {
        set((s) => {
          const tid = _tid();
          const msgs = [...(s.messages[tid] || [])];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            msgs[msgs.length - 1] = {
              ...last, isStreaming: false,
              usage: meta?.usage, traceId: meta?.traceId,
            };
          }
          return { messages: { ...s.messages, [tid]: msgs }, isStreaming: false, abortController: null };
        });
        get().fetchThreads();
      },
    });
    set({ abortController: ctrl });
  },

  cancelStream: () => { get().abortController?.abort(); set({ isStreaming: false, abortController: null }); },
  setThreadId: (id) => set({ currentThreadId: id }),
  loadMessages: (threadId, messages) => set((s) => ({ messages: { ...s.messages, [threadId]: messages } })),
  setModelId: (id) => set({ selectedModelId: id }),
  setAgentId: (id) => set({ selectedAgentId: id }),

  loadThreadHistory: async (threadId) => {
    try {
      const res = await apiClient.get(`/chat/threads/${threadId}`);
      const data = res.data;
      if (data.messages && data.messages.length > 0) {
        const msgs: ChatMessage[] = data.messages.map((m: any) => ({
          id: `${m.role}_${Date.now()}_${Math.random()}`,
          role: m.role, content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
          timestamp: new Date().toISOString(),
        }));
        set((s) => ({ messages: { ...s.messages, [threadId]: msgs } }));
      }
    } catch { /* thread may not exist yet */ }
  },

  clearThread: async (threadId) => {
    try { await apiClient.delete(`/chat/threads/${threadId}`); } catch { /* ignore */ }
    set((s) => {
      const msgs = { ...s.messages }; delete msgs[threadId];
      return { messages: msgs, threads: s.threads.filter(t => t.thread_id !== threadId) };
    });
  },
}));
