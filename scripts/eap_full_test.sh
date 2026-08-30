#!/bin/bash
# EAP 全功能测试套件
BASE="http://192.168.1.51/eap/api/v1"
OUT=/tmp/eap_ft
# 本地凭据（禁止提交仓库）：scripts/.test.env 中写
#   EAP_TEST_ADMIN_PW=xxx  EAP_TEST_VIEWER_PW=xxx
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/.test.env" ] && . "$SCRIPT_DIR/.test.env"
ADMIN_EMAIL="admin@example.com"
ADMIN_PW="${EAP_TEST_ADMIN_PW:-}"
VIEWER_EMAIL="viewer@example.com"
VIEWER_PW="${EAP_TEST_VIEWER_PW:-}"
mkdir -p $OUT
PASS=0; FAIL=0; WARN=0
declare -a FAILED=()

ok()   { PASS=$((PASS+1)); echo "  ✅ $1"; }
bad()  { FAIL=$((FAIL+1)); FAILED+=("$1"); echo "  ❌ $1"; }
warn() { WARN=$((WARN+1)); echo "  ⚠️ $1"; }

# python 提取 JSON
jget() { python3 -c "
import sys, json
d = json.load(sys.stdin)
try:
    v = eval(sys.argv[1])
    print(v if v is not None else '')
except Exception as e:
    print('')
" "$1" 2>/dev/null; }

# SSE 聊天: chat <agent_id> <message> [thread_id] → 事件文件路径
chat() {
    local aid="$1" msg="$2" tid="${3:-}" f="$OUT/sse_${4:-chat}.txt"
    local body
    if [ -z "$tid" ]; then
        body="{\"message\":$(python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$msg"),\"agent_id\":$aid}"
    else
        body="{\"message\":$(python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$msg"),\"agent_id\":$aid,\"thread_id\":\"$tid\"}"
    fi
    curl -sN -X POST "$BASE/chat/stream" -H "Authorization: Bearer $ATOKEN" \
      -H "Content-Type: application/json" -d "$body" --max-time 150 > "$f" 2>&1
    echo "$f"
}

# 从 SSE 文件提取信息
sse_ok()      { grep -q '"type": "done"' "$1"; }
sse_error()   { grep -oE '"type": "error".*' "$1" | head -1; }
sse_thread()  { grep -oE '"thread_id": "[^"]+"' "$1" | head -1 | sed 's/.*: "//;s/"//'; }
sse_tools()   { grep -oE '"type": "tool_start", "tool": "[^"]+"' "$1" | sed 's/.*"tool": "//'; }
sse_reply()   { grep -oE '"type": "token", "content": "[^"]*"' "$1" | sed 's/.*"content": "//;s/"$//' | tr -d '\n' | head -c 300; }
sse_full_thread() { grep -oE '"full_thread_id": "[^"]+"' "$1" | head -1 | sed 's/.*"full_thread_id": "//;s/"//'; }
# 第一条 interrupt 事件（整行 JSON）
sse_interrupt() { python3 -c "
import sys, json
for line in open(sys.argv[1], encoding='utf-8'):
    if line.startswith('data: '):
        try: d = json.loads(line[6:])
        except Exception: continue
        if d.get('type') == 'interrupt':
            print(json.dumps(d, ensure_ascii=False)); break
" "$1"; }

# HITL 恢复: resume <agent_id> <thread_id> <文件名> → SSE 事件文件路径
# 恢复值来自该线程已决议的审批（approve/reject/edit），message 为空
resume() {
    local aid="$1" tid="$2" f="$OUT/sse_${3:-resume}.txt"
    curl -sN -X POST "$BASE/chat/stream" -H "Authorization: Bearer $ATOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"resume\":true,\"thread_id\":\"$tid\",\"agent_id\":$aid}" \
      --max-time 150 > "$f" 2>&1
    echo "$f"
}

echo "=========================================="
echo "EAP 全功能测试  $(date '+%F %T')"
echo "=========================================="

# ================= Phase A: 认证与 RBAC =================
echo ""
echo "【Phase A】认证与 RBAC"

ADMIN_LOGIN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PW\"}")
ATOKEN=$(echo "$ADMIN_LOGIN" | jget "d['access_token']")
[ -n "$ATOKEN" ] && ok "A1 管理员登录" || bad "A1 管理员登录: $ADMIN_LOGIN"

VIEWER_LOGIN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"$VIEWER_EMAIL\",\"password\":\"$VIEWER_PW\"}")
VTOKEN=$(echo "$VIEWER_LOGIN" | jget "d['access_token']")
[ -n "$VTOKEN" ] && ok "A2 Viewer 登录" || bad "A2 Viewer 登录: $VIEWER_LOGIN"

S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"wrongpass123"}')
[ "$S" = "401" ] && ok "A3 错误密码 → 401" || bad "A3 错误密码应 401, 实际 $S"

ME=$(curl -s "$BASE/auth/me" -H "Authorization: Bearer $ATOKEN")
UNAME=$(echo "$ME" | jget "d.get('username','')")
[ "$UNAME" = "admin" ] && ok "A4 /auth/me 身份正确" || bad "A4 /auth/me: $ME"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/agents")
[ "$S" = "401" ] && ok "A5 无 token → 401" || bad "A5 无 token 应 401, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/agents" -H "Authorization: Bearer $VTOKEN")
[ "$S" = "200" ] && ok "A6 Viewer 可读 agents" || bad "A6 Viewer 读 agents 应 200, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/agents" -H "Authorization: Bearer $VTOKEN" -H "Content-Type: application/json" -d '{"name":"hack"}')
[ "$S" = "403" ] && ok "A7 Viewer 建 agent → 403" || bad "A7 Viewer 建 agent 应 403, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/monitor/dashboard" -H "Authorization: Bearer $VTOKEN")
[ "$S" = "403" ] && ok "A8 Viewer 访问监控 → 403" || bad "A8 Viewer 访问监控应 403, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/monitor/dashboard" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "A9 Admin 访问监控 → 200" || bad "A9 Admin 访问监控应 200, 实际 $S"

