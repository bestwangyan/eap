import { useEffect, useState } from 'react';
import {
  Table, Button, Space, Tag, Typography, Card, message, Popconfirm,
  Upload, Modal, Descriptions, Switch, Form, Input, Select, Radio,
} from 'antd';
import {
  UploadOutlined, ReloadOutlined, DeleteOutlined, EyeOutlined,
  InboxOutlined, PlusOutlined,
} from '@ant-design/icons';
import { listSkills, uploadSkill, createSkill, deleteSkill, toggleSkill, getSkill } from '../../api/skill';
import type { SkillInfo, CreateSkillData } from '../../api/skill';

const { Title, Text } = Typography;
const { Dragger } = Upload;

export default function SkillMarketPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailSkill, setDetailSkill] = useState<any>(null);
  const [form] = Form.useForm<CreateSkillData>();

  const fetchSkills = async () => {
    setLoading(true);
    try {
      const res = await listSkills();
      setSkills(res.skills);
    } catch {
      message.error('获取 Skill 列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSkills(); }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await uploadSkill(file);
      message.success('上传成功');
      setUploadOpen(false);
      fetchSkills();
    } catch (err: any) {
      message.error(err?.response?.data?.error || '上传失败');
    } finally {
      setUploading(false);
    }
    return false; // prevent default upload
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      await createSkill(values);
      message.success('Skill 创建成功');
      setCreateOpen(false);
      form.resetFields();
      fetchSkills();
    } catch (err: any) {
      if (err?.response?.data?.error) {
        message.error(err.response.data.error);
      } else if (err?.errorFields) {
        // form validation error, do nothing
      } else {
        message.error('创建失败');
      }
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteSkill(id);
      message.success('已删除');
      fetchSkills();
    } catch { message.error('删除失败'); }
  };

  const handleToggle = async (id: number, isActive: boolean) => {
    try {
      await toggleSkill(id, isActive);
      fetchSkills();
    } catch { message.error('操作失败'); }
  };

  const handleView = async (id: number) => {
    try {
      const res = await getSkill(id);
      setDetailSkill(res.skill);
      setDetailOpen(true);
    } catch { message.error('获取详情失败'); }
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: SkillInfo) => (
        <Space>
          {text}
          {record.is_active ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>}
        </Space>
      ),
    },
    {
      title: '版本', dataIndex: 'version', key: 'version', width: 80,
      render: (v: string) => <Tag>{v || '1.0.0'}</Tag>,
    },
    {
      title: '作者', dataIndex: 'author', key: 'author', width: 120,
    },
    {
      title: '标签', dataIndex: 'tags', key: 'tags', width: 200,
      render: (tags: string[]) => tags?.map((t) => <Tag key={t}>{t}</Tag>),
    },
    {
      title: '依赖工具', dataIndex: 'tools', key: 'tools', width: 200,
      render: (tools: string[]) => tools?.map((t) => <Tag key={t} color="blue">{t}</Tag>),
    },
    {
      title: '模式', dataIndex: 'mode', key: 'mode', width: 80,
      render: (mode: string) => (
        <Tag color={mode === 'agent' ? 'purple' : 'blue'}>
          {mode === 'agent' ? 'Agent' : 'Prompt'}
        </Tag>
      ),
    },
    {
      title: '文件名', dataIndex: 'original_filename', key: 'file', width: 200,
      ellipsis: true,
    },
    {
      title: '操作', key: 'actions', width: 240,
      render: (_: unknown, record: SkillInfo) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(record.id)}>详情</Button>
          <Switch
            checked={record.is_active}
            size="small"
            onChange={(v) => handleToggle(record.id, v)}
          />
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
            <Title level={4} style={{ margin: 0 }}>Skill 市场</Title>
            <Text type="secondary">上传 ZIP 压缩包创建 Skill，包内需含 SKILL.md</Text>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchSkills}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true); }}>
              手动创建
            </Button>
            <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
              上传 Skill
            </Button>
          </Space>
        </div>

        <Table columns={columns} dataSource={skills} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
      </Card>

      {/* 手动创建弹窗 */}
      <Modal
        title="手动创建 Skill"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={creating}
        okText="创建"
        cancelText="取消"
        destroyOnClose
        width={640}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入 Skill 名称' }]}>
            <Input placeholder="英文名称，如 web_search" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="Skill 功能描述" rows={2} />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item name="version" label="版本" initialValue="1.0.0">
              <Input placeholder="1.0.0" style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="author" label="作者">
              <Input placeholder="作者名" style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Form.Item name="tags" label="标签">
            <Select
              mode="tags"
              placeholder="输入后回车添加标签"
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item name="trigger_keywords" label="触发关键词">
            <Select
              mode="tags"
              placeholder="输入后回车添加关键词"
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item name="tools" label="依赖工具">
            <Select
              mode="tags"
              placeholder="输入工具名称后回车"
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item name="mode" label="运行模式" initialValue="prompt" tooltip="Prompt 模式将规则注入系统提示词；Agent 模式包装为可调用工具">
            <Radio.Group>
              <Radio.Button value="prompt">Prompt 模式</Radio.Button>
              <Radio.Button value="agent">Agent 模式</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item
            name="prompt"
            label="Skill 提示词 (Prompt)"
            tooltip="即 SKILL.md 中 frontmatter 之后的 Markdown 内容，定义 Skill 的行为规则"
            rules={[{ required: true, message: '请输入 Skill 提示词' }]}
          >
            <Input.TextArea
              placeholder={`你是一个专业的搜索助手。\n\n当用户提出搜索需求时：\n1. 先分析搜索意图\n2. 使用 search 工具执行搜索\n3. 整理并总结搜索结果\n\n注意事项：\n- 优先使用官方来源\n- 标注信息的时效性`}
              rows={10}
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 上传弹窗 */}
      <Modal
        title="上传 Skill"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        footer={null}
        destroyOnClose
      >
        <div style={{ padding: '16px 0' }}>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
            ZIP 包结构示例：<br />
            <code>
              my_skill/<br />
              &nbsp;&nbsp;├── SKILL.md&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(必须, YAML frontmatter)<br />
              &nbsp;&nbsp;├── scripts/<br />
              &nbsp;&nbsp;└── prompts/
            </code>
          </Text>
          <Dragger
            accept=".zip"
            maxCount={1}
            beforeUpload={(file) => { handleUpload(file); return false; }}
            showUploadList={false}
            disabled={uploading}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">点击或拖拽 ZIP 文件到此区域</p>
            <p className="ant-upload-hint">仅支持 .zip 格式，最大 50MB</p>
          </Dragger>
          {uploading && <div style={{ textAlign: 'center', marginTop: 16 }}>上传中...</div>}
        </div>
      </Modal>

      {/* 详情弹窗 */}
      <Modal
        title={detailSkill?.name}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={720}
      >
        {detailSkill && (
          <div>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="版本">{detailSkill.version}</Descriptions.Item>
              <Descriptions.Item label="作者">{detailSkill.author || '-'}</Descriptions.Item>
              <Descriptions.Item label="文件名">{detailSkill.original_filename}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={detailSkill.is_active ? 'green' : 'default'}>
                  {detailSkill.is_active ? '启用' : '禁用'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="运行模式">
                <Tag color={detailSkill.mode === 'agent' ? 'purple' : 'blue'}>
                  {detailSkill.mode === 'agent' ? 'Agent' : 'Prompt'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>
                {detailSkill.tags?.map((t: string) => <Tag key={t}>{t}</Tag>) || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="依赖工具" span={2}>
                {detailSkill.tools?.map((t: string) => <Tag key={t} color="blue">{t}</Tag>) || '-'}
              </Descriptions.Item>
            </Descriptions>
            <Title level={5}>SKILL.md 内容</Title>
            <pre style={{
              background: '#f5f5f5', padding: 16, borderRadius: 8,
              maxHeight: 400, overflow: 'auto', fontSize: 13,
            }}>
              {detailSkill.skill_content || '(空)'}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
}
