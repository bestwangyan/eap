import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message, Space, Tabs, Divider } from 'antd';
import { MailOutlined, LockOutlined, UserOutlined, TeamOutlined } from '@ant-design/icons';
import { useAuthStore } from '../../stores/authStore';
import { register } from '../../api/auth';

const { Title, Text } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      await login(values);
      message.success('登录成功');
      navigate('/chat');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '登录失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: {
    email: string;
    username: string;
    password: string;
    tenant_name: string;
  }) => {
    setLoading(true);
    try {
      await register(values);
      message.success('注册成功，请登录');
      setActiveTab('login');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '注册失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    }}>
      <Card
        style={{ width: 420, boxShadow: '0 8px 24px rgba(0,0,0,0.15)' }}
        bodyStyle={{ padding: '32px' }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={2} style={{ marginBottom: 4 }}>EAP</Title>
          <Text type="secondary">企业级 Agent 平台</Text>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k as 'login' | 'register')}
          centered
          items={[
            {
              key: 'login',
              label: '登录',
              children: (
                <Form onFinish={handleLogin} size="large" autoComplete="off">
                  <Form.Item name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
                    <Input prefix={<MailOutlined />} placeholder="邮箱" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder="密码" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      登录
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: (
                <Form onFinish={handleRegister} size="large" autoComplete="off">
                  <Form.Item name="tenant_name" rules={[{ required: true, message: '请输入组织名称' }]}>
                    <Input prefix={<TeamOutlined />} placeholder="组织名称" />
                  </Form.Item>
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input prefix={<UserOutlined />} placeholder="用户名" />
                  </Form.Item>
                  <Form.Item name="email" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
                    <Input prefix={<MailOutlined />} placeholder="邮箱" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, min: 6, message: '密码至少 6 位' }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder="密码" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      注册
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />

        <Divider plain style={{ fontSize: 12 }}>
          账号
        </Divider>
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', textAlign: 'center' }}>
            首次使用请联系管理员创建账号
          </Text>
        </Space>
      </Card>

      <Text type="secondary" style={{ color: 'rgba(255,255,255,0.7)', marginTop: 16 }}>
        Powered by LangChain Deep Agents
      </Text>
    </div>
  );
}
