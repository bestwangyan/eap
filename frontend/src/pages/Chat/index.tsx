import { useRef, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Input, Button, Select, Space } from 'antd';
import {
  SendOutlined, StopOutlined, PlusOutlined, DeleteOutlined,
  RightOutlined, DownOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useChatStore } from '../../stores/chatStore';
import { listAvailableModels } from '../../api/admin';
import { listAgents } from '../../api/agent';
import type { AvailableModel } from '../../api/admin';
import type { AgentConfig } from '../../types/agent';
import type { ChatMessage } from '../../types/chat';

/* ============================================================================
   聊天窗口 — "控制台" 设计

   设计意图：EAP 是带完整遥测的企业 Agent 平台（trace/token/工具调用），
   界面用它自己的语言说话：
     - 等宽字体承载一切元数据（TRD 线程号 / TRC 追踪号 / TOK 用量 / 工具名）
     - 每条助手回复带遥测页脚（真实 trace 数据，可溯源）
     - 工具调用默认折叠为单行状态条，降噪
   布局硬约束：消息区是唯一滚动容器（flex:1 + minHeight:0），
   输入区 flexShrink:0 永远钉在视口底部，窗口本身不滚动。
   ============================================================================ */

// 设计 token
const T = {
  ink: '#101828',      // 正文/用户气泡
  ink2: '#475467',     // 次级文字
  ink3: '#98a2b3',     // 元数据
  paper: '#ffffff',
  chrome: '#f7f8fa',
  line: '#e4e7ec',
  signal: '#1d4ed8',   // 信号蓝 — 主色
  signalDark: '#1e40af',
  codeBg: '#0f172a',
  codeTxt: '#e2e8f0',
  amberBg: '#fef3c7',
  amberBd: '#fde68a',
  amberTxt: '#b45309',
  danger: '#dc2626',
  mono: "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace",
};

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/* ---------- 助手回复的遥测页脚（签名元素） ---------- */
function TelemetryFooter({ msg }: { msg: ChatMessage }) {
  const total = msg.usage ? msg.usage.input_tokens + msg.usage.output_tokens : null;
  if (!msg.traceId && !total) return null;
  return (
    <div style={{ marginTop: 8, fontFamily: T.mono, fontSize: 11, color: T.ink3, letterSpacing: 0.4 }}>
      {msg.traceId && <>TRC {msg.traceId}</>}
      {msg.traceId && total && <> · </>}
      {total && <>{total} TOK</>}
    </div>
  );
}

/* ---------- 工具调用：默认折叠的单行状态条 ---------- */
function ToolRow({ msg }: { msg: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const running = !msg.toolOutput;
  return (
    <div style={{
      margin: '6px 0', fontFamily: T.mono, fontSize: 12,
      border: `1px solid ${T.amberBd}`, background: T.amberBg,
      borderRadius: 8, overflow: 'hidden',
    }}>
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '7px 10px', cursor: 'pointer', userSelect: 'none',
          color: T.amberTxt,
        }}
      >
        {open ? <DownOutlined style={{ fontSize: 10 }} /> : <RightOutlined style={{ fontSize: 10 }} />}
        <span style={{ fontWeight: 700, letterSpacing: 1 }}>TOOL</span>
        <span>▸</span>
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {msg.displayName || msg.toolName}
        </span>
        {running ? (
          <span className="eap-pulse">RUNNING</span>
        ) : (
          <span>DONE · {fmtTime(msg.timestamp)}</span>
        )}
      </div>
      {open && (
        <div style={{ borderTop: `1px solid ${T.amberBd}`, padding: '8px 10px', background: 'rgba(255,255,255,0.5)' }}>
          {msg.toolInput && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ color: T.amberTxt, opacity: 0.7, marginBottom: 2 }}>IN</div>
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: T.ink2 }}>{msg.toolInput}</div>
            </div>
          )}
          {msg.toolOutput && (
            <div>
              <div style={{ color: T.amberTxt, opacity: 0.7, marginBottom: 2 }}>OUT</div>
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: T.ink, maxHeight: 220, overflowY: 'auto' }}>
                {msg.toolOutput}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- 消息气泡 ---------- */
