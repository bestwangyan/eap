import { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Typography, Table, Tag, Modal, Timeline, Descriptions, Button } from 'antd';
import {
  DollarOutlined, ThunderboltOutlined, ApiOutlined, CheckCircleOutlined,
  EyeOutlined, ReloadOutlined, RobotOutlined, ToolOutlined,
} from '@ant-design/icons';
import apiClient from '../../../api/client';
import { listTraces, getTraceDetail, type TraceEvent, type TraceDetail } from '../../../api/monitor';

const { Title, Text } = Typography;

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<any>({ cost: {}, active_sessions: 0, status: 'loading' });
  const [traces, setTraces] = useState<TraceEvent[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [traceDetail, setTraceDetail] = useState<TraceDetail | null>(null);

  const fetchDashboard = () => {
    apiClient.get('/admin/monitor/dashboard').then(r => setDashboard(r.data)).catch(() => {});
  };

  const fetchTraces = async () => {
    setTraceLoading(true);
    try {
      const res = await listTraces(20);
      setTraces(res.traces || []);
    } catch { /* ignore */ }
    setTraceLoading(false);
  };

  useEffect(() => {
    fetchDashboard();
    fetchTraces();
  }, []);

  const handleViewTrace = async (traceId: string) => {
    try {
      const detail = await getTraceDetail(traceId);
      setTraceDetail(detail);
      setDetailOpen(true);
    } catch { /* ignore */ }
  };

  const eventIcon = (type: string) => {
    switch (type) {
      case 'llm': return <RobotOutlined style={{ color: '#1677ff' }} />;
      case 'tool': return <ToolOutlined style={{ color: '#fa8c16' }} />;
      default: return <ApiOutlined style={{ color: '#52c41a' }} />;
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>系统监控</Title>
        <Button icon={<ReloadOutlined />} onClick={() => { fetchDashboard(); fetchTraces(); }}>刷新</Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title="今日 Token" value={(dashboard.cost?.input_tokens || 0) + (dashboard.cost?.output_tokens || 0)} suffix="tokens" /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="今日成本" value={dashboard.cost?.cost_usd || 0} precision={4} prefix={<DollarOutlined />} suffix="USD" /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="活跃会话" value={dashboard.active_sessions} prefix={<ApiOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="系统状态" value={dashboard.status === 'healthy' ? '正常' : '降级'} prefix={<CheckCircleOutlined style={{ color: dashboard.status === 'healthy' ? '#52c41a' : '#faad14' }} />} /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card title="模型定价参考">
            <Table size="small" pagination={false} dataSource={[
              { model: 'DeepSeek V4 Pro', input: '$0.27', output: '$1.10' },
              { model: 'GPT-4o', input: '$2.50', output: '$10.00' },
              { model: 'Claude Sonnet 4', input: '$3.00', output: '$15.00' },
              { model: 'Claude Opus 4', input: '$15.00', output: '$75.00' },
            ]} columns={[
              { title: '模型', dataIndex: 'model' },
              { title: '输入 (1M tokens)', dataIndex: 'input' },
              { title: '输出 (1M tokens)', dataIndex: 'output' },
            ]} rowKey="model" />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="已部署模块">
            {[
              { phase: 'P1', status: 'done', items: '认证/RBAC/对话/Agent/模型/Skill/MCP' },
              { phase: 'P2', status: 'done', items: '知识库/RAG/文档管理/混合检索' },
              { phase: 'P3', status: 'done', items: '子Agent/监督者路由/编排测试' },
              { phase: 'P4', status: 'done', items: '安全围栏/PII/HITL审批' },
              { phase: 'P5', status: 'done', items: '成本追踪/监控仪表盘/Trace' },
            ].map(p => (
              <div key={p.phase} style={{ marginBottom: 8, display: 'flex', gap: 12 }}>
                <Tag color={p.status === 'done' ? 'green' : 'blue'}>{p.phase}</Tag>
                <span>{p.items}</span>
              </div>
            ))}
          </Card>
        </Col>
      </Row>

      {/* Trace 列表 */}
      <Card
        title={<span><ThunderboltOutlined style={{ marginRight: 8 }} />最近 Trace（对话可观测性）</span>}
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={fetchTraces}>刷新</Button>}
      >
        <Table
          size="small"
          loading={traceLoading}
          pagination={{ pageSize: 10 }}
          dataSource={traces}
          rowKey="trace_id"
          locale={{ emptyText: '暂无 Trace 数据，发送消息后自动生成' }}
          columns={[
            {
              title: 'Trace ID', dataIndex: 'trace_id', width: 140,
              render: (v: string) => <Text code>{v}</Text>,
            },
            {
              title: '名称', dataIndex: 'event_name', ellipsis: true,
            },
            {
              title: '时间', dataIndex: 'created_at', width: 170,
              render: (v: string) => v ? new Date(v).toLocaleString() : '-',
            },
            {
              title: '线程', dataIndex: 'thread_id', width: 120, ellipsis: true,
              render: (v: string) => v ? <Text code style={{ fontSize: 11 }}>{v.slice(0, 12)}...</Text> : '-',
            },
            {
              title: '耗时', dataIndex: 'duration_ms', width: 80,
              render: (v: number) => v ? `${(v / 1000).toFixed(1)}s` : '-',
            },
            {
              title: '操作', width: 80,
              render: (_: unknown, record: TraceEvent) => (
                <Button type="link" size="small" icon={<EyeOutlined />}
                  onClick={() => handleViewTrace(record.trace_id)}>详情</Button>
              ),
            },
          ]}
        />
      </Card>

      {/* Trace 详情弹窗 */}
      <Modal
        title={`Trace: ${traceDetail?.trace_id || ''}`}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={800}
        destroyOnClose
      >
        {traceDetail && (
          <div>
            <Descriptions size="small" column={4} bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="LLM 调用">{traceDetail.summary.llm_calls}</Descriptions.Item>
              <Descriptions.Item label="工具调用">{traceDetail.summary.tool_calls}</Descriptions.Item>
              <Descriptions.Item label="总 Token">{traceDetail.summary.total_tokens}</Descriptions.Item>
              <Descriptions.Item label="总耗时">{traceDetail.summary.total_duration_ms > 0 ? `${(traceDetail.summary.total_duration_ms / 1000).toFixed(1)}s` : '-'}</Descriptions.Item>
            </Descriptions>

            {traceDetail.summary.errors.length > 0 && (
              <div style={{ marginBottom: 12, padding: 8, background: '#fff2f0', borderRadius: 4 }}>
                {traceDetail.summary.errors.map((e, i) => (
                  <div key={i} style={{ color: '#ff4d4f', fontSize: 12 }}>⚠ {e.slice(0, 200)}</div>
                ))}
              </div>
            )}

            <Timeline
              items={traceDetail.events.map((evt) => ({
                dot: eventIcon(evt.event_type),
                children: (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Tag color={evt.event_type === 'llm' ? 'blue' : evt.event_type === 'tool' ? 'orange' : 'green'}>
                        {evt.event_type.toUpperCase()}
                      </Tag>
                      <Text strong>{evt.event_name}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {evt.duration_ms ? `${evt.duration_ms}ms` : ''}
                      </Text>
                    </div>
                    {evt.error && (
                      <Text type="danger" style={{ fontSize: 12 }}>错误: {evt.error.slice(0, 200)}</Text>
                    )}
                    {evt.input_data && Object.keys(evt.input_data).length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>输入:</Text>
                        <pre style={{ fontSize: 11, background: '#fafafa', padding: 4, borderRadius: 4, maxHeight: 120, overflow: 'auto', margin: '4px 0 0' }}>
                          {JSON.stringify(evt.input_data, null, 2).slice(0, 600)}
                        </pre>
                      </div>
                    )}
                    {evt.output_data && Object.keys(evt.output_data).length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>输出:</Text>
                        <pre style={{ fontSize: 11, background: '#fafafa', padding: 4, borderRadius: 4, maxHeight: 120, overflow: 'auto', margin: '4px 0 0' }}>
                          {JSON.stringify(evt.output_data, null, 2).slice(0, 600)}
                        </pre>
                      </div>
                    )}
                  </div>
                ),
              }))}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
