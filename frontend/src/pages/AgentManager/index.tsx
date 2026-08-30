import { useEffect, useState } from 'react';
import {
  Table, Button, Space, Tag, Typography, Modal, Form, Input, Select,
  Card, message, Popconfirm, InputNumber, Checkbox,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';
import { listAgents, createAgent, updateAgent, deleteAgent } from '../../api/agent';
import {
  listSubAgents, createSubAgent, deleteSubAgent,
  type SubAgentInfo,
} from '../../api/orchestration';
import apiClient from '../../api/client';
import { listAvailableModels } from '../../api/admin';
import type { AvailableModel } from '../../api/admin';
import type { AgentConfig } from '../../types/agent';

const { Title, Text } = Typography;

interface ResourceMap {
  tools: { id: string; name: string; description: string; display_name?: string; builtin?: boolean }[];
  skills: { id: string; name: string; description: string }[];
  mcp_servers: { id: string; name: string; transport: string; description: string }[];
  knowledge_collections: { id: number; name: string; description: string }[];
}

const PERMISSION_MODES = [
  { label: '默认 (关键操作需审批)', value: 'default' },
  { label: '自动接受编辑', value: 'acceptEdits' },
  { label: '静默执行', value: 'dontAsk' },
];

const BACKEND_OPTIONS = [
  { label: '本地进程（受限执行）', value: 'local' },
  { label: 'Docker 容器（预留）', value: 'container' },
];

export default function AgentManagerPage() {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentConfig | null>(null);
  const [resources, setResources] = useState<ResourceMap>({ tools: [], skills: [], mcp_servers: [], knowledge_collections: [] });
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [form] = Form.useForm();

  // ---- 子Agent 管理 ----
  const [subModalOpen, setSubModalOpen] = useState(false);
  const [subAgents, setSubAgents] = useState<SubAgentInfo[]>([]);
  const [subLoading, setSubLoading] = useState(false);
  const [parentAgent, setParentAgent] = useState<AgentConfig | null>(null);
  const [subForm] = Form.useForm();

  const openSubAgents = async (agent: AgentConfig) => {
    setParentAgent(agent);
    setSubModalOpen(true);
    setSubLoading(true);
    try {
      const res = await listSubAgents(agent.id);
      setSubAgents(res.sub_agents);
    } catch { message.error('获取子Agent列表失败'); }
    setSubLoading(false);
  };

  const handleCreateSub = async () => {
    if (!parentAgent) return;
    try {
      const values = await subForm.validateFields();
      await createSubAgent(parentAgent.id, values);
      message.success('子Agent 创建成功');
      subForm.resetFields();
      const res = await listSubAgents(parentAgent.id);
      setSubAgents(res.sub_agents);
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err?.response?.data?.error || '创建失败');
    }
  };

  const handleDeleteSub = async (subId: number) => {
    if (!parentAgent) return;
    try {
      await deleteSubAgent(parentAgent.id, subId);
      message.success('已删除');
      setSubAgents(prev => prev.filter(s => s.id !== subId));
    } catch { message.error('删除失败'); }
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [aRes, rRes] = await Promise.all([
        listAgents(), apiClient.get('/agents/resources'),
      ]);
      setAgents(aRes.agents);
      setResources(rRes.data);
    } catch { message.error('获取数据失败'); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchAll();
    listAvailableModels().then((res) => setAvailableModels(res.models)).catch(() => {});
  }, []);

  const handleCreate = () => {
    setEditingAgent(null);
    form.resetFields();
    // 默认绑定租户默认模型供应商（可在表单中切换）
    const defaultModel = availableModels.find((m) => m.is_default);
    form.setFieldsValue({
      model_provider_id: defaultModel?.id ?? undefined,
      permission_mode: 'default', backend: 'local', max_turns: 30,
      tools: ['calculator', 'datetime'], skills: [], mcp: [], knowledge: [],
    });
    setModalOpen(true);
  };

  const handleEdit = (record: AgentConfig) => {
    setEditingAgent(record);
    form.setFieldsValue({
      ...record,
      tools: record.tools_config || [],
      skills: record.skills || [],
      mcp: record.mcp_servers || [],
      knowledge: record.knowledge_collections || [],
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try { await deleteAgent(id); message.success('已删除'); fetchAll(); }
    catch { message.error('删除失败'); }
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const data = {
      ...values,
      tools_config: values.tools || [],
      skills: values.skills || [],
      mcp_servers: values.mcp || [],
      knowledge_collections: values.knowledge || [],
    };
    try {
      if (editingAgent) { await updateAgent(editingAgent.id, data); message.success('更新成功'); }
      else { await createAgent(data); message.success('创建成功'); }
      setModalOpen(false); fetchAll();
    } catch { message.error('操作失败'); }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', render: (t: string, r: AgentConfig) => <Space>{t}{r.is_active ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>}</Space> },
    { title: '模型后端', key: 'backend', width: 200, render: (_: unknown, r: AgentConfig) => {
      const bound = availableModels.find((m) => m.id === r.model_provider_id);
      return bound ? <Tag color="blue">{bound.name}</Tag> : <Tag>租户默认</Tag>;
    } },
    { title: '工具', key: 'tools', width: 100, render: (_: unknown, r: AgentConfig) => `${r.tools_config?.length || 0} 个` },
    { title: 'Skill', key: 'skill', width: 80, render: (_: unknown, r: AgentConfig) => `${r.skills?.length || 0} 个` },
    { title: '知识库', key: 'kb', width: 80, render: (_: unknown, r: AgentConfig) => `${r.knowledge_collections?.length || 0} 个` },
    { title: '子Agent', key: 'sub', width: 80, render: (_: unknown, r: AgentConfig) => <Button type="link" size="small" icon={<ApartmentOutlined />} onClick={() => openSubAgents(r)}>管理</Button> },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
    {
      title: '操作', key: 'actions', width: 240,
      render: (_: unknown, r: AgentConfig) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Button type="link" size="small" icon={<ApartmentOutlined />} onClick={() => openSubAgents(r)}>子Agent</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div><Title level={4} style={{ margin: 0 }}>Agent 管理</Title><Text type="secondary">配置 Agent 的工具 / Skill / MCP / 知识库</Text></div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchAll}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>创建 Agent</Button>
          </Space>
        </div>
        <Table columns={columns} dataSource={agents} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
      </Card>

      {/* 子Agent 管理弹窗 */}
      <Modal
        title={parentAgent ? `子Agent 管理 — ${parentAgent.name}` : '子Agent 管理'}
        open={subModalOpen}
        onCancel={() => { setSubModalOpen(false); setParentAgent(null); }}
        footer={null}
        width={720}
        destroyOnClose
      >
        {/* 创建表单 */}
        <Card size="small" title="创建子Agent" style={{ marginBottom: 16 }}>
          <Form form={subForm} layout="inline" style={{ flexWrap: 'wrap', gap: 8 }}>
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input placeholder="如: code_reviewer" style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="role_prompt" label="角色提示词" rules={[{ required: true }]}>
              <Input placeholder="如: 你是代码审查专家..." style={{ width: 280 }} />
            </Form.Item>
            <Form.Item name="mode" label="模式" initialValue="inline">
              <Select style={{ width: 100 }} options={[
                { label: 'inline', value: 'inline' },
                { label: 'compiled', value: 'compiled' },
                { label: 'async', value: 'async' },
              ]} />
            </Form.Item>
            <Form.Item name="model_provider_id" label="模型后端"
              tooltip="子代理使用的模型供应商；不选则继承主代理">
              <Select style={{ width: 220 }} allowClear placeholder="继承主代理"
                options={availableModels.map((m) => ({
                  label: `${m.name}${m.is_default ? ' (默认)' : ''}`, value: m.id }))} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateSub}>添加</Button>
            </Form.Item>
          </Form>
        </Card>

        {/* 子Agent 列表 */}
        <Table
          size="small"
          loading={subLoading}
          dataSource={subAgents}
          rowKey="id"
          pagination={false}
          locale={{ emptyText: '暂无子Agent，使用上方表单创建' }}
          columns={[
            { title: '名称', dataIndex: 'name', render: (v: string) => <strong>{v}</strong> },
            { title: '角色提示词', dataIndex: 'role_prompt', ellipsis: true, render: (v: string) => v?.slice(0, 60) + (v?.length > 60 ? '...' : '') },
            { title: '模式', dataIndex: 'mode', width: 80, render: (v: string) => <Tag>{v}</Tag> },
            { title: '状态', dataIndex: 'is_active', width: 60, render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '禁用'}</Tag> },
            {
              title: '操作', key: 'actions', width: 60,
              render: (_: unknown, r: SubAgentInfo) => (
                <Popconfirm title="确认删除？" onConfirm={() => handleDeleteSub(r.id)}>
                  <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              ),
            },
          ]}
        />
      </Modal>

      <Modal title={editingAgent ? '编辑 Agent' : '创建 Agent'} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={handleSubmit} width={700} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="system_prompt" label="系统提示词"><Input.TextArea rows={3} placeholder="留空使用默认提示词" /></Form.Item>

          <Typography.Title level={5} style={{ marginTop: 8 }}>资源配置</Typography.Title>

          <Form.Item name="tools" label="可用工具"
            tooltip="code_execution 可开关（映射 deepagents execute）；deepagents 内置文件工具恒启用，不可配置">
            <Checkbox.Group
              options={resources.tools.map(t => ({
                value: t.id,
                // deepagents 0.7.11 默认工具不可按名裁剪（tools_config 勾选无效）：
                // 禁用态展示 + 始终启用提示（终审 B2 处置），code_execution 保持可选
                disabled: t.builtin,
                label: t.builtin
                  ? `${t.display_name ?? t.name} (${t.name}) · deepagents 内置，始终启用`
                  : t.display_name ? `${t.display_name} (${t.name})` : `${t.name}: ${t.description}`,
              }))}
            />
          </Form.Item>

          <Form.Item name="skills" label="绑定 Skill">
            <Select mode="multiple" allowClear placeholder="选择 Skill" options={resources.skills.map(s => ({ label: s.name, value: s.id }))} />
          </Form.Item>

          <Form.Item name="mcp" label="MCP Server">
            <Select mode="multiple" allowClear placeholder="选择 MCP Server" options={resources.mcp_servers.map(s => ({ label: `${s.name} (${s.transport})`, value: s.id }))} />
          </Form.Item>

          <Form.Item name="knowledge" label="知识库">
            <Select mode="multiple" allowClear placeholder="选择知识库" options={resources.knowledge_collections.map(k => ({ label: k.name, value: k.id }))} />
          </Form.Item>

          <Typography.Title level={5} style={{ marginTop: 8 }}>高级设置</Typography.Title>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="model_provider_id" label="模型后端"
              tooltip="该智能体使用的模型供应商；不选则跟随租户默认或聊天页选择">
              <Select
                style={{ width: 220 }}
                allowClear
                placeholder="租户默认"
                options={availableModels.map((m) => ({
                  label: `${m.name}${m.is_default ? ' (默认)' : ''}`,
                  value: m.id,
                }))}
              />
            </Form.Item>
            <Form.Item name="permission_mode" label="权限模式"><Select style={{ width: 180 }} options={PERMISSION_MODES} /></Form.Item>
            <Form.Item name="backend" label="执行后端"
              tooltip="代码执行等工具的运行环境；Docker 容器沙箱为预留能力">
              <Select style={{ width: 200 }} options={BACKEND_OPTIONS} />
            </Form.Item>
            <Form.Item name="max_turns" label="最大轮次"><InputNumber min={1} max={100} /></Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
