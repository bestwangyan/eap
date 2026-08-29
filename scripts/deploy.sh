#!/bin/bash
# ============================================================
# EAP 部署脚本 - 部署到 192.168.1.51
# 用法: DEEPSEEK_API_KEY=sk-xxx ./scripts/deploy.sh
# ============================================================

set -e

SERVER="wangyan@192.168.1.51"
SSH_PASS="${SSH_PASSWORD:?请先设置 SSH_PASSWORD 环境变量}"
SSH="sshpass -p '${SSH_PASS}' ssh -o StrictHostKeyChecking=no ${SERVER}"
PROJECT_DIR="/home/wangyan/eap"

echo "========================================"
echo " EAP 企业 Agent 平台 - 部署脚本"
echo "========================================"

# 检查 DeepSeek Key
if [ -z "${DEEPSEEK_API_KEY}" ]; then
    echo "错误: 请设置 DEEPSEEK_API_KEY 环境变量"
    echo "用法: DEEPSEEK_API_KEY=sk-xxx ./scripts/deploy.sh"
    exit 1
fi

echo ""
echo ">>> [1/5] 同步代码到服务器..."
rsync -avz --delete \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.venv' --exclude='venv' --exclude='node_modules' \
    --exclude='frontend/dist' --exclude='.DS_Store' \
    ../backend/ ${SERVER}:${PROJECT_DIR}/backend/
rsync -avz --delete \
    --exclude='.git' --exclude='node_modules' --exclude='dist' \
    ../frontend/ ${SERVER}:${PROJECT_DIR}/frontend/
rsync -avz ../docker-compose.prod.yml ${SERVER}:${PROJECT_DIR}/

echo ""
echo ">>> [2/5] 构建 Docker 镜像..."
${SSH} "cd ${PROJECT_DIR} && \
    DEEPSEEK_API_KEY='${DEEPSEEK_API_KEY}' \
    SECRET_KEY='${SECRET_KEY:-eap-prod-$(date +%s)}' \
    docker compose -f docker-compose.prod.yml build --no-cache"

echo ""
echo ">>> [3/5] 停止旧容器..."
${SSH} "cd ${PROJECT_DIR} && docker compose -f docker-compose.prod.yml down || true"

echo ""
echo ">>> [4/5] 启动服务..."
${SSH} "cd ${PROJECT_DIR} && \
    DEEPSEEK_API_KEY='${DEEPSEEK_API_KEY}' \
    SECRET_KEY='${SECRET_KEY:-eap-prod-$(date +%s)}' \
    docker compose -f docker-compose.prod.yml up -d"

echo ""
echo ">>> [5/5] 验证部署..."
sleep 5
${SSH} "echo '--- 容器状态 ---' && docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' && \
    echo '' && echo '--- 后端健康检查 ---' && curl -s http://127.0.0.1:5000/health && echo '' && \
    echo '--- 前端 ---' && curl -s -o /dev/null -w 'HTTP %{http_code}' http://127.0.0.1:3000 && echo ''"

echo ""
echo "========================================"
echo " 部署完成!"
echo " 前端: http://192.168.1.51:3000"
echo " 后端: http://192.168.1.51:5000"
echo " 默认账号: admin@example.com（密码见 EAP_SEED_ADMIN_PW）"
echo "========================================"