function MessageBubble({ msg, agentName }: { msg: ChatMessage; agentName: string }) {
  if (msg.role === 'system') {
    return (
      <div style={{
        margin: '8px 0', fontFamily: T.mono, fontSize: 12, color: T.danger,
        border: `1px solid #fecaca`, background: '#fef2f2', borderRadius: 8, padding: '8px 12px',
      }}>
        ✕ {msg.content}
      </div>
    );
  }

  if (msg.role === 'tool') {
    return <ToolRow msg={msg} />;
  }

  const isUser = msg.role === 'user';

  if (isUser) {
    // 用户：墨色块，右下角 2px 直角是签名
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '10px 0' }}>
        <div style={{ maxWidth: '78%' }}>
          <div style={{
            background: T.ink, color: '#fff', padding: '10px 16px',
            borderRadius: '12px 12px 2px 12px',
            lineHeight: 1.7, wordBreak: 'break-word', whiteSpace: 'pre-wrap',
          }}>
            {msg.content}
          </div>
          <div style={{
            textAlign: 'right', marginTop: 4, fontFamily: T.mono,
            fontSize: 11, color: T.ink3,
          }}>
            {fmtTime(msg.timestamp)}
          </div>
        </div>
      </div>
    );
  }

  // 助手：左信号条 + 头部标识 + 正文 + 遥测页脚
  return (
    <div style={{ display: 'flex', gap: 12, padding: '14px 0' }}>
      <div style={{
        width: 3, borderRadius: 2, background: msg.isStreaming ? T.signal : T.line,
        flexShrink: 0, alignSelf: 'stretch', minHeight: 32,
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6,
        }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: T.ink, letterSpacing: 0.3 }}>
            EAP<span style={{ color: T.ink3, fontWeight: 400 }}> · </span>{agentName || '助手'}
          </span>
          <span style={{ fontFamily: T.mono, fontSize: 11, color: T.ink3 }}>
            {fmtTime(msg.timestamp)}
          </span>
        </div>
        <div style={{ fontSize: 15, lineHeight: 1.75, color: T.ink, wordBreak: 'break-word' }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ children }) => (
                <table style={{ borderCollapse: 'collapse', width: '100%', margin: '10px 0', fontSize: 14 }}>
                  {children}
                </table>
              ),
              thead: ({ children }) => <thead style={{ background: T.chrome }}>{children}</thead>,
              th: ({ children }) => (
                <th style={{ border: `1px solid ${T.line}`, padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td style={{ border: `1px solid ${T.line}`, padding: '8px 12px' }}>{children}</td>
              ),
              code({ className, children, ...props }) {
                const _ref = (props as Record<string, unknown>).ref;
                void _ref;
                const isInline = !className;
                return isInline ? (
                  <code style={{
                    background: '#eef1f5', padding: '1px 5px', borderRadius: 4,
                    fontFamily: T.mono, fontSize: '0.9em', color: T.ink,
                  }}>
                    {children}
                  </code>
                ) : (
                  <pre style={{
                    background: T.codeBg, color: T.codeTxt, padding: 14, borderRadius: 8,
                    overflow: 'auto', fontFamily: T.mono, fontSize: 13, lineHeight: 1.6,
                  }}>
                    <code className={className}>{children}</code>
                  </pre>
                );
              },
            }}
          >
            {msg.content || ''}
          </ReactMarkdown>
          {msg.isStreaming && <span className="stream-caret" />}
        </div>
        <TelemetryFooter msg={msg} />
      </div>
    </div>
  );
}

