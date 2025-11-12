# Docker 快速上手指南

> 5 分钟在任意 VPS 上部署 Amazon Q to Claude API Proxy

## 三种部署方式对比

| 方式 | 优点 | 适用场景 |
|------|------|----------|
| **Docker Hub** | 全球访问,一键部署 | 个人项目,公开服务 |
| **镜像文件** | 离线部署,无需仓库 | 内网环境,临时部署 |
| **手动部署** | 灵活配置,完全控制 | 企业环境,定制需求 |

---

## 方式一: Docker Hub 部署 (推荐)

### 步骤 1: 构建并发布镜像

在你的开发机器上:

```bash
# 登录 Docker Hub
docker login

# 使用脚本构建 (推荐)
./build-and-push.sh -u yourusername -v v1.0.0

# 或手动构建
docker build -t yourusername/amq2api:latest .
docker push yourusername/amq2api:latest
```

### 步骤 2: VPS 一键部署

在你的 VPS 上:

```bash
# 下载部署脚本
wget https://raw.githubusercontent.com/your-repo/amq2api/main/quick-deploy.sh
chmod +x quick-deploy.sh

# 设置镜像名并运行
export IMAGE_NAME="yourusername/amq2api:latest"
./quick-deploy.sh
```

脚本会自动完成所有配置! ✨

---

## 方式二: 镜像文件部署 (离线)

### 在开发机器上

```bash
# 1. 构建镜像
docker build -t amq2api:latest .

# 2. 导出镜像
docker save amq2api:latest | gzip > amq2api.tar.gz

# 3. 传输到 VPS
scp amq2api.tar.gz user@your-vps:/tmp/
```

### 在 VPS 上

```bash
# 1. 导入镜像
docker load < /tmp/amq2api.tar.gz

# 2. 创建配置目录
mkdir -p ~/amq2api && cd ~/amq2api

# 3. 创建 .env 配置文件
vim .env  # 填写账号信息

# 4. 启动服务
docker run -d \
  --name amq2api \
  -p 8080:8080 \
  --env-file .env \
  -v amq2api-cache:/home/appuser/.cache/amazonq \
  --restart unless-stopped \
  amq2api:latest

# 5. 验证
curl http://localhost:8080/health
```

---

## 方式三: 手动部署 (完整控制)

```bash
# 1. 创建部署目录
mkdir -p ~/amq2api && cd ~/amq2api

# 2. 创建配置文件
cat > .env << 'EOF'
PORT=8080
AMAZONQ_ACCOUNT_COUNT=3
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=your_token_here
AMAZONQ_ACCOUNT_1_CLIENT_ID=your_client_id_here
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=your_secret_here
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true
# 更多账号配置...
EOF

# 3. 创建 docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  amq2api:
    image: yourusername/amq2api:latest
    container_name: amq2api
    ports:
      - "8080:8080"
    env_file:
      - .env
    volumes:
      - token_cache:/home/appuser/.cache/amazonq
    restart: unless-stopped
volumes:
  token_cache:
EOF

# 4. 启动服务
docker compose up -d

# 5. 查看日志
docker compose logs -f
```

---

## 配置文件示例

### 最小配置 (单账号)

```bash
PORT=8080
AMAZONQ_REFRESH_TOKEN=your_token
AMAZONQ_CLIENT_ID=your_client_id
AMAZONQ_CLIENT_SECRET=your_secret
```

### 完整配置 (多账号)

```bash
# 服务配置
PORT=8080

# 多账号配置
AMAZONQ_ACCOUNT_COUNT=3

# 账号 1 - 主账号
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=token_1
AMAZONQ_ACCOUNT_1_CLIENT_ID=client_id_1
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=secret_1
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true

# 账号 2 - 备用
AMAZONQ_ACCOUNT_2_ID=backup
AMAZONQ_ACCOUNT_2_REFRESH_TOKEN=token_2
AMAZONQ_ACCOUNT_2_CLIENT_ID=client_id_2
AMAZONQ_ACCOUNT_2_CLIENT_SECRET=secret_2
AMAZONQ_ACCOUNT_2_WEIGHT=5
AMAZONQ_ACCOUNT_2_ENABLED=true

# 账号 3 - 应急
AMAZONQ_ACCOUNT_3_ID=fallback
AMAZONQ_ACCOUNT_3_REFRESH_TOKEN=token_3
AMAZONQ_ACCOUNT_3_CLIENT_ID=client_id_3
AMAZONQ_ACCOUNT_3_CLIENT_SECRET=secret_3
AMAZONQ_ACCOUNT_3_WEIGHT=3
AMAZONQ_ACCOUNT_3_ENABLED=true

# 负载均衡
LOAD_BALANCE_STRATEGY=weighted_round_robin

# 熔断器
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_ERROR_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300
```

---

## 常用命令速查

### 服务管理

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f

# 实时日志(过滤)
docker compose logs -f | grep -v assistantResponseEvent
```

### 镜像管理

```bash
# 拉取最新镜像
docker pull yourusername/amq2api:latest

# 更新服务
docker compose pull && docker compose up -d

# 查看本地镜像
docker images | grep amq2api

# 清理未使用镜像
docker image prune -a
```

### 容器管理

```bash
# 进入容器
docker exec -it amq2api bash

# 查看容器资源使用
docker stats amq2api

# 查看容器详情
docker inspect amq2api
```

---

## 验证服务

```bash
# 健康检查
curl http://localhost:8080/health

# 查看账号状态
curl http://localhost:8080/admin/accounts | jq

# 查看指标
curl http://localhost:8080/metrics

