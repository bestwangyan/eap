import { useEffect, useState } from 'react';
import {
  Table, Button, Space, Tag, Typography, Card, message, Popconfirm,
  Modal, Form, Input, Upload, InputNumber, Empty, Descriptions, Tabs,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, UploadOutlined,
  InboxOutlined, SearchOutlined, FileTextOutlined,
} from '@ant-design/icons';
import apiClient from '../../api/client';

const { Title, Text } = Typography;
const { Dragger } = Upload;

interface Collection {
  id: number; name: string; description: string;
  embedding_model: string; chunk_size: number; chunk_overlap: number;
  document_count: number; created_at: string;
}

interface Document {
  id: number; filename: string; file_type: string;
  file_size: number; status: string; chunk_count: number; created_at: string;
}

export default function KnowledgeBasePage() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [form] = Form.useForm();

  const fetchCollections = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/knowledge/collections');
      setCollections(res.data.collections);
    } catch { message.error('获取知识库列表失败'); }
    finally { setLoading(false); }
  };

  const fetchDocuments = async (id: number) => {
    try {
      const res = await apiClient.get(`/knowledge/collections/${id}/documents`);
      setDocuments(res.data.documents);
    } catch { /* ignore */ }
  };

  useEffect(() => { fetchCollections(); }, []);

  const handleSelect = (id: number) => {
    setSelectedId(id);
    fetchDocuments(id);
    setSearchResults([]);
    setSearchQuery('');
  };

  const handleCreate = async () => {
    const values = await form.validateFields();
    try {
      await apiClient.post('/knowledge/collections', values);
      message.success('知识库创建成功');
      setModalOpen(false);
      form.resetFields();
      fetchCollections();
    } catch { message.error('创建失败'); }
  };

  const handleDelete = async (id: number) => {
    try {
      await apiClient.delete(`/knowledge/collections/${id}`);
      message.success('已删除');
      if (selectedId === id) setSelectedId(null);
      fetchCollections();
    } catch { message.error('删除失败'); }
  };

  const handleUpload = async (file: File) => {
    if (!selectedId) { message.warning('请先选择知识库'); return false; }
    const formData = new FormData();
    formData.append('file', file);
    try {
      await apiClient.post(`/knowledge/collections/${selectedId}/documents/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000,
      });
      message.success(`${file.name} 上传成功`);
      fetchDocuments(selectedId);
      fetchCollections();
    } catch (err: any) {
      message.error(err?.response?.data?.error || '上传失败');
    }
    return false;
  };

  const handleDeleteDoc = async (docId: number) => {
    try {
      await apiClient.delete(`/knowledge/documents/${docId}`);
      message.success('文档已删除');
      if (selectedId) fetchDocuments(selectedId);
    } catch { message.error('删除失败'); }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim() || !selectedId) return;
    try {
      const res = await apiClient.post('/knowledge/search', {
        query: searchQuery, collection_id: selectedId, top_k: 5,
      });
      setSearchResults(res.data.results);
    } catch { message.error('检索失败'); }
  };

  return (
    <div style={{ padding: 24, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Title level={4}>知识库管理 (Phase 2)</Title>
      <div style={{ display: 'flex', gap: 16, flex: 1, overflow: 'hidden' }}>
        {/* 左侧：知识库列表 */}
        <Card title="知识库" style={{ width: 300 }} extra={
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建</Button>
        }>
          {collections.length === 0 ? <Empty description="暂无知识库" /> :
            collections.map(c => (
              <Card key={c.id} size="small" hoverable
                style={{ marginBottom: 8, borderColor: selectedId === c.id ? '#1677ff' : undefined }}
                onClick={() => handleSelect(c.id)}>
                <Text strong>{c.name}</Text>
                <br /><Text type="secondary" style={{ fontSize: 12 }}>{c.document_count} 文档 | chunk: {c.chunk_size}</Text>
              </Card>
            ))
          }
        </Card>

        {/* 右侧：文档管理 + 检索 */}
        <Card title={selectedId ? `文档列表 (#${selectedId})` : '请选择知识库'} style={{ flex: 1 }} extra={
          selectedId ? <Space>
            <Button icon={<ReloadOutlined />} size="small" onClick={() => fetchDocuments(selectedId)}>刷新</Button>
            <Popconfirm title="确认删除？" onConfirm={() => handleDelete(selectedId)}>
              <Button danger size="small" icon={<DeleteOutlined />}>删除知识库</Button>
            </Popconfirm>
          </Space> : null
        }>
          <Tabs items={[
            {
              key: 'docs', label: '文档管理',
              children: (
                <div>
                  <Dragger accept=".pdf,.docx,.md,.txt,.html,.csv" maxCount={1}
                    beforeUpload={(f) => { handleUpload(f); return false; }} showUploadList={false}
                    style={{ marginBottom: 16 }}>
                    <InboxOutlined style={{ fontSize: 24 }} />
                    <p>点击或拖拽文件上传 (PDF/Word/MD/TXT)</p>
                  </Dragger>
                  <Table dataSource={documents} rowKey="id" size="small" pagination={{ pageSize: 10 }}
                    columns={[
                      { title: '文件名', dataIndex: 'filename', ellipsis: true },
                      { title: '类型', dataIndex: 'file_type', width: 60, render: (v: string) => <Tag>{v}</Tag> },
                      { title: '状态', dataIndex: 'status', width: 80, render: (v: string) => {
                        const colors: Record<string,string> = {pending:'default',parsing:'processing',ready:'green',error:'red'};
                        return <Tag color={colors[v]}>{v}</Tag>;
                      }},
                      { title: '分块', dataIndex: 'chunk_count', width: 60 },
                      { title: '操作', width: 60, render: (_: unknown, r: Document) =>
                        <Popconfirm title="确认删除？" onConfirm={() => handleDeleteDoc(r.id)}>
                          <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      },
                    ]}
                  />
                </div>
              ),
            },
            {
              key: 'search', label: '检索测试',
              children: (
                <div>
                  <Space style={{ marginBottom: 16, width: '100%' }}>
                    <Input.Search placeholder="输入查询关键词" value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)} onSearch={handleSearch}
                      enterButton={<><SearchOutlined /> 搜索</>} style={{ flex: 1 }} />
                  </Space>
                  {searchResults.map((r, i) => (
                    <Card key={i} size="small" style={{ marginBottom: 8 }}>
                      <Text>{r.content}</Text>
                      <br /><Tag color="blue">score: {r.score}</Tag>
                      <Text type="secondary" style={{ fontSize: 11 }}>chunk #{r.chunk_index}</Text>
                    </Card>
                  ))}
                  {searchResults.length === 0 && searchQuery && <Empty description="无结果" />}
                </div>
              ),
            },
          ]} />
        </Card>
      </div>

      <Modal title="新建知识库" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={handleCreate}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="chunk_size" label="分块大小" initialValue={1000}><InputNumber min={100} max={4000} /></Form.Item>
          <Form.Item name="chunk_overlap" label="重叠字符数" initialValue={200}><InputNumber min={0} max={1000} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
