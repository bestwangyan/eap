import { useEffect, useState } from 'react';
import {
  Table, Button, Space, Tag, Typography, Card, message, Popconfirm,
  Modal, Form, Input, Select, Switch, Tabs,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  LinkOutlined, CodeOutlined,
} from '@ant-design/icons';
import { listServers, createServer, updateServer, deleteServer, testConnection } from '../../../api/mcp';
import type { MCPServerInfo } from '../../../api/mcp';

const { Title, Text } = Typography;

export default function MCPConfigPage() {
  const [servers, setServers] = useState<MCPServerInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MCPServerInfo | null>(null);
  const [transport, setTransport] = useState<'stdio' | 'sse'>('stdio');
  const [form] = Form.useForm();

  const fetchServers = async () => {
    setLoading(true);
    try {
      const res = await listServers();
      setServers(res.servers);
    } catch {
      message.error('获取列表失败');
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchServers(); }, []);

  const handleCreate = () => {
    setEditing(null);
    setTransport('stdio');
    form.resetFields();
    form.setFieldsValue({ transport: 'stdio', is_active: true });
    setModalOpen(true);
  };

  const handleEdit = (record: MCPServerInfo) => {
    setEditing(record);
    setTransport(record.transport as 'stdio' | 'sse');
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteServer(id);
      message.success('已删除');
      fetchServers();
    } catch { message.error('删除失败'); }
  };

  const handleTest = async (id: number) => {
    try {
      const res = await testConnection(id);
      if (res.status === 'connected') message.success('连接成功');
      else message.error(res.message || '连接失败');
    } catch { message.error('测试失败'); }
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateServer(editing.id, values);
        message.success('更新成功');
      } else {
        await createServer(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      fetchServers();
    } catch { message.error('操作失败'); }
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: MCPServerInfo) => (
        <Space>
          {text}
          {record.is_active ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>}
        </Space>
      ),
    },
    {
      title: '类型', dataIndex: 'transport', key: 'transport', width: 80,
      render: (v: string) => (
        <Tag icon={v === 'stdio' ? <CodeOutlined /> : <LinkOutlined />} color={v === 'stdio' ? 'blue' : 'purple'}>
          {v.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: '命令/URL', key: 'detail', width: 280,
      render: (_: unknown, record: MCPServerInfo) => (
        record.transport === 'stdio'
          ? <code>{record.command} {record.args?.join(' ')}</code>
          : <code>{record.sse_url}</code>
      ),
    },
    {
      title: '状态', dataIndex: 'connection_status', key: 'status', width: 100,
      render: (v: string) => {
        const colors: Record<string, string> = {
          connected: 'green', connecting: 'blue',
          error: 'red', disconnected: 'default',
        };
        const labels: Record<string, string> = {
          connected: '已连接', connecting: '连接中',
          error: '错误', disconnected: '未连接',
        };
        return <Tag color={colors[v] || 'default'}>{labels[v] || v}</Tag>;
      },
    },
    {
      title: '操作', key: 'actions', width: 240,
      render: (_: unknown, record: MCPServerInfo) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleTest(record.id)}>测试</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Title level={4} style={{ margin: 0 }}>MCP Server 管理</Title>
            <Text type="secondary">手动配置 stdio 或 SSE 类型的 MCP 服务</Text>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchServers}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>添加 Server</Button>
          </Space>
        </div>

        <Table columns={columns} dataSource={servers} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
      </Card>

      <Modal
        title={editing ? '编辑 MCP Server' : '添加 MCP Server'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="MCP Server 名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="简要描述" />
          </Form.Item>
          <Form.Item name="transport" label="连接类型" rules={[{ required: true }]}>
            <Select
              options={[
                { label: 'STDIO (命令行进程)', value: 'stdio' },
                { label: 'SSE (远程服务)', value: 'sse' },
              ]}
              onChange={(v) => setTransport(v as 'stdio' | 'sse')}
            />
          </Form.Item>

          {transport === 'stdio' ? (
            <>
              <Form.Item name="command" label="启动命令" rules={[{ required: true }]}
                tooltip="如 python / node / npx / uvx">
                <Input placeholder="例如: npx" />
              </Form.Item>
              <Form.Item name="args" label="命令参数"
                tooltip="JSON 数组，如 [&quot;-y&quot;, &quot;@modelcontextprotocol/server-filesystem&quot;, &quot;/tmp&quot;]">
                <Input.TextArea rows={2} placeholder='["-y", "@mcp/server-filesystem"]' />
              </Form.Item>
              <Form.Item name="env" label="环境变量"
                tooltip="JSON 对象，如 {&quot;API_KEY&quot;: &quot;xxx&quot;}"
                getValueFromEvent={(e) => {
                  try { return JSON.parse(e.target.value); } catch { return e.target.value; }
                }}
                getValueProps={(v) => ({
                  value: typeof v === 'object' ? JSON.stringify(v, null, 2) : v
                })}
              >
                <Input.TextArea rows={3} placeholder='{"KEY": "value"}' />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item name="sse_url" label="SSE 端点 URL" rules={[{ required: true }]}
                tooltip="如 http://192.168.1.51:8080/sse">
                <Input placeholder="http://host:port/sse" />
              </Form.Item>
              <Form.Item name="sse_headers" label="自定义请求头"
                tooltip='JSON 对象，如 {"Authorization": "Bearer xxx"}'
                getValueFromEvent={(e) => {
                  try { return JSON.parse(e.target.value); } catch { return e.target.value; }
                }}
                getValueProps={(v) => ({
                  value: typeof v === 'object' ? JSON.stringify(v, null, 2) : v
                })}
              >
                <Input.TextArea rows={3} placeholder='{"Authorization": "Bearer xxx"}' />
              </Form.Item>
            </>
          )}

          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