/* ---------- 空状态：控制台就绪页 ---------- */
function ConsoleReady() {
  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 0,
    }}>
      <div style={{ fontFamily: T.mono, fontSize: 11, letterSpacing: 4, color: T.ink3 }}>
        EAP · AGENT CONSOLE
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: T.ink, marginTop: 12, letterSpacing: 1 }}>
        准备就绪
      </div>
      <div style={{ fontFamily: T.mono, fontSize: 13, color: T.ink2, marginTop: 10 }}>
        选择 Agent 与模型，输入第一条指令
      </div>
      <div style={{ fontFamily: T.mono, fontSize: 11, color: T.ink3, marginTop: 28, lineHeight: 2, textAlign: 'center' }}>
        <div>— 7 项内置工具 · 计算 / 时间 / 搜索 / 代码执行 / 知识库 / 记忆 —</div>
        <div>— 子 Agent 与 Skill 按需调度 · 全程遥测可溯源 —</div>
      </div>
    </div>
  );
}

/* ---------- 聊天页 ---------- */
export default function ChatPage() {
  const { threadId } = useParams<{ threadId: string }>();
  const navigate = useNavigate();
  const [inputValue, setInputValue] = useState('');
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages, currentThreadId, isStreaming, selectedModelId, selectedAgentId,
    pendingApproval,
    sendMessage, resumeChat, cancelStream, setThreadId, setModelId, setAgentId, fetchThreads,
    loadThreadHistory, clearThread,
  } = useChatStore();

  const activeThreadId = threadId || currentThreadId || 'default';
  const isNewThread = activeThreadId === 'default';
  const currentMessages = messages[activeThreadId] || [];
  const agentName = agents.find((a) => a.id === selectedAgentId)?.name;
  const modelName = availableModels.find((m) => m.id === selectedModelId)?.name;

  useEffect(() => {
    listAvailableModels().then((res) => { setAvailableModels(res.models); if (!selectedModelId && res.default_id) setModelId(res.default_id); }).catch(() => {});
    listAgents().then((res) => { setAgents(res.agents); if (res.agents.length > 0 && !selectedAgentId) setAgentId(res.agents[0].id); }).catch(() => {});
    fetchThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (threadId) { setThreadId(threadId); loadThreadHistory(threadId); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  // 新对话时，收到后端 thread_id 后自动跳转到该 URL
  useEffect(() => {
    if (isNewThread && currentThreadId && currentThreadId !== 'default') {
      navigate(`/chat/${currentThreadId}`, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentThreadId]);

  // 滚动锚定：直接写 scrollTop，只滚消息容器，绝不影响窗口
  useEffect(() => {
    if (!autoScroll) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [currentMessages, autoScroll]);

  // 用户上翻历史时暂停自动跟随，接近底部 120px 内恢复
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
  };

  const handleSend = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || isStreaming) return;
    setInputValue('');
    setAutoScroll(true);
    await sendMessage(trimmed, isNewThread ? '' : activeThreadId);
    if (isNewThread) setTimeout(() => fetchThreads(), 1500);
  };

  const handleNewChat = () => {
    setThreadId('default'); setInputValue(''); navigate('/chat');
  };

  const handleClearThread = async () => {
    if (isNewThread) return;
    await clearThread(activeThreadId);
    navigate('/chat');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const metaLabel = (t: string) => (
    <span style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: 1.5, color: T.ink3 }}>{t}</span>
  );

  return (
    <div style={{
      height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column',
      width: '100%', maxWidth: 880, margin: '0 auto', padding: '0 20px',
    }}>
      {/* 顶部：Agent / 模型选择 + 线程操作 */}
      <div style={{
        flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 12, padding: '10px 0', borderBottom: `1px solid ${T.line}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          {metaLabel('AGENT')}
          <Select
            value={selectedAgentId}
            onChange={(v) => setAgentId(v)}
            placeholder="选择 Agent"
            size="middle"
            style={{ width: 170 }}
            options={agents.filter((a) => a.is_active).map((a) => ({ label: a.name, value: a.id }))}
          />
          {metaLabel('MODEL')}
          <Select
            value={selectedModelId}
            onChange={(v) => setModelId(v)}
            placeholder="选择模型"
            size="middle"
            style={{ width: 170 }}
            options={availableModels.map((m) => ({ label: m.name + (m.is_default ? ' · DEF' : ''), value: m.id }))}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {!isNewThread && (
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.ink3 }}>
              TRD {activeThreadId.slice(0, 8)}
            </span>
          )}
          <Button size="small" icon={<PlusOutlined />} onClick={handleNewChat}>新对话</Button>
          {!isNewThread && (
            <Button size="small" danger icon={<DeleteOutlined />} onClick={handleClearThread}>清除</Button>
          )}
        </div>
      </div>

      {/* 消息区：唯一的滚动容器 */}
      <div
        ref={scrollRef}
        className="messages-scroll"
        onScroll={handleScroll}
        style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 0 8px' }}
      >
        {currentMessages.length === 0 ? (
          <ConsoleReady />
        ) : (
          currentMessages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} agentName={agentName || ''} />
          ))
        )}
      </div>

      {/* 输入区：flexShrink 0，永远钉在底部 */}
      <div style={{
        flexShrink: 0, background: T.paper, borderTop: `1px solid ${T.line}`,
        padding: '12px 0 10px', position: 'relative', zIndex: 2,
      }}>
        {pendingApproval && (
          <div style={{
            border: `1px solid ${T.amberBd}`, background: T.amberBg,
            borderRadius: 10, padding: '10px 14px', marginBottom: 10,
            fontFamily: T.mono, fontSize: 12,
          }}>
            <div style={{ fontWeight: 700, marginBottom: 4, color: T.amberTxt }}>
              ⏸ 待人工审批 · {pendingApproval.toolName}
            </div>
            <div style={{
              color: T.ink2, marginBottom: 8, whiteSpace: 'pre-wrap',
              maxHeight: 120, overflowY: 'auto',
            }}>
              {pendingApproval.args}
            </div>
            <Space>
              <Button size="small" type="primary" onClick={() => resumeChat(pendingApproval.approvalId, 'approve')}>
                批准执行
              </Button>
              <Button size="small" danger onClick={() => resumeChat(pendingApproval.approvalId, 'reject')}>
                拒绝
              </Button>
            </Space>
          </div>
        )}
        {isStreaming && (
          <div style={{
            fontFamily: T.mono, fontSize: 11, color: T.signal,
            letterSpacing: 1, marginBottom: 8,
          }}>
            ▍ GENERATING<span className="eap-pulse"> · {agentName || 'AGENT'}</span>
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          <Input.TextArea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="> 输入消息 · Enter 发送 · Shift+Enter 换行"
            autoSize={{ minRows: 1, maxRows: 6 }}
            style={{
              flex: 1, resize: 'none', borderRadius: 10,
              fontFamily: T.mono, fontSize: 14,
              borderColor: T.line, background: T.chrome,
              padding: '10px 12px',
            }}
          />
          {isStreaming ? (
            <Button
              danger
              icon={<StopOutlined />}
              onClick={cancelStream}
              style={{ height: 42, width: 42, borderRadius: 10 }}
            />
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={!inputValue.trim()}
              style={{
                height: 42, width: 42, borderRadius: 10,
                background: T.signal, borderColor: T.signal,
                opacity: inputValue.trim() ? 1 : 0.4,
              }}
            />
          )}
        </div>
        <div style={{
          display: 'flex', justifyContent: 'space-between', marginTop: 8,
          fontFamily: T.mono, fontSize: 11, color: T.ink3,
        }}>
          <span>ENTER 发送 · SHIFT+ENTER 换行</span>
          <span>{agentName || '—'} / {modelName || '—'}</span>
        </div>
      </div>
    </div>
  );
}
