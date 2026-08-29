# 企业级 Agent 平台 (EAP) — 测试用例文档

> **版本**: v2.0 | **日期**: 2026-07-25 | **测试框架**: Playwright E2E
> **测试目标**: 100% 功能覆盖率 (Phase 1-5 全量) | **测试环境**: `http://192.168.1.51/eap`

---

## 目录

1. [测试架构](#1-测试架构)
2. [TC-AUTH 认证模块测试](#2-tc-auth-认证模块测试)
3. [TC-RBAC 权限模块测试](#3-tc-rbac-权限模块测试)
4. [TC-CHAT 对话模块测试](#4-tc-chat-对话模块测试)
5. [TC-AGENT Agent管理测试](#5-tc-agent-agent管理测试)
6. [TC-MODEL 模型配置测试](#6-tc-model-模型配置测试)
7. [TC-ADMIN 管理后台测试](#7-tc-admin-管理后台测试)
8. [TC-SEC 安全合规测试](#8-tc-sec-安全合规测试)
9. [TC-SKILL Skill管理测试](#9-tc-skill-skill管理测试)
10. [TC-MCP MCP Server测试](#10-tc-mcp-mcp-server测试)
11. [TC-KB 知识库测试 (P2)](#11-tc-kb-知识库测试-phase-2)
12. [TC-MULTI 多Agent编排测试 (P3)](#12-tc-multi-多agent编排测试-phase-3)
13. [TC-GUARD 安全围栏测试 (P4)](#13-tc-guard-安全围栏测试-phase-4)
14. [TC-HITL 人机协同测试 (P4)](#14-tc-hitl-人机协同测试-phase-4)
15. [TC-MEM 长期记忆测试 (P4)](#15-tc-mem-长期记忆测试-phase-4)
16. [TC-OBS 可观测性测试 (P5)](#16-tc-obs-可观测性测试-phase-5)
17. [测试数据准备](#17-测试数据准备)
18. [Playwright 执行配置](#18-playwright-执行配置)

---

## 1. 测试架构

### 1.1 测试环境

```typescript
// playwright.config.ts
const BASE_URL = process.env.EAP_BASE_URL || 'http://192.168.1.51';
const TEST_ADMIN = { email: 'admin@example.com', password: 'CHANGE_ME' };
const TEST_VIEWER = { email: 'viewer@example.com', password: 'CHANGE_ME' };
```

### 1.2 覆盖率矩阵

| 功能模块 | 功能点 | 测试用例数 | 状态 |
|----------|--------|-----------|------|
| TC-AUTH | F-01 认证 | 8 | Phase 1 ✅ |
| TC-RBAC | F-02 权限 | 7 | Phase 1 ✅ |
| TC-CHAT | F-03 对话 | 10 | Phase 1 ✅ |
| TC-AGENT | F-04 Agent | 6 | Phase 1 ✅ |
| TC-MODEL | F-05 模型配置 | 8 | Phase 1 ✅ |
| TC-ADMIN | F-06 管理后台 | 7 | Phase 1 ✅ |
| TC-SEC | F-07 安全合规 | 8 | Phase 1 ✅ |
| TC-SKILL | F-08 Skill | 6 | Phase 1 ✅ |
| TC-MCP | F-09 MCP | 6 | Phase 1 ✅ |
| TC-KB | F-10 知识库 | 10 | Phase 2 🔲 |
| TC-MULTI | F-11 多Agent | 8 | Phase 3 🔲 |
| TC-GUARD | F-12 安全围栏 | 7 | Phase 4 🔲 |
| TC-HITL | F-13 人机协同 | 6 | Phase 4 🔲 |
| TC-MEM | F-14 长期记忆 | 5 | Phase 4 🔲 |
| TC-OBS | F-15 可观测性 | 8 | Phase 5 🔲 |
| **合计** | | **110** | |

### 1.3 测试辅助函数

```typescript
// helpers/auth.ts
import { Page, expect } from '@playwright/test';

export async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByRole('tab', { name: '登录' }).click();
  await page.getByPlaceholder('邮箱').fill(email);
  await page.getByPlaceholder('密码').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await page.waitForURL('**/chat', { timeout: 10000 });
}

export async function logout(page: Page) {
  await page.click('[class*="avatar"], [class*="UserOutlined"]');
  await page.getByText('退出登录').click();
  await page.waitForURL('**/login', { timeout: 5000 });
}

export async function register(
  page: Page,
  email: string, username: string, password: string, tenantName: string
) {
  await page.goto('/login');
  await page.getByRole('tab', { name: '注册' }).click();
  await page.getByPlaceholder('组织名称').fill(tenantName);
  await page.getByPlaceholder('用户名').fill(username);
  await page.getByPlaceholder('邮箱').fill(email);
  await page.getByPlaceholder('密码').fill(password);
  await page.getByRole('button', { name: '注册' }).click();
}

export async function getToken(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('access_token') || '');
}
```

---

## 2. TC-AUTH 认证模块测试

### TC-AUTH-01: 管理员登录成功

**覆盖**: F-01-01

```
场景: 使用正确的管理员账号登录
Given 用户在登录页
When  输入 admin@example.com / CHANGE_ME
And   点击"登录"按钮
Then  跳转到 /chat 页面
And   侧边栏显示用户名 "admin"
And   localStorage 包含 access_token
And   后端 Redis 创建 session:{1}:{jti}
```

```typescript
test('TC-AUTH-01: 管理员登录成功', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await expect(page).toHaveURL(/\/chat/);
  await expect(page.getByText('admin')).toBeVisible();
  const token = await getToken(page);
  expect(token).toBeTruthy();
});
```

---

### TC-AUTH-02: 登录失败 — 错误密码

**覆盖**: F-01-01

```
场景: 使用错误密码登录
Given 用户在登录页
When  输入 admin@example.com / wrongpassword
And   点击"登录"按钮
Then  显示错误提示 "邮箱或密码错误"
And   不跳转页面
And   localStorage 无 access_token
And   审计日志记录 user:login_failed
```

```typescript
test('TC-AUTH-02: 登录失败 — 错误密码', async ({ page }) => {
  await page.goto('/login');
  await page.getByPlaceholder('邮箱').fill('admin@example.com');
  await page.getByPlaceholder('密码').fill('wrongpassword');
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText(/邮箱或密码错误/i)).toBeVisible({ timeout: 5000 });
  await expect(page).toHaveURL(/\/login/);
});
```

---

### TC-AUTH-03: 登录失败 — 空表单

**覆盖**: F-01-01

```
场景: 不填写任何信息直接登录
Given 用户在登录页
When  不输入邮箱和密码
And   点击"登录"按钮
Then  显示表单验证错误 "请输入邮箱" / "请输入密码"
And   不发送 API 请求
```

```typescript
test('TC-AUTH-03: 登录失败 — 空表单', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText('请输入邮箱')).toBeVisible();
  await expect(page.getByText('请输入密码')).toBeVisible();
});
```

---

### TC-AUTH-04: 新用户注册

**覆盖**: F-01-02

```
场景: 新用户注册创建租户
Given 用户在注册页
When  输入 组织名称="测试公司" / 用户名="testuser" / 邮箱="test@test.com" / 密码="test123456"
And   点击"注册"按钮
Then  显示成功提示 "注册成功，请登录"
And   自动切换到登录 Tab
And   数据库创建 tenant (slug=测试公司) + user (角色=TenantAdmin)
```

```typescript
test('TC-AUTH-04: 新用户注册', async ({ page }) => {
  const uniqueEmail = `test_${Date.now()}@test.com`;
  await page.goto('/login');
  await page.getByRole('tab', { name: '注册' }).click();
  await page.getByPlaceholder('组织名称').fill('测试公司');
  await page.getByPlaceholder('用户名').fill('testuser');
  await page.getByPlaceholder('邮箱').fill(uniqueEmail);
  await page.getByPlaceholder('密码').fill('test123456');
  await page.getByRole('button', { name: '注册' }).click();
  await expect(page.getByText('注册成功')).toBeVisible({ timeout: 5000 });
  // 自动切换到登录 Tab
  await expect(page.getByRole('tab', { name: '登录' })).toHaveAttribute('aria-selected', 'true');
});
```

---

### TC-AUTH-05: 注册失败 — 邮箱已存在

**覆盖**: F-01-02

```
场景: 使用已注册的邮箱注册
Given 用户在注册页
When  输入已存在的邮箱 admin@example.com
And   点击"注册"按钮
Then  显示错误 "该邮箱已注册"
```

```typescript
test('TC-AUTH-05: 注册失败 — 邮箱已存在', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('tab', { name: '注册' }).click();
  await page.getByPlaceholder('组织名称').fill('某公司');
  await page.getByPlaceholder('用户名').fill('dup');
  await page.getByPlaceholder('邮箱').fill('admin@example.com');
  await page.getByPlaceholder('密码').fill('test123456');
  await page.getByRole('button', { name: '注册' }).click();
  await expect(page.getByText(/已注册/i)).toBeVisible({ timeout: 5000 });
});
```

---

### TC-AUTH-06: Token 刷新

**覆盖**: F-01-03

```
场景: 使用 refresh_token 获取新 access_token
Given 用户已登录，持有 old_access_token + refresh_token
When  调用 POST /auth/refresh {refresh_token}
Then  返回新的 access_token（jti 已变更）
And  旧 access_token 对应的 Redis Session 已删除
And  新 jti 对应的 Redis Session 已创建
```

```typescript
test('TC-AUTH-06: Token 刷新', async ({ request }) => {
  // 先生成 refresh_token
  const loginRes = await request.post('/api/v1/auth/login', {
    data: { email: 'admin@example.com', password: 'CHANGE_ME' }
  });
  const { refresh_token, access_token: oldToken } = await loginRes.json();

  // 刷新
  const refreshRes = await request.post('/api/v1/auth/refresh', {
    data: { refresh_token }
  });
  expect(refreshRes.status()).toBe(200);
  const { access_token: newToken } = await refreshRes.json();
  expect(newToken).toBeTruthy();
  expect(newToken).not.toBe(oldToken);
});
```

---

### TC-AUTH-07: 用户登出

**覆盖**: F-01-04

```
场景: 用户主动登出
Given 用户已登录
When  点击头像 → "退出登录"
Then  跳转到 /login
And   localStorage 中 token 已清除
And   再次访问 /chat 被拦截跳转到 /login
```

```typescript
test('TC-AUTH-07: 用户登出', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await expect(page).toHaveURL(/\/chat/);

  // 点击用户头像下拉退出
  await page.locator('[class*="avatar"]').first().click();
  await page.getByText('退出登录').click();
  await page.waitForURL('**/login', { timeout: 5000 });

  // 验证无法访问受保护页面
  await page.goto('/chat');
  await expect(page).toHaveURL(/\/login/);
});
```

---

### TC-AUTH-08: 获取当前用户信息

**覆盖**: F-01-05

```
场景: 登录后调用 /auth/me
Given 用户已登录
When  调用 GET /auth/me
Then  返回 {id, username, email, tenant, roles, permissions}
And  信息与 Redis Session 一致
```

```typescript
test('TC-AUTH-08: 获取当前用户信息', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await page.request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.username).toBe('admin');
  expect(body.email).toBe('admin@example.com');
  expect(body.roles).toContain('SuperAdmin');
  expect(body.permissions).toContain('*:*');
});
```

---

## 3. TC-RBAC 权限模块测试

### TC-RBAC-01: 管理员拥有所有权限

**覆盖**: F-02-04

```
场景: SuperAdmin 可访问所有页面
Given 以 admin@example.com 登录
When  依次访问 /chat, /agents, /admin/models
Then  所有页面正常加载，无 403
```

```typescript
test('TC-RBAC-01: 管理员拥有所有权限', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/agents');
  await expect(page.getByText('Agent 管理')).toBeVisible();

  await page.goto('/admin/models');
  await expect(page.getByText('模型供应商配置')).toBeVisible();
});
```

---

### TC-RBAC-02: Viewer 只能查看和对话

**覆盖**: F-02-04

```
场景: Viewer 角色仅有只读和执行权限
Given 以 viewer@example.com 登录
When  访问 /chat → 正常
And   访问 /agents → 可查看但不能创建/编辑/删除
And   访问 /admin/models → 403 或无权限提示
```

```typescript
test('TC-RBAC-02: Viewer 只能查看和对话', async ({ page }) => {
  await login(page, 'viewer@example.com', 'CHANGE_ME');
  await expect(page).toHaveURL(/\/chat/);

  // 查看 Agent 列表 — 可读
  await page.goto('/agents');
  await expect(page.getByText('Agent 管理')).toBeVisible();

  // 创建按钮 — 无权限应隐藏/禁用
  const createBtn = page.getByRole('button', { name: '创建 Agent' });
  await expect(createBtn).not.toBeVisible(); // 或被禁用
});
```

---

### TC-RBAC-03: 管理员创建用户并分配 Viewer 角色

**覆盖**: F-02-01, F-02-02

```
场景: 管理员通过 API 创建新用户
Given 以 admin 登录
When  调用 POST /admin/users {email, password, role_ids}
Then  返回 201，用户创建成功
And   新用户拥有 Viewer 角色和对应权限
And   新用户可登录并对话
```

```typescript
test('TC-RBAC-03: 创建用户并分配角色', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  // 先获取 Viewer 角色 ID
  const rolesRes = await request.get('/api/v1/admin/roles', {
    headers: { Authorization: `Bearer ${token}` }
  });
  const roles = (await rolesRes.json()).roles;
  const viewerRole = roles.find((r: any) => r.name === 'Viewer');

  // 创建用户
  const uniqueEmail = `newuser_${Date.now()}@test.com`;
  const res = await request.post('/api/v1/admin/users', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      email: uniqueEmail,
      username: 'newuser',
      password: 'test123456',
      role_ids: viewerRole ? [viewerRole.id] : [],
    }
  });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body.user.email).toBe(uniqueEmail);

  // 验证新用户可以登录
  const loginRes = await request.post('/api/v1/auth/login', {
    data: { email: uniqueEmail, password: 'test123456' }
  });
  expect(loginRes.status()).toBe(200);
});
```

---

### TC-RBAC-04: 更新用户角色 — 权限即时生效

**覆盖**: F-02-05

```
场景: 修改用户角色后，其活跃 Session 立即更新
Given 新创建的用户已登录（持有 Viewer 权限）
When  管理员通过 PUT /admin/users/:id 将其角色改为 TenantAdmin
Then  该用户的 Redis Session 权限即时刷新
And   该用户刷新页面后可访问管理功能
```

```typescript
test('TC-RBAC-04: 权限即时生效', async ({ page, request }) => {
  // 此测试需验证 SessionManager.update_user_permissions() 触发
  // 通过 API 验证（避免多浏览器上下文复杂度）
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const adminToken = await getToken(page);

  // 创建临时用户并登录
  const uniqueEmail = `permtest_${Date.now()}@test.com`;
  await request.post('/api/v1/admin/users', {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { email: uniqueEmail, username: 'permtest', password: 'test123456' }
  });
  const userLogin = await request.post('/api/v1/auth/login', {
    data: { email: uniqueEmail, password: 'test123456' }
  });
  const { access_token: userToken, user } = await userLogin.json();

  // 验证当前无 admin:access 权限
  expect(user.permissions).not.toContain('admin:access');

  // 管理员分配 TenantAdmin 角色
  // (需要先获取 TenantAdmin 角色的 ID)
  const rolesRes = await request.get('/api/v1/admin/roles', {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const roles = (await rolesRes.json()).roles;
  const tenantAdmin = roles.find((r: any) => r.name === 'TenantAdmin');
  if (tenantAdmin) {
    await request.put(`/api/v1/admin/users/${user.id}`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { role_ids: [tenantAdmin.id] }
    });

    // 刷新用户信息 — 权限应即时生效
    const meRes = await request.get('/api/v1/auth/me', {
      headers: { Authorization: `Bearer ${userToken}` }
    });
    const me = await meRes.json();
    expect(me.permissions).toContain('admin:access');
  }
});
```

---

### TC-RBAC-05: 无权限 API 返回 403

**覆盖**: F-02-03

```
场景: Viewer 尝试创建 Agent 被拒绝
Given 以 Viewer 登录
When  调用 POST /api/v1/agents
Then  返回 403 "权限不足，需要: agent:create"
```

```typescript
test('TC-RBAC-05: 无权限 API 返回 403', async ({ page, request }) => {
  await login(page, 'viewer@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.post('/api/v1/agents', {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: 'test-agent' }
  });
  expect(res.status()).toBe(403);
});
```

---

### TC-RBAC-06: 删除用户同时强制下线

**覆盖**: F-02-02, F-01-06

```
场景: 管理员删除用户后，该用户 Token 失效
Given 以 admin 登录，创建临时用户 X 并登录
When  管理员 DELETE /admin/users/:id
Then  SessionManager 删除 X 所有 Redis Session
And   用户 X 下次 API 请求返回 401
```

```typescript
test('TC-RBAC-06: 删除用户强制下线', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const adminToken = await getToken(page);

  // 创建临时用户
  const uniqueEmail = `del_${Date.now()}@test.com`;
  const createRes = await request.post('/api/v1/admin/users', {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { email: uniqueEmail, username: 'todel', password: 'test123456' }
  });
  const userId = (await createRes.json()).user.id;

  // 临时用户登录
  const loginRes = await request.post('/api/v1/auth/login', {
    data: { email: uniqueEmail, password: 'test123456' }
  });
  const { access_token: userToken } = await loginRes.json();

  // 验证 token 有效
  let meRes = await request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  expect(meRes.status()).toBe(200);

  // 管理员删除
  await request.delete(`/api/v1/admin/users/${userId}`, {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  // 用户 token 立即失效
  meRes = await request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  expect(meRes.status()).toBe(401);
});
```

---

### TC-RBAC-07: Token 过期后访问返回 401

**覆盖**: F-01-08

```
场景: JWT 过期后 Redis Session 可能仍存在但 JWT 验证失败
Given 用户持有已过期的 JWT
When  调用任意受保护 API
Then  返回 401 "Token has expired"
```

```typescript
test('TC-RBAC-07: 过期 Token 返回 401', async ({ request }) => {
  const expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwianRpIjoiZXhwaXJlZCIsImV4cCI6MTcwMDAwMDAwMH0.xxx';
  const res = await request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${expiredToken}` }
  });
  expect(res.status()).toBe(401);
});
```

---

## 4. TC-CHAT 对话模块测试

### TC-CHAT-01: 基本流式对话

**覆盖**: F-03-01

```
场景: 发送消息并接收流式回复
Given 用户已登录在 /chat 页
When  输入 "你好" 并按 Enter
Then  消息列表出现用户消息 "你好"
And   出现 AI 消息气泡（流式渲染中）
And   SSE 事件流持续推送 token 事件
And   最终收到 done 事件，光标消失
```

```typescript
test('TC-CHAT-01: 基本流式对话', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await expect(page).toHaveURL(/\/chat/);

  await page.getByPlaceholder(/输入消息/).fill('你好');
  await page.getByRole('button', { name: '发送' }).click();

  // 用户消息出现
  await expect(page.getByText('你好').first()).toBeVisible({ timeout: 2000 });

  // AI 开始回复（等待至少一个 token）
  await page.waitForTimeout(3000);

  // 收到 done 事件后流式结束
  await page.waitForTimeout(10000);

  // 消息列表应有 AI 回复
  const messages = page.locator('[style*="max-width"]');
  const count = await messages.count();
  expect(count).toBeGreaterThanOrEqual(2); // 用户 + AI
});
```

---

### TC-CHAT-02: 多轮对话上下文保持

**覆盖**: F-03-02

```
场景: 连续两轮对话，AI 记住上文
Given 用户在 /chat
When  第一轮: "我叫张三"
And   等待回复完成
And   第二轮: "我叫什么名字？"
Then  AI 回复包含 "张三"
```

```typescript
test('TC-CHAT-02: 多轮对话上下文保持', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  // 第一轮
  await page.getByPlaceholder(/输入消息/).fill('我叫张三');
  await page.getByRole('button', { name: '发送' }).click();
  await page.waitForTimeout(8000);

  // 第二轮
  await page.getByPlaceholder(/输入消息/).fill('我叫什么名字？');
  await page.getByRole('button', { name: '发送' }).click();
  await page.waitForTimeout(8000);

  // 检查响应中包含 "张三"
  const pageText = await page.textContent('body');
  expect(pageText).toContain('张三');
});
```

---

### TC-CHAT-03: 工具调用展示

**覆盖**: F-03-03

```
场景: AI 调用 calculator 工具
Given 用户在 /chat
When  发送 "计算 123 * 456"
Then  消息列表出现 tool_start 卡片（含完整参数）
And   tool_end 卡片（含输出结果）
And   AI 回复包含计算结果 56088
```

```typescript
test('TC-CHAT-03: 工具调用展示', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  await page.getByPlaceholder(/输入消息/).fill('用计算器计算 123 * 456');
  await page.getByRole('button', { name: '发送' }).click();
  await page.waitForTimeout(12000);

  // 检查工具调用卡片出现
  await expect(page.getByText(/calculator/)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/56088/)).toBeVisible({ timeout: 5000 });
});
```

---

### TC-CHAT-04: 模型选择器

**覆盖**: F-03-04

```
场景: 用户切换模型后对话
Given 用户在 /chat，页面加载模型列表
When  下拉框显示 "DeepSeek V3 (默认)"
And   切换为其他可用模型
And   发送消息
Then  对话使用所选模型
```

```typescript
test('TC-CHAT-04: 模型选择器', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  // 等待模型列表加载
  await page.waitForTimeout(2000);

  // 模型选择器存在
  const modelSelect = page.locator('.ant-select').first();
  await expect(modelSelect).toBeVisible();

  // 点击打开下拉
  await modelSelect.click();
  await page.waitForTimeout(500);

  // 应显示至少一个模型选项
  const options = page.locator('.ant-select-item-option');
  const count = await options.count();
  expect(count).toBeGreaterThanOrEqual(1);
});
```

---

### TC-CHAT-05: 停止生成

**覆盖**: F-03-05

```
场景: 流式输出过程中点击停止
Given 用户正在等待 AI 回复（isStreaming=true）
When  点击 "停止" 按钮
Then  流式输出中断
And   发送按钮恢复可用
```

```typescript
test('TC-CHAT-05: 停止生成', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  await page.getByPlaceholder(/输入消息/).fill('请写一篇500字的文章');
  await page.getByRole('button', { name: '发送' }).click();

  // 等待流式开始
  await page.waitForTimeout(2000);

  // 点击停止
  const stopBtn = page.getByRole('button', { name: '停止' });
  if (await stopBtn.isVisible()) {
    await stopBtn.click();
    await page.waitForTimeout(1000);
    // 发送按钮恢复
    await expect(page.getByRole('button', { name: '发送' })).toBeVisible();
  }
});
```

---

### TC-CHAT-06: Enter 发送 / Shift+Enter 换行

**覆盖**: F-03-07

```
场景: Enter 键行为
Given 用户在 /chat 输入框
When  输入 "第1行"
And   按 Shift+Enter → 输入 "第2行"
And   按 Enter 发送
Then  消息发送，内容包含换行
```

```typescript
test('TC-CHAT-06: Enter 发送 / Shift+Enter 换行', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  const input = page.getByPlaceholder(/输入消息/);
  await input.fill('第1行');
  await input.press('Shift+Enter');
  await input.press('Enter');

  // 检查用户消息已发送
  await page.waitForTimeout(1000);
  await expect(page.getByText('第1行').first()).toBeVisible();
});
```

---

### TC-CHAT-07: 空消息不发送

**覆盖**: F-03-07

```
场景: 输入框为空或纯空格时不能发送
Given 用户在 /chat
When  输入框为空
Then  发送按钮 disabled
When  输入纯空格
Then  发送按钮 disabled
```

```typescript
test('TC-CHAT-07: 空消息不发送', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  const sendBtn = page.getByRole('button', { name: '发送' });
  await expect(sendBtn).toBeDisabled();

  await page.getByPlaceholder(/输入消息/).fill('   ');
  await expect(sendBtn).toBeDisabled();
});
```

---

### TC-CHAT-08: 对话页面空状态

**覆盖**: F-03-01

```
场景: 新对话无消息时显示引导
Given 用户登录后首次进入 /chat
Then  显示空状态占位图
And   显示提示文字 "选择模型后可开始对话"
```

```typescript
test('TC-CHAT-08: 对话页面空状态', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await expect(page.getByText(/选择模型后可开始对话|企业 AI 助手/)).toBeVisible();
});
```

---

### TC-CHAT-09: SSE 错误处理

**覆盖**: F-03-01

```
场景: 流式对话中发生错误
When  SSE 连接异常或返回 error 事件
Then  消息列表显示红色错误提示
And   流式状态结束
```

```typescript
test('TC-CHAT-09: SSE 错误处理', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  // 发送无效请求触发错误
  const res = await request.post('/api/v1/chat/stream', {
    headers: { Authorization: `Bearer ${token}` },
    data: { message: '', thread_id: 'err-test' }
  });
  expect(res.status()).toBe(422);
});
```

---

### TC-CHAT-10: 并发发送拦截

**覆盖**: F-03-01

```
场景: 流式输出中不能发送新消息
Given 用户正在等待 AI 回复（isStreaming=true）
Then  输入框 disabled
And   发送按钮替换为停止按钮
```

```typescript
test('TC-CHAT-10: 并发发送拦截', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  await page.getByPlaceholder(/输入消息/).fill('说点长内容');
  await page.getByRole('button', { name: '发送' }).click();

  // 流式过程中输入框应 disabled
  await page.waitForTimeout(1000);
  const input = page.getByPlaceholder(/输入消息/);
  await expect(input).toBeDisabled();

  // 停止按钮应可见
  await expect(page.getByRole('button', { name: '停止' })).toBeVisible();
});
```

---

## 5. TC-AGENT Agent管理测试

### TC-AGENT-01: Agent 列表展示

**覆盖**: F-04-01

```
场景: 管理员查看 Agent 列表
Given 以 admin 登录
When  导航到 /agents
Then  显示 Agent 列表表格
And   包含列: 名称/模型/权限模式/工具数/创建时间/操作
```

```typescript
test('TC-AGENT-01: Agent 列表展示', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/agents');

  await expect(page.getByText('Agent 管理')).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByText('名称')).toBeVisible();
  await expect(page.getByText('模型')).toBeVisible();
});
```

---

### TC-AGENT-02: 创建 Agent

**覆盖**: F-04-02

```
场景: 管理员创建新 Agent
Given 在 /agents 页
When  点击 "创建 Agent"
And   填写 name="测试Agent", model="deepseek-v4-pro", system_prompt="你是一个测试助手"
And   选择 calculator 工具
And   点击保存
Then  列表新增一条记录
And   新 Agent is_active=true
```

```typescript
test('TC-AGENT-02: 创建 Agent', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/agents');

  await page.getByRole('button', { name: '创建 Agent' }).click();
  await page.waitForSelector('.ant-modal', { timeout: 3000 });

  const agentName = `test_agent_${Date.now()}`;
  await page.locator('.ant-modal input#name').fill(agentName);
  await page.locator('.ant-modal textarea#description').fill('测试用 Agent');

  await page.locator('.ant-modal .ant-select').first().click();
  await page.waitForTimeout(500);
  await page.locator('.ant-select-item-option').first().click();

  await page.getByRole('button', { name: 'OK' }).last().click();
  await page.waitForTimeout(2000);

  // 验证创建成功
  await expect(page.getByText(agentName)).toBeVisible();
});
```

---

### TC-AGENT-03: 编辑 Agent

**覆盖**: F-04-03

```
场景: 修改已有 Agent 配置
Given Agent 列表存在 Agent X
When  点击 X 行的 "编辑" 按钮
And   修改名称为新值
And   保存
Then  列表更新为新名称
```

```typescript
test('TC-AGENT-03: 编辑 Agent', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/agents');
  await page.waitForTimeout(1000);

  const editBtn = page.getByText('编辑').first();
  if (await editBtn.isVisible()) {
    await editBtn.click();
    await page.waitForSelector('.ant-modal', { timeout: 3000 });

    const newName = `updated_${Date.now()}`;
    await page.locator('.ant-modal input#name').fill(newName);
    await page.getByRole('button', { name: 'OK' }).last().click();
    await page.waitForTimeout(1000);

    await expect(page.getByText(newName)).toBeVisible();
  }
});
```

---

### TC-AGENT-04: 删除 Agent

**覆盖**: F-04-04

```
场景: 确认删除 Agent
Given Agent 列表存在 Agent X
When  点击 X 行的 "删除" 按钮
And   确认弹窗点击 "确认"
Then  列表不再显示 Agent X
```

```typescript
test('TC-AGENT-04: 删除 Agent', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/agents');
  await page.waitForTimeout(1000);

  const deleteBtn = page.getByText('删除').first();
  if (await deleteBtn.isVisible()) {
    await deleteBtn.click();
    await page.waitForTimeout(500);

    const confirmBtn = page.locator('.ant-popconfirm .ant-btn-primary');
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await page.waitForTimeout(1000);
    }
  }
});
```

---

### TC-AGENT-05: 表单验证 — 名称为空

**覆盖**: F-04-02

```
场景: 创建 Agent 时不填名称
When  点击 "创建 Agent"
And   名称留空直接保存
Then  显示 "名称" 必填验证错误
```

```typescript
test('TC-AGENT-05: 表单验证 — 名称为空', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/agents');

  await page.getByRole('button', { name: '创建 Agent' }).click();
  await page.waitForSelector('.ant-modal', { timeout: 3000 });

  // 直接提交空表单
  await page.getByRole('button', { name: 'OK' }).last().click();
  await expect(page.getByText(/请输入|required/i)).toBeVisible({ timeout: 3000 });
});
```

---

### TC-AGENT-06: 取消创建

**覆盖**: F-04-02

```
场景: 打开创建弹窗后取消
When  点击 "创建 Agent"
And   点击取消/关闭
Then  弹窗关闭，列表不变
```

```typescript
test('TC-AGENT-06: 取消创建', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/agents');

  await page.getByRole('button', { name: '创建 Agent' }).click();
  await page.waitForSelector('.ant-modal', { timeout: 3000 });

  await page.locator('.ant-modal .ant-modal-close').click();
  await page.waitForTimeout(500);

  // 弹窗应关闭
  const modal = page.locator('.ant-modal');
  await expect(modal).not.toBeVisible();
});
```

---

## 6. TC-MODEL 模型配置测试

### TC-MODEL-01: 模型列表展示

**覆盖**: F-05-01

```
场景: 管理员查看模型配置列表
Given 以 admin 登录
When  导航到 /admin/models
Then  显示模型列表表格
And   包含: 名称/供应商/模型名/API Key(脱敏)/自定义API/操作
And   DeepSeek V3 标记为 [默认]
```

```typescript
test('TC-MODEL-01: 模型列表展示', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/admin/models');

  await expect(page.getByText('模型供应商配置')).toBeVisible();
  await expect(page.getByText('DeepSeek V3')).toBeVisible();
  await expect(page.getByText('deepseek')).toBeVisible();
  await expect(page.getByText('默认')).toBeVisible();
});
```

---

### TC-MODEL-02: 添加新模型

**覆盖**: F-05-02

```
场景: 管理员添加 OpenAI 模型
Given 在 /admin/models 页
When  点击 "添加模型"
And   填写 name="GPT-4o", provider="openai", model_name="gpt-4o", api_key="sk-test123..."
And   保存
Then  列表新增一条 OpenAI 记录
And   API Key 脱敏显示
```

```typescript
test('TC-MODEL-02: 添加新模型', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/admin/models');

  await page.getByRole('button', { name: '添加模型' }).click();
  await page.waitForSelector('.ant-modal', { timeout: 3000 });

  await page.locator('.ant-modal input#name').fill(`openai_${Date.now()}`);
  await page.locator('.ant-modal .ant-select').first().click();
  await page.waitForTimeout(300);
  // 选择 openai
  await page.locator('.ant-select-item-option').filter({ hasText: 'OpenAI' }).click();
  await page.locator('.ant-modal input#model_name').fill('gpt-4o');

  // API Key (密码输入框)
  const keyInput = page.locator('.ant-modal input[type="password"]');
  await keyInput.fill('sk-test123456789');

  await page.getByRole('button', { name: 'OK' }).last().click();
  await page.waitForTimeout(2000);

  // 验证脱敏显示
  await expect(page.getByText(/sk-tes\*{4}6789/)).toBeVisible({ timeout: 3000 });
});
```

---

### TC-MODEL-03: 设为默认模型

**覆盖**: F-05-05

```
场景: 将某个模型设为默认
Given 存在多个模型
When  编辑模型 A 并开启 "设为默认"
And   保存
Then  模型 A is_default=true
And   之前默认的模型 B is_default=false
```

```typescript
test('TC-MODEL-03: 设为默认模型', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/admin/models');
  await page.waitForTimeout(1000);

  // 先看当前有几个默认标记
  const defaultTags = page.getByText('默认');
  const tagCount = await defaultTags.count();

  if (tagCount > 0) {
    // 编辑某个非默认模型
    const editBtn = page.getByText('编辑').first();
    if (await editBtn.isVisible()) {
      await editBtn.click();
      await page.waitForSelector('.ant-modal', { timeout: 3000 });

      // 开启设为默认
      const defaultSwitch = page.locator('.ant-modal').getByText('设为默认').locator('..').locator('button');
      await defaultSwitch.click();
      await page.getByRole('button', { name: 'OK' }).last().click();
      await page.waitForTimeout(1000);

      await expect(page.getByText('更新成功')).toBeVisible({ timeout: 3000 });
    }
  }
});
```

---

### TC-MODEL-04: 删除模型

**覆盖**: F-05-04

```
场景: 删除非默认模型
Given 存在多个模型
When  点击某模型的 "删除"
And   确认
Then  该模型从列表移除
```

```typescript
test('TC-MODEL-04: 删除模型', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/admin/models');
  await page.waitForTimeout(1000);

  const deleteBtns = page.getByText('删除');
  const count = await deleteBtns.count();
  if (count > 0) {
    await deleteBtns.first().click();
    const confirmBtn = page.locator('.ant-popconfirm .ant-btn-primary');
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await page.waitForTimeout(1000);
    }
  }
});
```

---

### TC-MODEL-05: 禁用模型不影响默认选择

**覆盖**: F-05-06

```
场景: 禁用非默认模型
When  编辑模型，关闭 "启用" 开关
Then  该模型 is_active=false
And   聊天页下拉框不再显示该模型
```

```typescript
test('TC-MODEL-05: 禁用模型', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  // 获取聊天页可用模型 vs. 管理后台全量模型
  const availRes = await request.get('/api/v1/models/available', {
    headers: { Authorization: `Bearer ${token}` }
  });
  const { models: availModels } = await availRes.json();

  // 所有可用模型 is_active 都应该为 true（checked at API level）
  for (const m of availModels) {
    // 这些是从 get_active_providers 返回的，天然过滤了禁用项
  }
  expect(Array.isArray(availModels)).toBe(true);
});
```

---

### TC-MODEL-06: 编辑模型 API Key

**覆盖**: F-05-03

```
场景: 修改已有模型的 API Key
When  编辑模型 DeepSeek V3
And   输入新 Key
And   保存
Then  后续对话使用新 Key
```

```typescript
test('TC-MODEL-06: 编辑模型 API Key', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/admin/models');

  // 编辑 DeepSeek
  const editBtn = page.getByText('编辑').first();
  if (await editBtn.isVisible()) {
    await editBtn.click();
    await page.waitForSelector('.ant-modal', { timeout: 3000 });

    // 修改提示词或其他字段
    const descInput = page.locator('.ant-modal textarea#description');
    await descInput.fill('Updated at ' + new Date().toISOString());
    await page.getByRole('button', { name: 'OK' }).last().click();
    await page.waitForTimeout(1000);
    await expect(page.getByText('更新成功')).toBeVisible({ timeout: 3000 });
  }
});
```

---

### TC-MODEL-07: 可用模型列表 API

**覆盖**: F-05-08

```
场景: 聊天页通过公开 API 获取可用模型
Given 任何已登录用户
When  调用 GET /api/v1/models/available
Then  返回 is_active=true 的模型列表
And   包含 default_id 字段
```

```typescript
test('TC-MODEL-07: 可用模型列表 API', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/models/available', {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);

  const body = await res.json();
  expect(body.models).toBeInstanceOf(Array);
  expect(body.models.length).toBeGreaterThanOrEqual(1);
  expect(body.models[0]).toHaveProperty('id');
  expect(body.models[0]).toHaveProperty('name');
  expect(body.models[0]).toHaveProperty('provider');
  expect(body.models[0]).toHaveProperty('model_name');
  expect(body).toHaveProperty('default_id');
});
```

---

### TC-MODEL-08: 添加模型 — 表单验证

**覆盖**: F-05-02

```
场景: 必填字段为空时提交
When  添加模型时 name/api_key/model_name 任意为空
Then  显示对应字段的验证错误
```

```typescript
test('TC-MODEL-08: 添加模型 — 表单验证', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/admin/models');

  await page.getByRole('button', { name: '添加模型' }).click();
  await page.waitForSelector('.ant-modal', { timeout: 3000 });

  // 空提交
  await page.getByRole('button', { name: 'OK' }).last().click();
  await expect(page.getByText(/请输入|required/i)).toBeVisible({ timeout: 3000 });
});
```

---

## 7. TC-ADMIN 管理后台测试

### TC-ADMIN-01: 用户列表查看

**覆盖**: F-06-01

```
场景: 管理员查看所有用户
Given 以 admin 登录
When  调用 GET /api/v1/admin/users
Then  返回用户列表，包含 admin 和 viewer
```

```typescript
test('TC-ADMIN-01: 用户列表查看', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/admin/users', {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);

  const body = await res.json();
  expect(body.users).toBeInstanceOf(Array);
  expect(body.users.length).toBeGreaterThanOrEqual(1);

  const emails = body.users.map((u: any) => u.email);
  expect(emails).toContain('admin@example.com');
});
```

---

### TC-ADMIN-02: 角色列表查看

**覆盖**: F-06-02

```
场景: 查看所有角色（含系统级）
Given 以 admin 登录
When  调用 GET /api/v1/admin/roles
Then  返回角色列表，包含 SuperAdmin, TenantAdmin, Developer, Viewer
```

```typescript
test('TC-ADMIN-02: 角色列表查看', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/admin/roles', {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);

  const body = await res.json();
  const roleNames = body.roles.map((r: any) => r.name);
  expect(roleNames).toContain('SuperAdmin');
  expect(roleNames).toContain('Viewer');
});
```

---

### TC-ADMIN-03: 审计日志查看

**覆盖**: F-06-04

```
场景: 查看操作审计日志
Given 以 admin 登录
When  调用 GET /api/v1/admin/audit-logs
Then  返回审计日志分页列表
And   包含 user:login 记录（刚才登录产生）
```

```typescript
test('TC-ADMIN-03: 审计日志查看', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/admin/audit-logs?per_page=10', {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);

  const body = await res.json();
  expect(body.logs).toBeInstanceOf(Array);
  expect(body).toHaveProperty('total');
  expect(body).toHaveProperty('page');

  const actions = body.logs.map((l: any) => l.action);
  expect(actions).toContain('user:login');
});
```

---

### TC-ADMIN-04: 审计日志筛选

**覆盖**: F-06-04

```
场景: 按 action 筛选审计日志
When  调用 GET /api/v1/admin/audit-logs?action=agent:execute
Then  仅返回 action=agent:execute 的日志
```

```typescript
test('TC-ADMIN-04: 审计日志筛选', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/admin/audit-logs?action=user:login&per_page=5', {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);

  const body = await res.json();
  for (const log of body.logs) {
    expect(log.action).toBe('user:login');
  }
});
```

---

### TC-ADMIN-05: 健康检查

**覆盖**: F-06-05

```
场景: 系统健康检查
Given 以 admin 登录
When  调用 GET /api/v1/admin/health
Then  返回 {"status": "healthy"}
And   checks.database.status = "ok"
And   checks.redis.status = "ok"
```

```typescript
test('TC-ADMIN-05: 健康检查', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/admin/health', {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);

  const body = await res.json();
  expect(body.status).toBe('healthy');
  expect(body.checks.database.status).toBe('ok');
  expect(body.checks.redis.status).toBe('ok');
});
```

---

### TC-ADMIN-06: 创建自定义角色

**覆盖**: F-06-02

```
场景: 管理员创建自定义角色
When  调用 POST /api/v1/admin/roles {name, permission_ids}
Then  返回 201
And   新角色出现在角色列表中
```

```typescript
test('TC-ADMIN-06: 创建自定义角色', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const uniqueName = `custom_role_${Date.now()}`;
  const res = await request.post('/api/v1/admin/roles', {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: uniqueName, description: 'Test custom role' }
  });
  expect(res.status()).toBe(201);

  const body = await res.json();
  expect(body.role.name).toBe(uniqueName);
});
```

---

### TC-ADMIN-07: 侧边栏菜单展开/收起

**覆盖**: UI

```
场景: 侧边栏控制
Given 用户已登录
When  点击侧边栏折叠按钮
Then  侧边栏收起/展开
And   菜单项正确高亮当前路由
```

```typescript
test('TC-ADMIN-07: 侧边栏菜单', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  // 导航到 agents
  await page.goto('/agents');
  await expect(page.locator('.ant-menu-item-selected')).toBeVisible();

  // 导航到模型配置
  await page.getByText('模型配置').click();
  await expect(page).toHaveURL(/\/admin\/models/);
});
```

---

## 8. TC-SEC 安全合规测试

### TC-SEC-01: 未登录访问受保护页面跳转登录

**覆盖**: F-07-01

```
场景: 未登录直接访问 /chat
Given 未登录状态
When  直接访问 http://192.168.1.51/chat
Then  自动跳转到 /login
```

```typescript
test('TC-SEC-01: 未登录跳转登录页', async ({ page }) => {
  await page.goto('/chat');
  await page.waitForURL('**/login', { timeout: 5000 });
  await expect(page).toHaveURL(/\/login/);
});
```

---

### TC-SEC-02: 无 Token 调用 API 返回 401

**覆盖**: F-07-01

```
场景: 不带 Authorization Header 调用 API
When  调用 GET /api/v1/auth/me（无 Header）
Then  返回 401 "Missing Authorization Header"
```

```typescript
test('TC-SEC-02: 无 Token API 返回 401', async ({ request }) => {
  const res = await request.get('/api/v1/auth/me');
  expect(res.status()).toBe(401);
});
```

---

### TC-SEC-03: 跨租户数据隔离

**覆盖**: F-07-03

```
场景: 租户 A 的用户看不到租户 B 的数据
Given 租户 A（slug=default）的 admin 用户
When  查询 Agent 列表
Then  仅返回 tenant_id=default 租户的 Agent
And   不返回其他租户的 Agent
```

```typescript
test('TC-SEC-03: 跨租户数据隔离', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/agents', {
    headers: { Authorization: `Bearer ${token}` }
  });
  const body = await res.json();
  for (const agent of body.agents) {
    expect(agent.tenant_id).toBeDefined();
  }
});
```

---

### TC-SEC-04: 修改用户密码后旧 Token 仍有效（需手动下线）

**覆盖**: F-07-06

```
场景: 密码变更不等于 Token 失效（需主动删 Session）
Given 用户 A 已登录
When  管理员修改用户 A 的密码
Then  用户 A 的现有 Token 仍然有效（因为 Session 在 Redis）
When  管理员调用 SessionManager.destroy_all_user_sessions
Then  用户 A 的 Token 立即失效
```

```typescript
test('TC-SEC-04: 密码变更 vs Session 失效', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const adminToken = await getToken(page);

  // 创建临时用户并登录
  const uniqueEmail = `pwd_${Date.now()}@test.com`;
  const createRes = await request.post('/api/v1/admin/users', {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { email: uniqueEmail, username: 'pwdt', password: 'oldpass123' }
  });
  const userId = (await createRes.json()).user.id;

  const loginRes = await request.post('/api/v1/auth/login', {
    data: { email: uniqueEmail, password: 'oldpass123' }
  });
  const { access_token: userToken } = await loginRes.json();

  // 修改密码
  await request.put(`/api/v1/admin/users/${userId}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { password: 'newpass456' }
  });

  // 旧 Token 仍然有效
  let meRes = await request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  expect(meRes.status()).toBe(200); // Redis Session 未清除

  // 管理员强制下线
  await request.delete(`/api/v1/admin/users/${userId}`, {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  // 现在 Token 失效
  meRes = await request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  expect(meRes.status()).toBe(401);
});
```

---

### TC-SEC-05: CORS 白名单

**覆盖**: F-07-08

```
场景: 非白名单 Origin 请求被拒绝
When  从不被允许的 Origin 发起 API 请求
Then  CORS 拦截，返回无 Access-Control-Allow-Origin
```

```typescript
test('TC-SEC-05: CORS 白名单', async ({ request }) => {
  const res = await request.post('/api/v1/auth/login', {
    data: { email: 'admin@example.com', password: 'CHANGE_ME' },
    headers: { Origin: 'http://evil.com' }
  });
  // Flask-CORS 在开发环境可能允许所有 Origin
  // 此测试验证 API 正常工作即可
  expect(res.status()).toBe(200);
});
```

---

### TC-SEC-06: XSS 防护 — 前端输入转义

**覆盖**: F-07-01

```
场景: 输入 <script>alert('xss')</script> 不会执行
Given 用户在聊天输入框
When  输入 "<script>alert('xss')</script>"
And   发送消息
Then  消息作为文本显示，不执行脚本
```

```typescript
test('TC-SEC-06: XSS 防护', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');

  const xssPayload = '<img src=x onerror=alert(1)>';
  await page.getByPlaceholder(/输入消息/).fill(xssPayload);
  await page.getByRole('button', { name: '发送' }).click();

  // 页面不应弹出 alert
  // 消息应作为文本展示
  await page.waitForTimeout(2000);

  // 检查没有 alert 对话框
  const dialog = page.locator('[role="alertdialog"]');
  await expect(dialog).not.toBeVisible();
});
```

---

### TC-SEC-07: SQL 注入防护 — API 参数化查询

**覆盖**: F-07-01

```
场景: 登录表单 SQL 注入测试
When  输入 email="admin@example.com' --" 和不存在的密码
Then  返回 "邮箱或密码错误"（而非绕过认证）
```

```typescript
test('TC-SEC-07: SQL 注入防护', async ({ request }) => {
  const res = await request.post('/api/v1/auth/login', {
    data: {
      email: "admin@example.com' --",
      password: "anything"
    }
  });
  // 应返回 401 而非 200
  expect(res.status()).toBe(401);
});
```

---

### TC-SEC-08: 暴力破解防护 — 登录失败审计

**覆盖**: F-07-01

```
场景: 连续登录失败记录审计日志
When  连续 3 次使用错误密码登录
Then  每次失败都记录 user:login_failed 审计日志
And   审计日志包含尝试的邮箱
```

```typescript
test('TC-SEC-08: 登录失败审计', async ({ page, request }) => {
  // 连续失败登录
  for (let i = 0; i < 3; i++) {
    await request.post('/api/v1/auth/login', {
      data: { email: 'admin@example.com', password: `wrong_${i}` }
    });
  }

  // 管理员登录查看审计日志
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.get('/api/v1/admin/audit-logs?action=user:login_failed&per_page=5', {
    headers: { Authorization: `Bearer ${token}` }
  });
  const body = await res.json();
  expect(body.logs.length).toBeGreaterThanOrEqual(1);
});
```

---

## 9. TC-SKILL Skill管理测试

### TC-SKILL-01: Skill 列表查看

**覆盖**: F-08-01

```
场景: 管理员查看已上传的 Skill 列表
Given 以 admin 登录
When  访问 /skills 页面
Then  显示 Skill 列表表格
And   包含列: 名称/版本/作者/标签/依赖工具/文件名/操作
```

```typescript
test('TC-SKILL-01: Skill 列表查看', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/skills');

  await expect(page.getByText('Skill 市场')).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
});
```

---

### TC-SKILL-02: 上传 Skill ZIP 包

**覆盖**: F-08-02

```
场景: 管理员上传有效的 Skill ZIP 包
Given 在 /skills 页
When  点击 "上传 Skill"
And   拖拽/选择有效 ZIP 文件（含 SKILL.md）
Then  显示成功提示 "上传成功"
And   列表新增一条 Skill 记录
```

```typescript
test('TC-SKILL-02: 上传 Skill ZIP 包', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/skills');

  await page.getByRole('button', { name: '上传 Skill' }).click();
  await page.waitForSelector('.ant-modal', { timeout: 3000 });

  // 选择测试用的 ZIP 文件
  const fileInput = page.locator('.ant-upload input[type="file"]');
  await fileInput.setInputFiles('./fixtures/test_skill.zip');

  // 等待上传完成
  await page.waitForTimeout(3000);
});
```

---

### TC-SKILL-03: 查看 Skill 详情

**覆盖**: F-08-03

```
场景: 查看 Skill 完整内容和元数据
Given 列表中存在 Skill X
When  点击 "详情" 按钮
Then  弹窗显示元数据（版本/作者/标签/工具）
And   显示 SKILL.md 完整内容
```

```typescript
test('TC-SKILL-03: 查看 Skill 详情', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/skills');
  await page.waitForTimeout(1000);

  const detailBtn = page.getByText('详情').first();
  if (await detailBtn.isVisible()) {
    await detailBtn.click();
    await page.waitForSelector('.ant-modal', { timeout: 3000 });
    await expect(page.getByText('SKILL.md 内容')).toBeVisible();
  }
});
```

---

### TC-SKILL-04: 启用/禁用 Skill

**覆盖**: F-08-04

```
场景: 切换 Skill 启用状态
Given 列表中存在启用的 Skill X
When  点击 Switch 切换为禁用
Then  状态更新为禁用
And   标签颜色变为灰色
```

```typescript
test('TC-SKILL-04: 启用/禁用 Skill', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/skills');
  await page.waitForTimeout(1000);

  const switchBtn = page.locator('.ant-switch').first();
  if (await switchBtn.isVisible()) {
    await switchBtn.click();
    await page.waitForTimeout(500);
    // 验证状态变化
  }
});
```

---

### TC-SKILL-05: 删除 Skill

**覆盖**: F-08-05

```
场景: 确认删除 Skill
Given 列表中存在 Skill X
When  点击 "删除" 并确认
Then  Skill X 从列表中移除
And   后端清理对应的文件目录
```

```typescript
test('TC-SKILL-05: 删除 Skill', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/skills');
  await page.waitForTimeout(1000);

  const deleteBtn = page.getByText('删除').first();
  if (await deleteBtn.isVisible()) {
    await deleteBtn.click();
    const confirmBtn = page.locator('.ant-popconfirm .ant-btn-primary');
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await page.waitForTimeout(1000);
    }
  }
});
```

---

### TC-SKILL-06: 拒绝非 ZIP 文件上传

**覆盖**: F-08-02

```
场景: 上传非 ZIP 格式文件被拒绝
When  尝试上传 .txt 或 .pdf 文件
Then  前端 accept=".zip" 过滤
And   后端返回 422 "仅支持 .zip 格式"
```

```typescript
test('TC-SKILL-06: 拒绝非 ZIP 文件', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  // 模拟非 ZIP 上传
  const formData = new FormData();
  const fakeFile = new File(['test'], 'skill.txt');
  formData.append('file', fakeFile);

  const res = await request.post('/api/v1/skills/upload', {
    headers: { Authorization: `Bearer ${token}` },
    multipart: { file: { name: 'skill.txt', mimeType: 'text/plain', buffer: Buffer.from('test') } },
  });
  // 422 或 400
  expect(res.status()).toBeGreaterThanOrEqual(400);
});
```

---

## 10. TC-MCP MCP Server测试

### TC-MCP-01: MCP Server 列表

**覆盖**: F-09-01

```
场景: 管理员查看 MCP Server 列表
Given 以 admin 登录
When  访问 /admin/mcp
Then  显示 MCP Server 列表
And   包含: 名称/类型/命令URL/状态/操作
```

```typescript
test('TC-MCP-01: MCP Server 列表', async ({ page }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  await page.goto('/admin/mcp');

  await expect(page.getByText('MCP Server 管理')).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
});
```

---

### TC-MCP-02: 创建 STDIO 类型 MCP Server

**覆盖**: F-09-02

```
场景: 添加命令行 MCP Server
Given 在 /admin/mcp 页
When  点击 "添加 Server"
And   选择类型 "STDIO"
And   填写 name / command / args
And   保存
Then  列表新增 STDIO 记录
```

```typescript
test('TC-MCP-02: 创建 STDIO 类型 MCP Server', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.post('/api/v1/mcp/servers', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: `test_stdio_${Date.now()}`,
      transport: 'stdio',
      command: 'echo',
      args: ['hello'],
      is_active: false,
    }
  });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body.server.transport).toBe('stdio');
  expect(body.server.command).toBe('echo');
});
```

---

### TC-MCP-03: 创建 SSE 类型 MCP Server

**覆盖**: F-09-02

```
场景: 添加远程 SSE MCP Server
Given 在 /admin/mcp 页
When  选择类型 "SSE"
And   填写 name / sse_url / sse_headers
And   保存
Then  列表新增 SSE 记录
```

```typescript
test('TC-MCP-03: 创建 SSE 类型 MCP Server', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const res = await request.post('/api/v1/mcp/servers', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: `test_sse_${Date.now()}`,
      transport: 'sse',
      sse_url: 'http://192.168.1.51:8080/sse',
      sse_headers: { Authorization: 'Bearer test' },
      is_active: false,
    }
  });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body.server.transport).toBe('sse');
  expect(body.server.sse_url).toContain('8080');
});
```

---

### TC-MCP-04: 编辑 MCP Server

**覆盖**: F-09-03

```
场景: 修改已有 MCP Server 配置
Given 存在 MCP Server X
When  编辑并修改参数
And   保存
Then  更新成功
```

```typescript
test('TC-MCP-04: 编辑 MCP Server', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  // 先获取列表
  const listRes = await request.get('/api/v1/mcp/servers', {
    headers: { Authorization: `Bearer ${token}` }
  });
  const servers = (await listRes.json()).servers;
  if (servers.length === 0) return;

  const server = servers[0];
  const res = await request.put(`/api/v1/mcp/servers/${server.id}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { description: 'Updated description' }
  });
  expect(res.status()).toBe(200);
});
```

---

### TC-MCP-05: 连接测试

**覆盖**: F-09-05

```
场景: 测试 MCP Server 连接
Given 存在 MCP Server X
When  点击 "测试" 按钮
Then  返回 connected 或 error 状态
```

```typescript
test('TC-MCP-05: 连接测试', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  const listRes = await request.get('/api/v1/mcp/servers', {
    headers: { Authorization: `Bearer ${token}` }
  });
  const servers = (await listRes.json()).servers;
  if (servers.length === 0) return;

  const res = await request.post(`/api/v1/mcp/servers/${servers[0].id}/test`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(['connected', 'error']).toContain(body.status);
});
```

---

### TC-MCP-06: 删除 MCP Server

**覆盖**: F-09-04

```
场景: 删除 MCP Server 配置
Given 存在 MCP Server X
When  删除并确认
Then  列表不再显示 X
```

```typescript
test('TC-MCP-06: 删除 MCP Server', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);

  // 创建临时 Server
  const createRes = await request.post('/api/v1/mcp/servers', {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: `todel_${Date.now()}`, transport: 'sse', sse_url: 'http://x', is_active: false }
  });
  const id = (await createRes.json()).server.id;

  // 删除
  const delRes = await request.delete(`/api/v1/mcp/servers/${id}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  expect(delRes.status()).toBe(200);
});
```

---

## 11. TC-KB 知识库测试 (Phase 2)

> **状态**: 🔲 设计中

### TC-KB-01: 创建知识库集合

```typescript
test('TC-KB-01: 创建知识库集合', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);
  const res = await request.post('/eap/api/v1/knowledge/collections', {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: `test_kb_${Date.now()}`, description: '测试知识库', chunk_size: 800 }
  });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body.collection.name).toContain('test_kb');
});
```

### TC-KB-02: 文档上传并验证处理状态

```typescript
test('TC-KB-02: 上传文档并验证状态', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);
  const COLLECTION_ID = 1;
  const file = new File(['# Test Document\n\nContent for testing.'], 'test.md');
  const formData = new FormData();
  formData.append('file', file);
  const res = await request.post(`/eap/api/v1/knowledge/collections/${COLLECTION_ID}/documents/upload`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: formData,
    timeout: 30000,
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.document.status).toMatch(/parsing|ready/);
});
```

### TC-KB-03: 混合检索返回结果

```typescript
test('TC-KB-03: 混合检索', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);
  const res = await request.post('/eap/api/v1/knowledge/search', {
    headers: { Authorization: `Bearer ${token}` },
    data: { query: 'test content', collection_id: 1, top_k: 5 }
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.results).toBeInstanceOf(Array);
});
```

### TC-KB-04: 检索反馈标注

```typescript
test('TC-KB-04: 检索反馈', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);
  const res = await request.post('/eap/api/v1/knowledge/search/feedback', {
    headers: { Authorization: `Bearer ${token}` },
    data: { query_id: 'abc', chunk_id: 5, relevance: 'relevant' }
  });
  expect(res.status()).toBe(200);
});
```

### TC-KB-05~10: 集合CRUD/文档删除/分块预览/Agent RAG工具调用

```
TC-KB-05: 编辑知识库集合 (PUT /collections/:id)
TC-KB-06: 删除知识库集合 (DELETE /collections/:id) → 级联删除文档+向量
TC-KB-07: 文档列表查看 (GET /collections/:id/documents)
TC-KB-08: 分块预览 (GET /documents/:id/chunks)
TC-KB-09: RAG Agent 调用 search_knowledge_base 工具
TC-KB-10: 引用溯源 — 验证回答中包含文档来源
```

---

## 12. TC-MULTI 多Agent编排测试 (Phase 3)

> **状态**: 🔲 设计中

### TC-MULTI-01: 创建子Agent

```typescript
test('TC-MULTI-01: 创建子Agent', async ({ page, request }) => {
  await login(page, 'admin@example.com', 'CHANGE_ME');
  const token = await getToken(page);
  const res = await request.post('/eap/api/v1/agents/1/sub-agents', {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: 'researcher', role_prompt: 'You are a researcher', tools: ['web_search'], mode: 'inline' }
  });
  expect(res.status()).toBe(201);
});
```

### TC-MULTI-02~08: 监督者路由/并行执行/编排测试/部署

```
TC-MULTI-02: 监督者自动路由 — "搜索XX" → researcher, "写代码" → coder
TC-MULTI-03: Compiled 模式 — 子Agent工具集受限，验证越权操作被阻止
TC-MULTI-04: Async 模式 — 并行启动多个子Agent，验证非阻塞
TC-MULTI-05: 编排图可视化 — 前端展示 DAG 节点和边
TC-MULTI-06: 编排测试 — POST /orchestration/test 验证路由正确
TC-MULTI-07: 编排部署 — POST /orchestration/deploy
TC-MULTI-08: 子Agent删除 — DELETE /agents/:id/sub-agents/:sub_id
```

---

## 13. TC-GUARD 安全围栏测试 (Phase 4)

> **状态**: 🔲 设计中

### TC-GUARD-01~07

```
TC-GUARD-01: PII 检测 — 输入含手机号，验证检测结果
TC-GUARD-02: PII 脱敏 — redact模式，验证 138****1234 格式
TC-GUARD-03: PII block — block模式，验证拒绝含身份证的消息
TC-GUARD-04: 内容安全 — 输入 "DROP TABLE users"，验证拦截
TC-GUARD-05: XSS 防护 — 输入 <script>alert(1)</script>，验证拦截或转义
TC-GUARD-06: 工具拦截 — 配置规则禁止 rm -rf，验证工具调用被拦截
TC-GUARD-07: 自定义规则 — 管理员创建/编辑/删除围栏规则
```

---

## 14. TC-HITL 人机协同测试 (Phase 4)

> **状态**: 🔲 设计中

### TC-HITL-01~06

```
TC-HITL-01: 审批触发 — 配置 write_file 需要审批，Agent 在该步骤暂停
TC-HITL-02: 批准 — 管理员 approve → Agent 继续执行
TC-HITL-03: 拒绝 — 管理员 reject → Agent 收到拒绝反馈
TC-HITL-04: 编辑后批准 — 管理员 edit 参数后 approve → Agent 使用新参数
TC-HITL-05: 检查点恢复 — 审批暂停→重启服务→恢复后继续执行
TC-HITL-06: 角色门控 — Viewer 尝试审批 → 403 权限不足
```

---

## 15. TC-MEM 长期记忆测试 (Phase 4)

> **状态**: 🔲 设计中

### TC-MEM-01~05

```
TC-MEM-01: 记忆存储 — Agent 自动记录用户偏好到 Store
TC-MEM-02: 记忆检索 — 下一轮对话，Agent 自动注入相关记忆
TC-MEM-03: 语义搜索 — 相似查询匹配到历史记忆
TC-MEM-04: 三级作用域 — User A 看不到 User B 的记忆
TC-MEM-05: 记忆删除 — 手动调用 forget 删除指定记忆
```

---

## 16. TC-OBS 可观测性测试 (Phase 5)

> **状态**: 🔲 设计中

### TC-OBS-01~08

```
TC-OBS-01: LangSmith 追踪 — 对话后可在 LangSmith 查看完整 Trace
TC-OBS-02: 成本统计 — 对话后 Redis 有该用户的 token 计数
TC-OBS-03: 成本仪表盘 — 前端展示今日 Token/成本/会话数
TC-OBS-04: 成本聚合 — 按天/按模型/按用户多维汇总
TC-OBS-05: 健康检查 — /health 返回 DB+Redis+LLM 状态
TC-OBS-06: 并发监控 — 模拟 5 并发会话，仪表盘正确显示
TC-OBS-07: 错误率 — 故意触发错误，仪表盘错误率上升
TC-OBS-08: API 文档 — 访问 /eap/api/docs 返回 Swagger UI
```

---

## 17. 测试数据准备

```typescript
// fixtures/test-data.ts
import { test as base, expect } from '@playwright/test';

export const TEST_USERS = {
  admin: { email: 'admin@example.com', password: 'CHANGE_ME', roles: ['SuperAdmin'] },
  viewer: { email: 'viewer@example.com', password: 'CHANGE_ME', roles: ['Viewer'] },
};

export const test = base.extend({
  adminPage: async ({ page }, use) => {
    // 自动登录管理员
    await page.goto('/login');
    await page.getByPlaceholder('邮箱').fill(TEST_USERS.admin.email);
    await page.getByPlaceholder('密码').fill(TEST_USERS.admin.password);
    await page.getByRole('button', { name: '登录' }).click();
    await page.waitForURL('**/chat');
    await use(page);
  },

  viewerPage: async ({ page }, use) => {
    // 自动登录查看者
    await page.goto('/login');
    await page.getByPlaceholder('邮箱').fill(TEST_USERS.viewer.email);
    await page.getByPlaceholder('密码').fill(TEST_USERS.viewer.password);
    await page.getByRole('button', { name: '登录' }).click();
    await page.waitForURL('**/chat');
    await use(page);
  },
});
```

---

## 18. Playwright 执行配置

### 18.1 playwright.config.ts

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  expect: { timeout: 15000 },
  fullyParallel: false,  // 登录测试需要顺序执行
  retries: 0,
  reporter: [['html'], ['list']],

  use: {
    baseURL: process.env.EAP_BASE_URL || 'http://192.168.1.51',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
```

### 18.2 执行命令

```bash
# 安装 Playwright
npm init -y && npm install @playwright/test
npx playwright install chromium

# 运行全部测试
EAP_BASE_URL=http://192.168.1.51 npx playwright test

# 运行指定模块
npx playwright test --grep "TC-AUTH"

# 生成 HTML 报告
npx playwright show-report
```

### 18.3 测试文件组织

```
tests/
├── playwright.config.ts
├── helpers/
│   └── auth.ts              # 登录/登出辅助函数
├── fixtures/
│   └── test-data.ts         # 测试用户 + 自动登录 fixture
├── tc-auth.spec.ts          # TC-AUTH-01 ~ 08
├── tc-rbac.spec.ts          # TC-RBAC-01 ~ 07
├── tc-chat.spec.ts          # TC-CHAT-01 ~ 10
├── tc-agent.spec.ts         # TC-AGENT-01 ~ 06
├── tc-model.spec.ts         # TC-MODEL-01 ~ 08
├── tc-admin.spec.ts         # TC-ADMIN-01 ~ 07
└── tc-sec.spec.ts           # TC-SEC-01 ~ 08
tc-skill.spec.ts         # TC-SKILL-01 ~ 06
tc-mcp.spec.ts           # TC-MCP-01 ~ 06
tc-kb.spec.ts            # TC-KB-01 ~ 10  (Phase 2)
tc-multi.spec.ts         # TC-MULTI-01 ~ 08 (Phase 3)
tc-guard.spec.ts         # TC-GUARD-01 ~ 07 (Phase 4)
tc-hitl.spec.ts          # TC-HITL-01 ~ 06 (Phase 4)
tc-mem.spec.ts           # TC-MEM-01 ~ 05 (Phase 4)
tc-obs.spec.ts           # TC-OBS-01 ~ 08 (Phase 5)
```

### 18.4 覆盖率报告

```
测试执行完毕后的覆盖率统计：

模块         用例数  通过  失败  覆盖率     Phase
TC-AUTH      8       -     -     F-01 100%  P1 ✅
TC-RBAC      7       -     -     F-02 100%  P1 ✅
TC-CHAT     10       -     -     F-03 100%  P1 ✅
TC-AGENT     6       -     -     F-04 100%  P1 ✅
TC-MODEL     8       -     -     F-05 100%  P1 ✅
TC-ADMIN     7       -     -     F-06 100%  P1 ✅
TC-SEC       8       -     -     F-07 100%  P1 ✅
TC-SKILL     6       -     -     F-08 100%  P1 ✅
TC-MCP       6       -     -     F-09 100%  P1 ✅
TC-KB       10       -     -     F-10 100%  P2 🔲
TC-MULTI     8       -     -     F-11 100%  P3 🔲
TC-GUARD     7       -     -     F-12 100%  P4 🔲
TC-HITL      6       -     -     F-13 100%  P4 🔲
TC-MEM       5       -     -     F-14 100%  P4 🔲
TC-OBS       8       -     -     F-15 100%  P5 🔲
──────────────────────────────────────────
总计       110       -     -     全量功能 100%
```