# 测试 API
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4.5","messages":[{"role":"user","content":"Hello"}]}'
```

---

## 自动化构建 (GitHub Actions)

### 配置 GitHub Secrets

1. 进入仓库 Settings → Secrets and variables → Actions
2. 添加以下 secrets:
   - `DOCKER_USERNAME`: 你的 Docker Hub 用户名
   - `DOCKER_PASSWORD`: 你的 Docker Hub 密码或 Token

### 触发构建

```bash
# 推送代码自动构建 latest 标签
git push origin main

# 创建版本标签自动构建版本镜像
git tag v1.0.0
git push origin v1.0.0
```

### 查看构建结果

访问 GitHub 仓库的 Actions 标签页查看构建状态

---

## 故障排查

### 问题 1: 服务无法启动

```bash
# 查看详细日志
docker logs amq2api

# 检查配置
cat .env

# 手动测试配置
docker run -it --rm --env-file .env yourusername/amq2api:latest
```

### 问题 2: 端口被占用

```bash
# 查看端口占用
sudo lsof -i :8080

# 修改端口
# 在 .env 中设置: PORT=8081
# 或在 docker run 中: -p 8081:8080
```

### 问题 3: 镜像拉取失败

```bash
# 配置国内镜像加速器
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<-'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn"
  ]
}
EOF
sudo systemctl restart docker
```

### 问题 4: Token 刷新失败

```bash
# 检查账号凭证是否正确
docker exec amq2api cat .env

# 清除 token 缓存重试
docker volume rm amq2api_token_cache
docker compose up -d
```

---

## 性能调优

### 资源限制

```yaml
# docker-compose.yml
services:
  amq2api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M
```

### 日志限制

```yaml
# docker-compose.yml
services:
  amq2api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 完整部署示例

### 场景: 首次部署到生产 VPS

```bash
# 1. 在开发机构建镜像
docker login
./build-and-push.sh -u myusername -v v1.0.0

# 2. SSH 到 VPS
ssh user@your-vps

# 3. 安装 Docker (如果未安装)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
exit  # 重新登录

# 4. 创建部署目录
mkdir -p ~/amq2api && cd ~/amq2api

# 5. 创建配置
vim .env  # 填写账号信息

# 6. 创建 docker-compose.yml
cat > docker-compose.yml << 'YAML'
version: '3.8'
services:
  amq2api:
    image: myusername/amq2api:v1.0.0
    container_name: amq2api
    ports:
      - "8080:8080"
    env_file:
      - .env
    volumes:
      - token_cache:/home/appuser/.cache/amazonq
    restart: unless-stopped
volumes:
  token_cache:
YAML

# 7. 启动服务
docker compose up -d

# 8. 验证
curl http://localhost:8080/health
curl http://localhost:8080/admin/accounts
```

---

## 使用脚本工具

### build-and-push.sh

在开发机器上构建并推送镜像

```bash
# 基本用法
./build-and-push.sh -u yourusername -v v1.0.0

# 参数说明
-u, --username USER    Docker Hub 用户名
-v, --version VER      版本号 (如 v1.0.0)
-t, --tag TAG          标签 (默认: latest)
--no-push              只构建不推送
--no-cache             不使用缓存构建
-h, --help             显示帮助
```

### quick-deploy.sh

在 VPS 上一键部署

```bash
# 设置镜像名
export IMAGE_NAME="yourusername/amq2api:latest"

# 运行部署
./quick-deploy.sh
```

自动完成:
- ✅ Docker 安装检查
- ✅ 配置文件创建
- ✅ 镜像拉取
- ✅ 服务启动
- ✅ 健康检查

---

## 更新部署

```bash
# 方式 1: 使用 compose
docker compose pull
docker compose up -d

# 方式 2: 手动更新
docker pull yourusername/amq2api:latest
docker stop amq2api
docker rm amq2api
docker run -d --name amq2api -p 8080:8080 --env-file .env yourusername/amq2api:latest

# 方式 3: 零停机更新
docker run -d --name amq2api-new -p 8081:8080 --env-file .env yourusername/amq2api:latest
# 验证新容器正常后切换
docker stop amq2api && docker rm amq2api
docker rename amq2api-new amq2api
```

---

## 监控和运维

### Prometheus 指标

```bash
# 查看所有指标
curl http://localhost:8080/metrics

# 查看特定指标
curl http://localhost:8080/metrics | grep request_counter
curl http://localhost:8080/metrics | grep error_counter
curl http://localhost:8080/metrics | grep account_availability
```

### 健康检查

```bash
# 定时健康检查
watch -n 30 'curl -s http://localhost:8080/health | jq'

# 账号状态监控
watch -n 60 'curl -s http://localhost:8080/admin/accounts | jq'
```

---

## 安全建议

1. **不要将 .env 提交到版本控制**
   ```bash
   echo ".env" >> .gitignore
   chmod 600 .env
   ```

2. **使用非 root 用户运行** (已配置)

3. **限制容器端口暴露**
   ```yaml
   ports:
     - "127.0.0.1:8080:8080"  # 仅本地访问
   ```

4. **定期更新镜像**
   ```bash
   docker pull yourusername/amq2api:latest
   docker compose up -d
   ```

---

## 更多文档

- 📖 [完整 Docker 部署文档](DOCKER_DEPLOYMENT.md) - 详细配置和故障排查
- 📖 [镜像构建详细指南](BUILD_AND_PUSH.md) - 镜像仓库和 CI/CD
- 📖 [多账号配置说明](MULTI_ACCOUNT.md) - 负载均衡和熔断器
- 📖 [快速参考手册](QUICK_REFERENCE.md) - 常用命令速查

---

**开始你的 5 分钟部署之旅! 🚀**
