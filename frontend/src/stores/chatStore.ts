import { create } from 'zustand';
import type { ChatMessage, ChatThread } from '../types/chat';
import { streamChat } from '../api/chat';
import apiClient from '../api/client';

export interface PendingApproval {
  approvalId: number;
  toolName: string;
  args: string; // JSON.stringify 后的工具参数（审批卡展示用）
  threadId: string; // interrupt 时刻的 _tid()，持久化防新对话导航竞态
}

interface ChatState {
  messages: Record<string, ChatMessage[]>;
  currentThreadId: string | null;
  isStreaming: boolean;
  abortController: AbortController | null;
  selectedModelId: number | null;
  selectedAgentId: number | null;
  threads: ChatThread[];
  pendingApproval: PendingApproval | null;

  sendMessage: (content: string, threadId: string, modelId?: number | null, agentId?: number | null, resume?: boolean) => Promise<void>;
  resumeChat: (approvalId: number, decision: 'approve' | 'reject') => Promise<void>;
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
  threads: [], pendingApproval: null,

  fetchThreads: async () => {
    try {
      const res = await apiClient.get('/chat/threads');
      set({ threads: res.data.threads });
    } catch { /* ignore */ }
  },

  sendMessage: async (content, threadId, modelId, agentId, resume = false) => {
    const assistantMsg: ChatMessage = { id: genId(), role: 'assistant', content: '', timestamp: new Date().toISOString(), isStreaming: true };

    set((s) => {
      const existing = s.messages[threadId] || [];
      // resume 模式不追加用户气泡（message 为空串，内容来自审批决定）；
      // 新起一轮对话则清掉可能残留的待审批卡（用户已转移注意力）
      const msgs = resume ? existing : [...existing, { id: genId(), role: 'user', content, timestamp: new Date().toISOString() }];
      return {
        messages: { ...s.messages, [threadId]: [...msgs, assistantMsg] },
        currentThreadId: threadId, isStreaming: true,
        pendingApproval: resume ? s.pendingApproval : null,
      };
    });

    // 使用函数来获取当前有效的 threadId（新对话时会在收到 thread_id 事件后更新）
    const _tid = () => get().currentThreadId || threadId;

    const ctrl = streamChat(resume ? '' : content, threadId, modelId ?? get().selectedModelId, agentId ?? get().selectedAgentId, {
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
      onToolStart: (toolName, input, displayName) => set((s) => {
        const tid = _tid();
        const msgs = [...(s.messages[tid] || [])];
        msgs.push({
          id: genId(), role: 'tool', content: `调用工具: ${toolName}`,
          toolName, toolInput: input, displayName,
          timestamp: new Date().toISOString(),
        });
        return { messages: { ...s.messages, [tid]: msgs } };
      }),
      onInterrupt: (approvalId, toolName, args) => set((s) => ({
        // threadId 以 interrupt 时刻的 _tid() 为准并持久化（新对话导航竞态防护）
        pendingApproval: {
          approvalId, toolName,
          args: JSON.stringify(args, null, 2),
          threadId: _tid(),
        },
      })),
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
    }, resume);
    set({ abortController: ctrl });
  },

  resumeChat: async (approvalId, decision) => {
    const p = get().pendingApproval;
    if (!p) return;
    // 立即清除卡片，防双击重复决议（后端已决议的行再决议 → 409）
    set({ pendingApproval: null });
    try {
      await apiClient.post(
        `/workflow/approvals/${approvalId}/${decision === 'reject' ? 'reject' : 'approve'}`,
        {},
      );
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 409 = 已被决议（如双击/他处已处理）：另一路已负责 resume，静默返回
      if (status === 409) return;
      // 决议落库失败：恢复卡片供重试 + 错误提示
      set((s) => {
        const msgs = [...(s.messages[p.threadId] || []), {
          id: genId(), role: 'system',
          content: `审批失败: ${(err as { response?: { data?: { error?: string } } })?.response?.data?.error || (err as Error)?.message || '未知错误'}`,
          timestamp: new Date().toISOString(),
        }];
        return { messages: { ...s.messages, [p.threadId]: msgs }, pendingApproval: p };
      });
      return;
    }
    // 决议成功 → resume 原线程（复用 sendMessage 的 onToken/onTool 回调链）
    await get().sendMessage('', p.threadId, undefined, undefined, true);
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
