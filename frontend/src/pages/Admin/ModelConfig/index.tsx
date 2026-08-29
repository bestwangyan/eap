import { useEffect, useState } from 'react';
import {
  Table, Button, Space, Tag, Typography, Modal, Form, Input, Select,
  Card, message, Popconfirm, Switch, InputNumber,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import {
  listModelProviders, createModelProvider, updateModelProvider, deleteModelProvider,
} from '../../../api/admin';
import type { ModelProviderInfo } from '../../../api/admin';

const { Title, Text } = Typography;

const PROVIDER_OPTIONS = [
  { label: 'Anthropic (Claude)', value: 'anthropic' },
  { label: 'OpenAI (GPT)', value: 'openai' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'LM Studio (本地)', value: 'lmstudio' },
];

export default function ModelConfigPage() {
  const [models, setModels] = useState<ModelProviderInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModelProviderInfo | null>(null);
  const [form] = Form.useForm();

  const fetchModels = async () => {
    setLoading(true);
    try {
      const res = await listModelProviders();
      setModels(res.models);
    } catch {
      message.error('获取模型列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchModels(); }, []);

  const handleCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ provider: 'deepseek', api_base: 'https://api.deepseek.com/v1', is_active: true, is_default: false });
    setModalOpen(true);
  };

  const handleEdit = (record: ModelProviderInfo) => {
    setEditing(record);
    // 列表返回的 api_key 是脱敏展示值，编辑时清空；留空 = 不修改原 Key
    const { api_key: _masked, ...rest } = record;
    void _masked;
    form.setFieldsValue({ ...rest, api_key: '' });
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteModelProvider(id);
      message.success('已删除');
      fetchModels();
    } catch {
      message.error('删除失败');
    }
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        // api_key 留空表示不修改，从提交内容中移除
        const payload = { ...values };
        if (!payload.api_key) delete payload.api_key;
        await updateModelProvider(editing.id, payload);
        message.success('更新成功');
      } else {
        await createModelProvider(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      fetchModels();
    } catch {
      message.error('操作失败');
    }
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: ModelProviderInfo) => (
        <Space>
          {text}
          {record.is_default && <Tag color="blue">默认</Tag>}
          {!record.is_active && <Tag>禁用</Tag>}
        </Space>
      ),
    },
    {
      title: '供应商', dataIndex: 'provider', key: 'provider', width: 120,
      render: (v: string) => {
        const labels: Record<string, string> = { anthropic: 'Anthropic', openai: 'OpenAI', deepseek: 'DeepSeek' };
        return <Tag>{labels[v] || v}</Tag>;
      },
    },
    {
      title: '模型名', dataIndex: 'model_name', key: 'model_name', width: 220,
      render: (v: string) => <code>{v}</code>,
    },
    {
      title: 'API Key', dataIndex: 'api_key', key: 'api_key', width: 180,
      render: (v: string) => <Text code>{v || '****'}</Text>,
    },
    {
      title: '自定义 API', dataIndex: 'api_base', key: 'api_base', width: 200,
      render: (v: string) => v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : <Text type="secondary">默认</Text>,
    },
    {
      title: '操作', key: 'actions', width: 160,
      render: (_: unknown, record: ModelProviderInfo) => (
        <Space>
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
            <Title level={4} style={{ margin: 0 }}>模型供应商配置</Title>
            <Text type="secondary">配置 LLM 接入信息，配置后用户可在聊天中选择使用</Text>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchModels}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>添加模型</Button>
          </Space>
        </div>

        <Table columns={columns} dataSource={models} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
      </Card>

      <Modal
        title={editing ? '编辑模型配置' : '添加模型配置'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="显示名称" rules={[{ required: true }]}>
            <Input placeholder="例如: Claude Sonnet 4" />
          </Form.Item>
          <Form.Item name="provider" label="供应商" rules={[{ required: true }]}>
            <Select options={PROVIDER_OPTIONS} />
          </Form.Item>
          <Form.Item name="model_name" label="模型标识名" rules={[{ required: true }]}
            tooltip="供应商 API 中的模型 ID，如 claude-sonnet-4-20250514">
            <Input placeholder="claude-sonnet-4-20250514" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key" rules={editing ? [] : [{ required: true }]}
            tooltip="模型供应商的 API 密钥">
            <Input.Password prefix={<KeyOutlined />}
              placeholder={editing ? '已配置，留空表示不修改' : 'sk-...'} />
          </Form.Item>
          <Form.Item name="api_base" label="自定义 API 地址"
            tooltip="留空使用默认地址；DeepSeek 等需填写 https://api.deepseek.com/v1">
            <Input placeholder="留空使用默认" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="简要描述" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="is_active" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_default" label="设为默认" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