# ================= Phase B: CRUD =================
echo ""
echo "【Phase B】CRUD 接口"

# --- 启动清理：只删除 ft_ 前缀的测试残留（幂等，绝不触碰生产数据） ---
# 直接解析 JSON 响应，按 name 的 ft_ 前缀过滤（agents/skills/knowledge/mcp 一致）
for ep in "agents" "skills" "knowledge/collections" "mcp/servers"; do
  curl -s "$BASE/$ep" -H "Authorization: Bearer $ATOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for k, v in d.items():
    if isinstance(v, list):
        for it in v:
            if 'ft_' in (it.get('name') or ''):
                print(it.get('id', ''))
" | while read -r iid; do
    [ -z "$iid" ] && continue
    curl -s -X DELETE "$BASE/$ep/$iid" -H "Authorization: Bearer $ATOKEN" > /dev/null 2>&1
  done
done
echo "  (启动清理完成: 仅 ft_ 前缀数据)"

# --- Skills ---
R=$(curl -s -X POST "$BASE/skills" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_code_style","description":"代码风格检查规则","mode":"prompt","prompt":"你是代码风格检查员：检查缩进、命名规范、注释完整性。输出格式：问题列表。"}')
SK1=$(echo "$R" | jget "d.get('skill',{}).get('id')")
[ -n "$SK1" ] && ok "B1 创建 prompt-mode skill" || bad "B1 创建 prompt skill: $R"

R=$(curl -s -X POST "$BASE/skills" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_translator","description":"中英翻译","mode":"agent","prompt":"你是专业翻译。把输入的中文翻译成英文，只输出译文。"}')
SK2=$(echo "$R" | jget "d.get('skill',{}).get('id')")
[ -n "$SK2" ] && ok "B2 创建 agent-mode skill" || bad "B2 创建 agent skill: $R"

R=$(curl -s -X POST "$BASE/skills" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_中文技能","description":"中文名技能测试","mode":"agent","prompt":"你是中文技能测试，收到输入后回复：中文技能已执行。"}')
SK3=$(echo "$R" | jget "d.get('skill',{}).get('id')")
[ -n "$SK3" ] && ok "B3 创建中文名 agent-mode skill" || bad "B3 创建中文名 skill: $R"

S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/skills" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{"name":"ft_code_style","description":"dup"}')
[ "$S" = "409" ] && ok "B4 重名 skill → 409" || bad "B4 重名应 409, 实际 $S"

R=$(curl -s "$BASE/skills/$SK2" -H "Authorization: Bearer $ATOKEN")
PROMPT=$(echo "$R" | jget "d.get('skill',{}).get('prompt','')")
[ -n "$PROMPT" ] && ok "B5 skill 详情含 prompt" || bad "B5 skill 详情: $R"

# --- ZIP 上传 ---
rm -rf /tmp/ft_zip && mkdir -p /tmp/ft_zip/zipsub/references /tmp/ft_zip/zipsub/scripts /tmp/ft_zip/zipsub/data
cat > /tmp/ft_zip/zipsub/SKILL.md <<'EOF'
---
name: ft_zipsub
description: ZIP 打包技能测试
mode: prompt
version: 1.0.0
---
你是 ZIP 技能测试员。回答时先引用参考资料，再输出结论。
EOF
echo "ZIP 参考文档：EAP 打包技能验证内容 ABC123" > /tmp/ft_zip/zipsub/references/guide.md
echo "print('hello from zip script')" > /tmp/ft_zip/zipsub/scripts/run.py
echo '{"key": "zip_data"}' > /tmp/ft_zip/zipsub/data/config.json
(cd /tmp/ft_zip && zip -qr zipsub.zip zipsub)
R=$(curl -s -X POST "$BASE/skills/upload" -H "Authorization: Bearer $ATOKEN" -F "file=@/tmp/ft_zip/zipsub.zip")
SK4=$(echo "$R" | jget "d.get('skill',{}).get('id')")
[ -n "$SK4" ] && ok "B6 ZIP 上传 skill" || bad "B6 ZIP 上传: $R"

S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/skills/upload" -H "Authorization: Bearer $ATOKEN" -F "file=@/tmp/ft_zip/zipsub.zip")
[ "$S" = "422" ] && ok "B7 重复 ZIP → 422" || bad "B7 重复 ZIP 应 422, 实际 $S"

R=$(curl -s -X POST "$BASE/skills/$SK1/toggle" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{"is_active":false}')
ACT=$(echo "$R" | jget "d.get('skill',{}).get('is_active')")
[ "$ACT" = "False" ] && ok "B8 toggle 停用" || bad "B8 toggle: $R"
curl -s -X POST "$BASE/skills/$SK1/toggle" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{"is_active":true}' > /dev/null

# --- Agent ---
R=$(curl -s -X POST "$BASE/agents" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{
  "name":"ft_全功能测试","description":"全功能回归测试 agent",
  "model":"deepseek-v4-pro",
  "system_prompt":"你是全功能测试助手，按用户要求调用工具。",
  "tools_config":["calculator","datetime","web_search","code_execution","knowledge_search","memory_save","memory_search"],
  "skills":["ft_translator","ft_code_style"],
  "permission_mode":"default","max_turns":30}')
AID=$(echo "$R" | jget "d.get('agent',{}).get('id')")
[ -n "$AID" ] && ok "B9 创建测试 agent" || bad "B9 创建 agent: $R"

R=$(curl -s -X POST "$BASE/agents" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{
  "name":"ft_中文技能agent","description":"中文技能名测试",
  "model":"deepseek-v4-pro",
  "system_prompt":"你是测试助手。",
  "tools_config":["calculator"],
  "skills":["ft_中文技能"]}')
AID2=$(echo "$R" | jget "d.get('agent',{}).get('id')")
[ -z "$AID2" ] && bad "B10 创建中文技能 agent 无 ID: $R"
[ -n "$AID2" ] && ok "B10 创建中文技能 agent" || bad "B10 创建中文技能 agent: $R"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/agents/$AID" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B11 agent 详情" || bad "B11 agent 详情应 200, 实际 $S"

# --- 子 Agent ---
R=$(curl -s -X POST "$BASE/agents/$AID/sub-agents" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_researcher","role_prompt":"你是研究助理，擅长资料整理与总结，输出简洁要点。","mode":"inline"}')
SUBID=$(echo "$R" | jget "d.get('sub_agent',{}).get('id')")
[ -n "$SUBID" ] && ok "B12 创建子 agent" || bad "B12 创建子 agent: $R"

R=$(curl -s "$BASE/agents/$AID/sub-agents" -H "Authorization: Bearer $ATOKEN")
NSUB=$(echo "$R" | jget "len(d.get('sub_agents',[]))")
[ "$NSUB" -ge 1 ] && ok "B13 子 agent 列表" || bad "B13 子 agent 列表: $R"

R=$(curl -s -X POST "$BASE/orchestration/test" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d "{\"message\":\"帮我研究量子计算\",\"agent_id\":$AID}")
DEC=$(echo "$R" | jget "d.get('decision',{}).get('worker','')")
[ -n "$DEC" ] && ok "B14 编排测试（worker=$DEC）" || warn "B14 编排测试未选择 worker: $R"

# --- 知识库 ---
R=$(curl -s -X POST "$BASE/knowledge/collections" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_知识库","description":"全功能测试知识库"}')
KBID=$(echo "$R" | jget "d.get('collection',{}).get('id')")
[ -n "$KBID" ] && ok "B15 创建知识库" || bad "B15 创建知识库: $R"

echo "EAP 平台于 2024 年在北京成立，产品代号 EAP-2024，创始人叫张三，核心技术是 LangGraph 编排。" > /tmp/ft_kb.txt
R=$(curl -s -X POST "$BASE/knowledge/collections/$KBID/documents/upload" -H "Authorization: Bearer $ATOKEN" -F "file=@/tmp/ft_kb.txt")
DOCID=$(echo "$R" | jget "d.get('document',{}).get('id')")
[ -n "$DOCID" ] && ok "B16 上传知识文档" || bad "B16 上传文档: $R"

R=$(curl -s -X POST "$BASE/knowledge/search" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d "{\"query\":\"EAP 平台在哪里成立\",\"collection_id\":$KBID,\"top_k\":3}")
NRES=$(echo "$R" | jget "len(d.get('results',[]))")
[ "$NRES" -ge 1 ] && ok "B17 知识库检索（$NRES 条）" || bad "B17 知识库检索无结果: $R"

# agent 绑定知识库
R=$(curl -s -X PUT "$BASE/agents/$AID" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d "{\"knowledge_collections\":[$KBID]}")
KB=$(echo "$R" | jget "d.get('agent',{}).get('knowledge_collections')")
[ -n "$KB" ] && ok "B18 agent 绑定知识库" || bad "B18 agent 绑定知识库: $R"

# --- MCP ---
R=$(curl -s -X POST "$BASE/mcp/servers" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_mcp_test","description":"测试 MCP","transport":"sse","sse_url":"http://127.0.0.1:9999/sse"}')
MCPID=$(echo "$R" | jget "d.get('server',{}).get('id')")
[ -n "$MCPID" ] && ok "B19 创建 MCP server" || bad "B19 创建 MCP: $R"

S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/mcp/servers" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{"name":"bad","transport":"http"}')
[ "$S" = "422" ] && ok "B20 非法 transport → 422" || bad "B20 非法 transport 应 422, 实际 $S"

# --- Admin ---
S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/users" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B21 用户列表" || bad "B21 用户列表应 200, 实际 $S"
S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/roles" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B22 角色列表" || bad "B22 角色列表应 200, 实际 $S"
S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/models" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B23 模型供应商列表" || bad "B23 模型列表应 200, 实际 $S"
S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/models/available" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B24 可用模型列表" || bad "B24 可用模型应 200, 实际 $S"
# B29: 编辑模型时脱敏 Key 不得覆盖真实 Key（前端回传脱敏值的历史 bug 防护）
R=$(curl -s -X POST "$BASE/admin/models" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_model","provider":"deepseek","api_key":"sk-ftreal1234567890","model_name":"ft-model"}')
MID=$(echo "$R" | jget "d.get('model',{}).get('id')")
curl -s -X PUT "$BASE/admin/models/$MID" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_model_renamed","api_key":"sk-XXXX****YYYY"}' > /dev/null
GETKEY=$(curl -s "$BASE/admin/models" -H "Authorization: Bearer $ATOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for m in d['models']:
    if m['id'] == $MID: print(m['api_key'])")
if [ "$GETKEY" = "sk-ftr****7890" ]; then ok "B29 脱敏 Key 不覆盖真实 Key"; else bad "B29 Key 被覆盖: $GETKEY"; fi
curl -s -X DELETE "$BASE/admin/models/$MID" -H "Authorization: Bearer $ATOKEN" > /dev/null

# B33: 执行后端字段（backend=container 预留接口存取 + 非法值拒绝）
R=$(curl -s -X POST "$BASE/agents" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_backend预留","backend":"container","tools_config":["calculator"]}')
BKID=$(echo "$R" | jget "d.get('agent',{}).get('id')")
BKVAL=$(echo "$R" | jget "d.get('agent',{}).get('backend')")
if [ -n "$BKID" ] && [ "$BKVAL" = "container" ]; then ok "B33 backend 字段存取（container 预留）"; else bad "B33 backend 字段: $R"; fi
curl -s -X DELETE "$BASE/agents/$BKID" -H "Authorization: Bearer $ATOKEN" > /dev/null
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/agents" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_backend非法","backend":"k8s"}')
[ "$S" = "422" ] && ok "B33b 非法 backend 拒绝" || bad "B33b 非法 backend 应 422, 实际 $S"

# B32: 智能体绑定模型后端（model_provider_id 存取）
DEFAULT_MP=$(curl -s "$BASE/models/available" -H "Authorization: Bearer $ATOKEN" | jget "d.get('models',[{}])[0].get('id')")
R=$(curl -s -X POST "$BASE/agents" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d "{\"name\":\"ft_backend绑定\",\"model_provider_id\":$DEFAULT_MP,\"tools_config\":[\"calculator\"]}")
BIND_ID=$(echo "$R" | jget "d.get('agent',{}).get('id')")
BOUND_MP=$(echo "$R" | jget "d.get('agent',{}).get('model_provider_id')")
if [ -n "$BIND_ID" ] && [ "$BOUND_MP" = "$DEFAULT_MP" ]; then ok "B32 智能体绑定模型后端"; else bad "B32 绑定后端: $R"; fi
curl -s -X DELETE "$BASE/agents/$BIND_ID" -H "Authorization: Bearer $ATOKEN" > /dev/null

# B31: LM Studio 通道 CRUD
R=$(curl -s -X POST "$BASE/admin/models" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_lmstudio","provider":"lmstudio","api_key":"lm-studio","model_name":"ft-local-model","api_base":"http://127.0.0.1:1234/v1"}')
LMSID=$(echo "$R" | jget "d.get('model',{}).get('id')")
AVAIL=$(curl -s "$BASE/models/available" -H "Authorization: Bearer $ATOKEN" | grep -c "ft_lmstudio")
if [ -n "$LMSID" ] && [ "$AVAIL" -ge 1 ]; then ok "B31 LM Studio 通道创建并出现在可用列表"; else bad "B31 LM Studio 通道: $R"; fi
curl -s -X DELETE "$BASE/admin/models/$LMSID" -H "Authorization: Bearer $ATOKEN" > /dev/null

# B30: 创建模型时拒绝脱敏 Key
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/admin/models" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"name":"ft_model2","provider":"deepseek","api_key":"sk-xxxx****abcd","model_name":"ft-model2"}')
[ "$S" = "422" ] && ok "B30 创建拒绝脱敏 Key" || bad "B30 创建脱敏 Key 应 422, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/audit-logs" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B25 审计日志" || bad "B25 审计日志应 200, 实际 $S"

R=$(curl -s -X POST "$BASE/admin/users" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" \
  -d '{"username":"ftuser","email":"ftuser@test.com","password":"ft123456","role_names":["Viewer"]}')
FTUID=$(echo "$R" | jget "d.get('user',{}).get('id')")
[ -n "$FTUID" ] && ok "B26 创建用户" || bad "B26 创建用户: $R"

S=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/admin/users/$FTUID" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B27 删除用户" || bad "B27 删除用户应 200, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/workflow/approvals" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "B28 审批列表" || bad "B28 审批列表应 200, 实际 $S"

echo ""
echo "【Phase B 完成】agent=$AID skills=($SK1,$SK2,$SK3,$SK4) sub=$SUBID kb=$KBID mcp=$MCPID"
echo "AGENT_ID=$AID" > $OUT/ids.env
echo "AGENT_ID2=$AID2" >> $OUT/ids.env
echo "SK1=$SK1; SK2=$SK2; SK3=$SK3; SK4=$SK4" >> $OUT/ids.env
echo "KBID=$KBID; DOCID=$DOCID; SUBID=$SUBID; MCPID=$MCPID; FTUID=$FTUID" >> $OUT/ids.env

# ================= Phase C: Agent 功能 =================
echo ""
echo "【Phase C】Agent 功能测试（SSE 聊天）"

# C1 计算器
F=$(chat $AID "请使用 calculator 工具计算 123*456" "" c1_calc)
if sse_ok "$F" && sse_tools "$F" | grep -q "calculator"; then ok "C1 计算器工具调用"; else bad "C1 计算器: $(sse_tools "$F" | tr '\n' ' ') $(sse_error "$F")"; fi

# C2 时间
F=$(chat $AID "请使用 datetime 工具告诉我今天的日期和星期" "" c2_dt)
if sse_ok "$F"; then
  if sse_tools "$F" | grep -q "datetime" || sse_reply "$F" | grep -q "星期"; then ok "C2 日期工具调用"; else warn "C2 日期（未调 datetime，回复: $(sse_reply "$F")）"; fi
else bad "C2 日期: $(sse_error "$F")"; fi

# C3 记忆保存
F=$(chat $AID "请保存记忆：我叫全功能测试员，最喜欢的编程语言是 Rust，使用的操作系统是 macOS" "" c3_mem)
if sse_ok "$F" && sse_tools "$F" | grep -q "memory_save"; then ok "C3 记忆保存"; else bad "C3 记忆保存: $(sse_tools "$F" | tr '\n' ' ') $(sse_error "$F")"; fi

# C4 跨线程记忆
F=$(chat $AID "我叫什么名字？请先搜索记忆再回答" "" c4_mem2)
if sse_ok "$F"; then
  if sse_tools "$F" | grep -q "memory_search" || sse_reply "$F" | grep -q "全功能测试员"; then
    ok "C4 跨线程记忆读取"
  else warn "C4 记忆读取（done 但未见记忆内容: $(sse_reply "$F")）"; fi
else bad "C4 记忆读取: $(sse_error "$F")"; fi

# C5 agent-mode skill（英文名）
F=$(chat $AID "请使用 ft_translator 技能把'你好，世界'翻译成英文" "" c5_skill)
if sse_ok "$F" && sse_tools "$F" | grep -q "skill_ft_translator"; then ok "C5 agent-mode skill 工具"; else bad "C5 skill 工具: $(sse_tools "$F" | tr '\n' ' ') $(sse_error "$F")"; fi

# C6 子 agent
F=$(chat $AID "请调用 ft_researcher 子agent：整理量子计算的三条基础知识" "" c6_sub)
if sse_ok "$F" && sse_tools "$F" | grep -q "sub_agent_ft_researcher"; then ok "C6 子 agent 工具"; else bad "C6 子 agent: $(sse_tools "$F" | tr '\n' ' ') $(sse_error "$F")"; fi

# C7 知识库 RAG
F=$(chat $AID "请使用知识库搜索：EAP 平台在哪里成立的？创始人是谁？" "" c7_kb)
if sse_ok "$F"; then
  if sse_tools "$F" | grep -q "knowledge_search" || sse_reply "$F" | grep -q "北京"; then
    ok "C7 知识库 RAG"
  else warn "C7 知识库（done 但未见检索/答案: $(sse_reply "$F")）"; fi
else bad "C7 知识库: $(sse_error "$F")"; fi

# C8 多轮对话（用 C1 的 thread）
TID_C1=$(sse_thread $OUT/sse_c1_calc.txt)
F=$(chat $AID "我刚才让你计算什么？结果是多少？" "$TID_C1" c8_multi)
if sse_ok "$F" && sse_reply "$F" | grep -qE "123|56088"; then ok "C8 多轮对话上下文"; else warn "C8 多轮（$(sse_reply "$F")）"; fi

# C9 web 搜索（可能受网络影响，WARN 级）
F=$(chat $AID "请使用 web_search 搜索今天的科技新闻并总结两条" "" c9_web)
if sse_ok "$F"; then
  if sse_tools "$F" | grep -q "web_search"; then ok "C9 web 搜索"; else warn "C9 web 搜索（done 但未调用工具）"; fi
else warn "C9 web 搜索失败: $(sse_error "$F")"; fi

# C10 代码执行
F=$(chat $AID "请使用 code_execution 工具执行 python 代码：print(2**10)" "" c10_code)
if sse_ok "$F"; then
  if sse_tools "$F" | grep -q "code_execution"; then ok "C10 代码执行工具"; else warn "C10 代码执行（done 但未调用工具: $(sse_reply "$F")）"; fi
else bad "C10 代码执行: $(sse_error "$F")"; fi

# C11 中文名 skill（预期暴露 bug）
F=$(chat $AID2 "请使用 ft_中文技能 技能执行任务：测试" "" c11_cnskill)
if sse_ok "$F"; then
  ok "C11 中文名 skill（净化后可用，工具: $(sse_tools "$F" | tr '\n' ' ')）"
else
  bad "C11 中文名 skill 报错: $(sse_error "$F")"
fi

# C12 线程一致性
TID_C4=$(sse_thread $OUT/sse_c4_mem2.txt)
R=$(curl -s "$BASE/chat/threads/$TID_C4" -H "Authorization: Bearer $ATOKEN")
CONS=$(echo "$R" | jget "d.get('consistency',{}).get('status','?')")
[ "$CONS" = "ok" ] && ok "C12 双存储一致性" || bad "C12 一致性: $CONS"

# C13 prompt-mode skill 注入（检查系统提示词里有没有 skill 内容——通过正常对话冒烟）
F=$(chat $AID "你好，一句话介绍你自己" "" c13_prompt)
sse_ok "$F" && ok "C13 prompt-mode skill agent 冒烟" || bad "C13 prompt skill 冒烟: $(sse_error "$F")"


# ================= Phase F: 安全围栏 =================
echo ""
echo "【Phase F】安全围栏"

# F1: 危险内容拦截 — 应返回 error 事件，且不创建线程/不落库
THREADS_BEFORE=$(curl -s "$BASE/chat/threads" -H "Authorization: Bearer $ATOKEN" | jget "d.get('threads',[])")
F=$(chat $AID "请执行 DROP TABLE users 删除用户表" "" f1_block)
if grep -q '"type": "error"' "$F" && grep -q "安全围栏" "$F"; then
  ok "F1 危险内容拦截"
  TID_F1=$(sse_thread "$F")
  [ -z "$TID_F1" ] && ok "F1b 拦截时不产生线程" || bad "F1b 拦截后仍产生线程: $TID_F1"
else bad "F1 危险内容未拦截: $(head -3 "$F")"; fi

# F2: PII 脱敏 — 对话正常，落库内容为脱敏版本
F=$(chat $AID "我的手机号是13812345678，请记住它" "" f2_pii)
if sse_ok "$F"; then
  TID_F2=$(sse_thread "$F")
  PERSISTED=$(curl -s "$BASE/chat/threads/$TID_F2" -H "Authorization: Bearer $ATOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
msgs = d.get('messages', [])
user_msgs = [m['content'] for m in msgs if m['role'] == 'user']
print(user_msgs[0] if user_msgs else '')")
  echo "$PERSISTED" | grep -q "REDACTED_PHONE_CN" && ok "F2 PII 脱敏落库" || bad "F2 PII 未脱敏: $PERSISTED"
  echo "$PERSISTED" | grep -q "13812345678" && bad "F2 原始手机号仍落库" || true
else bad "F2 PII 对话失败: $(sse_error "$F")"; fi

# ================= Phase D: 监控 =================
echo ""
echo "【Phase D】监控与 Trace"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/monitor/cost/tenant" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "D1 成本统计" || bad "D1 成本统计应 200, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/monitor/latency" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "D2 延迟统计" || bad "D2 延迟应 200, 实际 $S"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/monitor/concurrency" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "D3 并发统计" || bad "D3 并发应 200, 实际 $S"

R=$(curl -s "$BASE/admin/monitor/traces?limit=10" -H "Authorization: Bearer $ATOKEN")
NTR=$(echo "$R" | jget "len(d.get('traces',[]))")
[ "$NTR" -ge 1 ] && ok "D4 Trace 列表（$NTR 条）" || bad "D4 Trace 列表为空: $R"

TRACE_ID=$(echo "$R" | jget "d.get('traces',[{}])[0].get('trace_id','')")
R2=$(curl -s "$BASE/admin/monitor/traces/$TRACE_ID" -H "Authorization: Bearer $ATOKEN")
TOT=$(echo "$R2" | jget "d.get('summary',{}).get('total_tokens',0)")
LLMC=$(echo "$R2" | jget "d.get('summary',{}).get('llm_calls',0)")
TOOLC=$(echo "$R2" | jget "d.get('summary',{}).get('tool_calls',0)")
[ "$LLMC" -ge 1 ] && ok "D5 Trace 含 LLM 事件（$LLMC 次）" || bad "D5 Trace 无 LLM 事件"
if [ "$TOOLC" -ge 1 ]; then ok "D6 Trace 含工具事件（$TOOLC 次）"; else warn "D6 最近 trace 无工具事件（可能选了无工具的对话）"; fi
if [ "$TOT" -gt 0 ]; then ok "D7 Token 统计正常（$TOT tokens）"; else bad "D7 Token 统计为 0"; fi

# ================= Phase H: HITL 审批流转（interrupt → 审批 → resume） =================
echo ""
echo "【Phase H】HITL 审批流转（write_file 中断 → 审批 → resume）"

# 专用 HITL agent（local 后端即有 write_file/edit_file；permission_mode=default → 中断）
R=$(curl -s -X POST "$BASE/agents" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{
  "name":"ft_hitl","description":"HITL 回归测试 agent",
  "model":"deepseek-v4-pro",
  "system_prompt":"你是文件操作助手：按用户要求用 write_file 写入指定文件，写完后用一句话确认文件名。",
  "tools_config":["calculator"],
  "permission_mode":"default"}')
HITL_AID=$(echo "$R" | jget "d.get('agent',{}).get('id')")
[ -n "$HITL_AID" ] && ok "H0 创建 HITL agent" || bad "H0 创建 HITL agent: $R"

# H1: 触发中断 —— 应发射 interrupt 事件（approval_id/tool_name/args），
# 无 tool_end；done 带 interrupted 标志（review Important 2）
F=$(chat $HITL_AID "请把文件 hitl_approve.txt 的内容写为 hello hitl approve 1024，写完后确认" "" h1_intr)
if grep -q '"type": "interrupt"' "$F"; then
  H1_AID=$(sse_interrupt "$F" | jget "d['approval_id']")
  H1_TOOL=$(sse_interrupt "$F" | jget "d['tool_name']")
  [ "$H1_TOOL" = "write_file" ] && ok "H1 write_file 触发中断（approval_id=$H1_AID）" || bad "H1 中断工具名异常: $H1_TOOL"
else
  bad "H1 未收到 interrupt 事件: $(sse_error "$F")"
fi
# H1b: 中断轮发 done 且带 interrupted 标志（review Important 2：usage 供
# 成本入账；事件类型仍为 done，前端兼容）；不允许出现无标志 done
grep -q '"type": "done", "interrupted": true' "$F" && ok "H1b 中断轮 done 带 interrupted 标志" || bad "H1b 中断轮 done 缺 interrupted 标志: $(grep -oE '"type": "done".*' "$F" | head -1)"
grep -q '"type": "tool_end", "tool": "write_file"' "$F" && bad "H1c 中断时工具未执行" || ok "H1c 中断时工具未执行（无 tool_end）"
TID_H1=$(sse_thread "$F")
FULL_TID_H1=$(sse_full_thread "$F")

# H2: 审批列表出现 pending 记录（与 interrupt 事件的 approval_id 一致）
R=$(curl -s "$BASE/workflow/approvals?status=pending" -H "Authorization: Bearer $ATOKEN")
HPEND=$(echo "$R" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for a in d.get('approvals', []):
    if a['thread_id'] == '$FULL_TID_H1' and a['tool_name'] == 'write_file':
        print(a['id']); break")
if [ -n "$HPEND" ] && [ "$HPEND" = "$H1_AID" ]; then
  ok "H2 审批列表出现 pending 记录（id=$HPEND 与中断事件一致）"
else
  bad "H2 pending 审批缺失或不一致: $R"
fi

# H3: approve
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/workflow/approvals/$HPEND/approve" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "H3 approve 审批（200）" || bad "H3 approve 应 200, 实际 $S"

# H4: resume → 工具执行 + done
F=$(resume $HITL_AID "$TID_H1" h4_resume)
if grep -q '"type": "tool_end", "tool": "write_file"' "$F" && sse_ok "$F"; then
  ok "H4 resume 后 write_file 执行并 done"
else
  bad "H4 resume 未执行工具: $(sse_tools "$F" | tr '\n' ' ') $(sse_error "$F")"
fi

# H4b: approve 路径文件内容验证（同一线程追问 read_file 读回）
F=$(chat $HITL_AID "请用 read_file 读取 hitl_approve.txt 并原样回复其中的内容" "$TID_H1" h4_verify)
if sse_ok "$F" && sse_reply "$F" | grep -q "1024"; then
  ok "H4b approve 路径文件内容已写入（读回含 1024）"
else
  bad "H4b 文件内容读回不符: $(sse_reply "$F")"
fi

# H5: reject 路径 —— 中断 → reject → resume：工具跳过，注入拒绝说明
F=$(chat $HITL_AID "请把文件 hitl_reject.txt 的内容写为 top secret，写完后确认" "" h5_intr)
if grep -q '"type": "interrupt"' "$F"; then
  RID=$(sse_interrupt "$F" | jget "d['approval_id']")
  ok "H5 前置中断（approval_id=$RID）"
else
  bad "H5 未收到中断: $(sse_error "$F")"
fi
TID_H5=$(sse_thread "$F")
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/workflow/approvals/$RID/reject" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{"reason":"回归测试拒绝"}')
[ "$S" = "200" ] && ok "H5b reject 审批（200）" || bad "H5b reject 应 200, 实际 $S"
F=$(resume $HITL_AID "$TID_H5" h5_resume)
# reject 时中间件注入 ToolMessage(status=error, "User rejected the tool call ... was not executed")，
# 工具不执行 → tool_end 的 output 必含 rejected 标记
if sse_ok "$F" && grep -q '"type": "tool_end", "tool": "write_file"' "$F" && grep -qi "rejected" "$F"; then
  ok "H5c reject 后工具跳过（注入拒绝说明，无实际执行）"
else
  bad "H5c reject 路径异常: $(grep -oE '"type": "tool_end".*' "$F" | head -1) $(sse_error "$F")"
fi

# H6: edit 路径 —— 中断 → edit_and_approve（改 content）→ resume：按编辑后的参数执行
F=$(chat $HITL_AID "请把文件 hitl_edit.txt 的内容写为 original content" "" h6_intr)
if grep -q '"type": "interrupt"' "$F"; then
  EID=$(sse_interrupt "$F" | jget "d['approval_id']")
  ok "H6 前置中断（approval_id=$EID）"
else
  bad "H6 未收到中断: $(sse_error "$F")"
fi
TID_H6=$(sse_thread "$F")
# 从 interrupt 事件的原始 args 上改 content，保证工具参数完整
EEDITED=$(sse_interrupt "$F" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
a = dict(d['args']); a['content'] = 'edited-by-test'
print(json.dumps(a, ensure_ascii=False))")
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/workflow/approvals/$EID/edit" -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d "{\"edited_args\":$EEDITED}")
[ "$S" = "200" ] && ok "H6b edit_and_approve（200）" || bad "H6b edit 应 200, 实际 $S"
F=$(resume $HITL_AID "$TID_H6" h6_resume)
# 编辑后的参数必须生效：tool_start 的 input 含 edited-by-test，且工具已执行
if grep -q '"input": ".*edited-by-test' "$F" && grep -q '"type": "tool_end", "tool": "write_file"' "$F"; then
  ok "H6c 编辑后的参数生效并执行（input 含 edited-by-test）"
else
  bad "H6c 编辑参数未生效: $(grep -oE '"type": "tool_start".*' "$F" | head -1) $(sse_error "$F")"
fi
# 中间件不回显编辑后的内容 → 模型可能再次发起写入 → 链式中断（每笔写入都需审批）：
# 新审批 → approve → resume → done
if grep -q '"type": "interrupt"' "$F"; then
  EID2=$(sse_interrupt "$F" | jget "d['approval_id']")
  if [ -n "$EID2" ] && [ "$EID2" != "$EID" ]; then
    ok "H6c2 链式中断产生新审批（id=$EID2，与编辑审批 $EID 不同）"
  else
    bad "H6c2 链式中断审批异常: $F"
  fi
  S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/workflow/approvals/$EID2/approve" -H "Authorization: Bearer $ATOKEN")
  [ "$S" = "200" ] && ok "H6c3 链式审批 approve（200）" || bad "H6c3 链式 approve 应 200, 实际 $S"
  F=$(resume $HITL_AID "$TID_H6" h6_resume2)
  sse_ok "$F" && ok "H6c4 链式 resume 完成（done）" || bad "H6c4 链式 resume: $(sse_error "$F")"
else
  sse_ok "$F" && ok "H6c2 恢复流一次完成（无链式中断）" || bad "H6c2 恢复流未 done: $(sse_error "$F")"
fi

# H6d: 文件内容读回（无链式时 = edited-by-test；链式复写后 = original content，均为编辑流合法终点）
F=$(chat $HITL_AID "请用 read_file 读取 hitl_edit.txt 并原样回复其中的内容" "$TID_H6" h6_verify)
if sse_ok "$F" && (sse_reply "$F" | grep -q "edited-by-test" || sse_reply "$F" | grep -q "original content"); then
  ok "H6d 文件内容读回一致（$(sse_reply "$F" | grep -oE 'edited-by-test|original content' | head -1)）"
else
  bad "H6d 读回内容不符: $(sse_reply "$F")"
fi

# 触发 HITL 中断：模型有时先探索目录而不调用 write_file（非确定性），
# 最多重试 3 次，后续尝试明确要求直接调用 write_file（同线程续聊）
interrupt_retry() {
    local out="$1" tid="${2:-}" base_msg="$3"
    local f="" t=""
    for i in 1 2 3; do
        if [ "$i" = "1" ]; then
            f=$(chat $HITL_AID "$base_msg" "$tid" "${out}_$i")
        else
            t=$(sse_thread "$f")
            f=$(chat $HITL_AID "不要查找/探索目录，请直接调用 write_file 工具执行：$base_msg" "$t" "${out}_$i")
        fi
        grep -q '"type": "interrupt"' "$f" && { echo "$f"; return 0; }
    done
    echo "$f"
    return 1
}

# H7: review Important-1 回归 —— 审批后放弃 → 新消息 → 再次中断 → 审批 → resume
# 决定不串：批次1 已 approve 但放弃（不 resume，改发新消息）→ 批次2 新中断 →
# approve 批次2 → resume 必须成功，且执行的是批次2 的写入（旧决议不得混入）
F=$(interrupt_retry "h7_intr" "" "请把文件 hitl_abandon.txt 的内容写为 batch-one（该文件还不存在，请直接写），写完后确认")
if grep -q '"type": "interrupt"' "$F" 2>/dev/null; then
  B1ID=$(sse_interrupt "$F" | jget "d['approval_id']")
  ok "H7a 批次1 中断（approval_id=$B1ID）"
else
  bad "H7a 批次1 未中断（3 次尝试模型仍未调用 write_file）: $(sse_error "$F")"
fi
TID_H7=$(sse_thread "$F")
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/workflow/approvals/$B1ID/approve" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "H7b 批次1 approve（200，随后放弃不 resume）" || bad "H7b 批次1 approve 应 200, 实际 $S"
# 放弃批次1：同线程发新消息（非 resume）→ checkpoint 清理 + 旧决议标记 orphaned
F=$(interrupt_retry "h7_intr2" "$TID_H7" "请把文件 hitl_abandon.txt 的内容写为 batch-two（该文件还不存在，请直接写），写完后确认")
if grep -q '"type": "interrupt"' "$F" 2>/dev/null; then
  B2ID=$(sse_interrupt "$F" | jget "d['approval_id']")
  if [ -n "$B2ID" ] && [ "$B2ID" != "$B1ID" ]; then
    ok "H7c 批次2 中断产生新审批（id=$B2ID，与批次1 $B1ID 不同）"
  else
    bad "H7c 批次2 审批异常（未产生新审批）: $F"
  fi
else
  bad "H7c 批次2 未中断（3 次尝试模型仍未调用 write_file）: $(sse_error "$F")"
fi
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/workflow/approvals/$B2ID/approve" -H "Authorization: Bearer $ATOKEN")
[ "$S" = "200" ] && ok "H7d 批次2 approve（200）" || bad "H7d 批次2 approve 应 200, 实际 $S"
F=$(resume $HITL_AID "$TID_H7" h7_resume)
# 回归核心：resume 成功（旧批次决定不得混入/不得报"决议数不足"卡死）
if grep -q '"type": "tool_end", "tool": "write_file"' "$F" && sse_ok "$F"; then
  ok "H7e resume 成功，批次1 决议未混入（write_file 执行 + done）"
else
  bad "H7e resume 失败/决定串批: $(sse_tools "$F" | tr '\n' ' ') $(sse_error "$F")"
fi
F=$(chat $HITL_AID "请用 read_file 读取 hitl_abandon.txt 并原样回复其中的内容" "$TID_H7" h7_verify)
if sse_ok "$F" && sse_reply "$F" | grep -q "batch-two"; then
  ok "H7f 文件内容为批次2 的 batch-two（决定不串）"
else
  bad "H7f 文件内容不符（批次串味）: $(sse_reply "$F")"
fi

# ================= Phase E: 线程列表 + 清理 =================
echo ""
echo "【Phase E】线程与清理"

R=$(curl -s "$BASE/chat/threads" -H "Authorization: Bearer $ATOKEN")
NT=$(echo "$R" | jget "len(d.get('threads',[]))")
[ "$NT" -ge 3 ] && ok "E1 线程列表（$NT 个）" || warn "E1 线程列表仅 $NT 个"

# 清理测试数据
echo "--- 清理测试数据 ---"
curl -s -X DELETE "$BASE/skills/$SK4" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除 ZIP skill $SK4"
curl -s -X DELETE "$BASE/skills/$SK3" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除中文 skill $SK3"
curl -s -X DELETE "$BASE/skills/$SK2" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除 translator skill $SK2"
curl -s -X DELETE "$BASE/skills/$SK1" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除 code_style skill $SK1"
curl -s -X DELETE "$BASE/agents/$AID2" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除中文技能 agent $AID2"
curl -s -X DELETE "$BASE/agents/$AID" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除测试 agent $AID"
[ -n "$HITL_AID" ] && curl -s -X DELETE "$BASE/agents/$HITL_AID" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除 HITL agent $HITL_AID"
curl -s -X DELETE "$BASE/knowledge/documents/$DOCID" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除文档 $DOCID"
curl -s -X DELETE "$BASE/knowledge/collections/$KBID" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除知识库 $KBID"
curl -s -X DELETE "$BASE/mcp/servers/$MCPID" -H "Authorization: Bearer $ATOKEN" > /dev/null && echo "  已删除 MCP $MCPID"

# 清理历史线程（仅测试产生的）——保留，不删用户数据

# ================= 汇总 =================
echo ""
echo "=========================================="
echo "测试汇总: 通过 $PASS / 失败 $FAIL / 警告 $WARN"
if [ $FAIL -gt 0 ]; then
  echo "失败项:"
  for f in "${FAILED[@]}"; do echo "  ❌ $f"; done
fi
echo "=========================================="
exit $FAIL
