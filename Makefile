.PHONY: up down logs build clean dev-backend dev-frontend deploy deploy-nginx deploy-restart

SERVER = wangyan@192.168.1.51
DEPLOY_PATH = /home/wangyan/deploy/eap
# ===== 部署凭据 =====
# 密码禁止提交到仓库：在本地 .make.env 文件写 SSH_PASSWORD=xxx（该文件已 gitignore）
-include .make.env
SSHPASS = sshpass -p '$(SSH_PASSWORD)' ssh -o StrictHostKeyChecking=no
SCP = sshpass -p '$(SSH_PASSWORD)' scp -o StrictHostKeyChecking=no
# sudo 凭证缓存过期时非交互 SSH 无法弹密码, 统一用 -S 从管道读密码
SUDO = echo $(SSH_PASSWORD) | sudo -S

# 本地 Docker 开发
up:
	docker-compose up -d
down:
	docker-compose down
logs:
	docker-compose logs -f
build:
	docker-compose build --no-cache
clean:
	docker-compose down -v

# 本地开发
dev-backend:
	cd backend && FLASK_ENV=development FLASK_DEBUG=1 python wsgi.py

dev-frontend:
	cd frontend && npm install && npm run dev

# 安装依赖
install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

# ===== 部署到服务器 =====

# 完整部署: 构建前端 + 同步代码 + 重启
deploy:
	cd frontend && npm run build
	cd ..
	rsync -avz --delete -e "$(SSHPASS)" \
		--exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
		--exclude='tests' --exclude='migrations' --exclude='.venv' --exclude='.env' \
		./backend/ $(SERVER):$(DEPLOY_PATH)/backend/
	rsync -avz --delete -e "$(SSHPASS)" \
		./frontend/dist/ $(SERVER):$(DEPLOY_PATH)/frontend/dist/
	$(SSHPASS) $(SERVER) 'cd $(DEPLOY_PATH)/backend && .venv/bin/pip install -q -r requirements.txt'
	$(SSHPASS) $(SERVER) '$(SUDO) systemctl restart eap-backend'
	@echo "部署完成, 等待 5 秒验证..."
	sleep 5
	$(SSHPASS) $(SERVER) 'curl -s http://127.0.0.1:5003/health'

# 仅部署后端
deploy-backend:
	rsync -avz --delete -e "$(SSHPASS)" \
		--exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
		--exclude='tests' --exclude='migrations' --exclude='.venv' --exclude='.env' \
		./backend/ $(SERVER):$(DEPLOY_PATH)/backend/
	$(SSHPASS) $(SERVER) '$(SUDO) systemctl restart eap-backend'

# 仅部署前端
deploy-frontend:
	cd frontend && npm run build
	rsync -avz --delete -e "$(SSHPASS)" \
		./frontend/dist/ $(SERVER):$(DEPLOY_PATH)/frontend/dist/

# 部署 Nginx 配置
# 注意: sudo -S 从 stdin 读密码, 不能用 stdin 直接传配置文件, 改为 scp 到 /tmp 再 sudo 复制
deploy-nginx:
	$(SCP) scripts/nginx_eap.conf $(SERVER):/tmp/nginx_eap.conf
	$(SSHPASS) $(SERVER) '$(SUDO) cp /tmp/nginx_eap.conf /etc/nginx/sites-enabled/eap && rm -f /tmp/nginx_eap.conf && $(SUDO) nginx -t && $(SUDO) systemctl reload nginx'

# 仅重启后端
deploy-restart:
	$(SSHPASS) $(SERVER) '$(SUDO) systemctl restart eap-backend'

# 服务器信息
server-info:
	$(SSHPASS) $(SERVER) 'echo "=== 服务状态 ===" && $(SUDO) systemctl status eap-backend 2>&1 | grep -E "Active:|Memory:" && echo "=== 端口 ===" && ss -tlnp 2>/dev/null | grep -E "5003|80|5432|6379" && echo "=== 磁盘 ===" && df -h / | tail -1'
