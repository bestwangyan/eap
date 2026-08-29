import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Dropdown, Avatar, Space, theme } from 'antd';
import {
  MessageOutlined, RobotOutlined, ThunderboltOutlined, SettingOutlined,
  LogoutOutlined, UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  ApiOutlined, CloudServerOutlined, FileTextOutlined, DashboardOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '../../stores/authStore';
import { useChatStore } from '../../stores/chatStore';

const { Header, Sider, Content } = Layout;

const staticItems = [
  {
    key: '/chat-group', icon: <MessageOutlined />, label: '对话',
    children: [{ key: '/chat', label: '新对话' }],
  },
  { key: '/agents', icon: <RobotOutlined />, label: 'Agent 管理' },
  { key: '/skills', icon: <ThunderboltOutlined />, label: 'Skill 市场' },
  { key: '/knowledge', icon: <FileTextOutlined />, label: '知识库' },
  {
    key: '/admin', icon: <SettingOutlined />, label: '管理后台',
    children: [
      { key: '/admin/models', icon: <ApiOutlined />, label: '模型配置' },
      { key: '/admin/mcp', icon: <CloudServerOutlined />, label: 'MCP 服务' },
      { key: '/admin/dashboard', icon: <DashboardOutlined />, label: '系统监控' },
    ],
  },
];

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const { threads, fetchThreads } = useChatStore();
  const { token: themeToken } = theme.useToken();

  useEffect(() => { fetchThreads(); const t = setInterval(fetchThreads, 15000); return () => clearInterval(t); }, []);

  const handleLogout = async () => { await logout(); navigate('/login'); };

  // 构建对话子菜单：新对话 + 历史线程列表
  const chatChildren = [
    { key: '/chat', label: '↳ 新对话' },
    ...(threads || []).slice(0, 30).map((t: any) => ({
      key: `/chat/${t.thread_id}`,
      label: (
        <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block', maxWidth: collapsed ? 60 : 160 }}>
          {t.title || t.thread_id?.slice(0, 8)}
        </span>
      ),
    })),
  ];

  const menuItems = staticItems.map(item =>
    item.key === '/chat-group' ? { ...item, children: chatChildren } : item
  );

  const selectedKey = location.pathname.startsWith('/chat/')
    ? `/chat/${location.pathname.split('/chat/')[1]}` : location.pathname.startsWith('/chat')
    ? '/chat' : '/' + location.pathname.split('/')[1];

  const userMenuItems = [
    { key: 'info', label: `${user?.username} (${user?.tenant_name || user?.tenant})`, disabled: true },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  return (
    <Layout className="app-shell">
      <Sider trigger={null} collapsible collapsed={collapsed}
        style={{ background: themeToken.colorBgContainer, borderRight: '1px solid #f0f0f0' }}>
        <div style={{ height: 48, margin: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontWeight: 700, fontSize: collapsed ? 16 : 18, color: themeToken.colorPrimary, whiteSpace: 'nowrap', overflow: 'hidden' }}>
          {collapsed ? 'EAP' : 'EAP Platform'}
        </div>
        <Menu mode="inline" selectedKeys={[selectedKey]} items={menuItems}
          onClick={({ key }) => navigate(key)} />
      </Sider>
      <Layout style={{ overflow: 'hidden' }}>
        <Header style={{ padding: '0 24px', background: themeToken.colorBgContainer,
          borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)} />
          <Dropdown menu={{ items: userMenuItems, onClick: ({ key }) => { if (key === 'logout') handleLogout(); } }}>
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{user?.username}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}><Outlet /></Content>
      </Layout>
    </Layout>
  );
}
