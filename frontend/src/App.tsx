import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuthStore } from './stores/authStore';
import LoginPage from './pages/Login';
import ChatPage from './pages/Chat';
import AgentManagerPage from './pages/AgentManager';
import SkillMarketPage from './pages/SkillMarket';
import KnowledgeBasePage from './pages/KnowledgeBase';
import ModelConfigPage from './pages/Admin/ModelConfig';
import MCPConfigPage from './pages/Admin/MCPConfig';
import DashboardPage from './pages/Admin/Dashboard';
import MainLayout from './components/Layout/MainLayout';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, initialized } = useAuthStore();

  if (!initialized) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  const { init, initialized } = useAuthStore();

  useEffect(() => {
    init();
  }, [init]);

  if (!initialized) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:threadId" element={<ChatPage />} />
        <Route path="agents" element={<AgentManagerPage />} />
        <Route path="skills" element={<SkillMarketPage />} />
        <Route path="knowledge" element={<KnowledgeBasePage />} />
        <Route path="admin/models" element={<ModelConfigPage />} />
        <Route path="admin/mcp" element={<MCPConfigPage />} />
        <Route path="admin/dashboard" element={<DashboardPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
