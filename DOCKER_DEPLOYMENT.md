# Docker 部署指南

本指南介绍如何使用 Docker 部署 Amazon Q to Claude API Proxy,支持单账号和多账号模式。

## 目录

- [快速开始](#快速开始)
- [部署方式对比](#部署方式对比)
- [环境准备](#环境准备)
- [单账号模式部署](#单账号模式部署)
- [多账号模式部署](#多账号模式部署)
- [容器管理](#容器管理)
- [持久化存储](#持久化存储)
- [健康检查](#健康检查)
- [日志管理](#日志管理)
- [环境变量](#环境变量)
- [故障排查](#故障排查)

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/amq2api.git
cd amq2api
```

### 2. 配置环境变量

```bash
# 复制示例配置
cp .env.multi_account.example .env

# 编辑配置文件
vim .env
```

### 3. 启动服务

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8080/health

# 查看账号状态(多账号模式)
curl http://localhost:8080/admin/accounts

# 查看指标
curl http://localhost:8080/metrics
```

---

## 部署方式对比

### 方式 1: Docker Compose(推荐)

✅ **优点**:
- 配置简单,一键启动
- 自动管理容器生命周期
- 环境变量管理方便
- 支持容器编排

❌ **缺点**:
- 需要安装 Docker Compose
- 资源使用略高于直接运行

### 方式 2: Docker 命令

✅ **优点**:
- 不需要 docker-compose.yml
- 更灵活的参数控制

❌ **缺点**:
- 命令较长,容易出错
- 手动管理容器

### 方式 3: 直接运行(非容器)

✅ **优点**:
- 启动速度快
- 资源占用少
- 调试方便

❌ **缺点**:
- 环境依赖管理复杂
- 不同系统可能有兼容性问题
- 不便于部署和迁移

---

## 环境准备

### 系统要求

- **操作系统**: Linux / macOS / Windows(WSL2)
- **Docker**: >= 20.10
- **Docker Compose**: >= 2.0
- **内存**: >= 512MB
- **磁盘**: >= 1GB

### 安装 Docker

#### Linux (Ubuntu/Debian)

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 添加用户到 docker 组
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo apt install docker-compose-plugin
```

#### macOS

```bash
# 使用 Homebrew 安装
brew install --cask docker

# 或下载 Docker Desktop
# https://www.docker.com/products/docker-desktop
```

#### Windows

下载并安装 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)

---

## 单账号模式部署

### 1. 配置环境变量

编辑 `.env` 文件:

```bash
# 单账号模式(不设置或设置为 0)
AMAZONQ_ACCOUNT_COUNT=0

# 账号凭证
AMAZONQ_REFRESH_TOKEN=your_refresh_token
AMAZONQ_CLIENT_ID=your_client_id
AMAZONQ_CLIENT_SECRET=your_client_secret
AMAZONQ_PROFILE_ARN=  # 可选,组织账号使用

# 服务配置
PORT=8080
```

### 2. 启动服务

```bash
docker compose up -d
```

### 3. 验证

```bash
curl http://localhost:8080/health
```

预期输出:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

---

## 多账号模式部署

### 1. 配置环境变量

编辑 `.env` 文件:

```bash
# 多账号模式
AMAZONQ_ACCOUNT_COUNT=3

# 账号 1
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=token_1
AMAZONQ_ACCOUNT_1_CLIENT_ID=client_id_1
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=client_secret_1
AMAZONQ_ACCOUNT_1_PROFILE_ARN=
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true

# 账号 2
AMAZONQ_ACCOUNT_2_ID=backup
AMAZONQ_ACCOUNT_2_REFRESH_TOKEN=token_2
AMAZONQ_ACCOUNT_2_CLIENT_ID=client_id_2
AMAZONQ_ACCOUNT_2_CLIENT_SECRET=client_secret_2
AMAZONQ_ACCOUNT_2_PROFILE_ARN=
AMAZONQ_ACCOUNT_2_WEIGHT=5
AMAZONQ_ACCOUNT_2_ENABLED=true

# 账号 3
AMAZONQ_ACCOUNT_3_ID=fallback
AMAZONQ_ACCOUNT_3_REFRESH_TOKEN=token_3
AMAZONQ_ACCOUNT_3_CLIENT_ID=client_id_3
AMAZONQ_ACCOUNT_3_CLIENT_SECRET=client_secret_3
AMAZONQ_ACCOUNT_3_PROFILE_ARN=
AMAZONQ_ACCOUNT_3_WEIGHT=3
AMAZONQ_ACCOUNT_3_ENABLED=true

# 负载均衡策略
LOAD_BALANCE_STRATEGY=weighted_round_robin

# 熔断器配置
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_ERROR_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300
```

### 2. 启动服务

```bash
docker compose up -d
```

### 3. 查看账号状态

```bash
curl http://localhost:8080/admin/accounts
```

预期输出:
```json
[
  {
    "id": "primary",
    "enabled": true,
    "available": true,
    "request_count": 42,
    "error_count": 0,
    "success_count": 42,
    "circuit_breaker_open": false,
    "last_used": "2025-11-12T12:34:56Z"
  },
  ...
]
```

---

## 容器管理

### 启动容器

```bash
# 前台启动(查看日志)
docker compose up

# 后台启动
docker compose up -d

# 重新构建并启动
docker compose up -d --build
```

### 停止容器

```bash
# 停止容器(保留数据)
docker compose stop

# 停止并删除容器(保留数据卷)
docker compose down

# 停止并删除容器和数据卷
docker compose down -v
```

### 重启容器

```bash
docker compose restart
```

### 查看容器状态

```bash
# 查看运行状态
docker compose ps

# 查看资源使用
docker stats amq2api
```

### 进入容器

```bash
# 进入容器 shell
docker compose exec amq2api bash

# 或使用 sh(如果 bash 不可用)
docker compose exec amq2api sh
```

---

## 持久化存储

### 数据卷

Docker Compose 配置了以下数据卷:

```yaml
volumes:
  - token_cache:/home/appuser/.cache/amazonq  # Token 缓存
  - ./logs:/app/logs                          # 日志文件
```

### 备份 Token 缓存

```bash
# 导出数据卷
docker run --rm -v amq2api_token_cache:/data -v $(pwd):/backup \
  alpine tar czf /backup/token_cache_backup.tar.gz -C /data .

# 恢复数据卷
docker run --rm -v amq2api_token_cache:/data -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/token_cache_backup.tar.gz"
```

### 查看数据卷

```bash
# 列出所有数据卷
docker volume ls

# 查看数据卷详情
docker volume inspect amq2api_token_cache
```

---

## 健康检查

### 容器自带健康检查

Docker 容器已配置自动健康检查:

```yaml
healthcheck:
  test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### 查看健康状态

```bash
# 查看健康状态
docker inspect --format='{{.State.Health.Status}}' amq2api

# 查看健康检查日志
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' amq2api
```

### 外部监控

```bash
# 使用 curl 监控
watch -n 30 'curl -s http://localhost:8080/health | jq'

# 使用 Prometheus 监控
curl http://localhost:8080/metrics
```

---

## 日志管理

### 查看日志

```bash
# 查看所有日志
docker compose logs

# 实时跟踪日志
docker compose logs -f

# 查看最近 100 行
docker compose logs --tail=100

# 查看特定时间范围
docker compose logs --since 2025-11-12T10:00:00

# 只看错误日志
docker compose logs | grep ERROR
```

### 日志配置

docker-compose.yml 已配置日志轮转:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"  # 单个文件最大 10MB
    max-file: "3"    # 保留最近 3 个文件
```

### 日志文件位置

```bash
# 容器内日志
docker compose exec amq2api ls -lh /app/logs

# 宿主机日志(挂载目录)
ls -lh ./logs

# Docker 系统日志
docker inspect --format='{{.LogPath}}' amq2api
```

---

## 环境变量

### 全局配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PORT` | `8080` | 服务监听端口 |
| `AMAZONQ_API_ENDPOINT` | `https://q.us-east-1.amazonaws.com/` | Amazon Q API 端点 |
| `AMAZONQ_TOKEN_ENDPOINT` | `https://oidc.us-east-1.amazonaws.com/token` | Token 端点 |
| `ZERO_INPUT_TOKEN_MODELS` | `haiku` | 小模型列表(逗号分隔) |

### 多账号配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `AMAZONQ_ACCOUNT_COUNT` | `0` | 账号数量(0 为单账号模式) |
| `LOAD_BALANCE_STRATEGY` | `weighted_round_robin` | 负载均衡策略 |

### 熔断器配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `CIRCUIT_BREAKER_ENABLED` | `true` | 是否启用熔断器 |
| `CIRCUIT_BREAKER_ERROR_THRESHOLD` | `5` | 熔断错误阈值 |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | `300` | 熔断恢复时间(秒) |

### 健康检查配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `HEALTH_CHECK_INTERVAL` | `300` | 健康检查间隔(秒) |

详细配置说明请参考 [MULTI_ACCOUNT.md](MULTI_ACCOUNT.md)

---

## 故障排查

### 1. 容器无法启动

**症状**: `docker compose up` 失败

**检查步骤**:

```bash
# 查看构建日志
docker compose build

# 查看启动日志
docker compose up

# 查看容器状态
docker compose ps -a
```

**常见原因**:
- 端口被占用: 修改 `.env` 中的 `PORT`
- 环境变量错误: 检查 `.env` 配置
- 依赖安装失败: 检查网络连接

### 2. 健康检查失败

**症状**: 容器状态显示 `unhealthy`

**检查步骤**:

```bash
# 查看健康检查日志
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' amq2api

# 手动测试健康检查
docker compose exec amq2api curl http://localhost:8080/health
```

**常见原因**:
- 服务未完全启动: 等待 start_period(40秒)
- Token 刷新失败: 检查账号凭证
- 端口配置错误: 检查 PORT 环境变量

### 3. Token 刷新失败

**症状**: 日志中出现 "Token refresh failed"

**检查步骤**:

```bash
# 查看详细日志
docker compose logs | grep -A 5 "Token refresh failed"

# 检查 Token 缓存
docker compose exec amq2api ls -la /home/appuser/.cache/amazonq/
```

**解决方案**:
- 检查账号凭证是否正确
- 检查网络连接
- 手动删除 Token 缓存重试:
  ```bash
  docker compose down
  docker volume rm amq2api_token_cache
  docker compose up -d
  ```

### 4. 账号熔断

**症状**: 账号状态显示 `circuit_breaker_open: true`

**检查步骤**:

```bash
# 查看账号状态
curl http://localhost:8080/admin/accounts | jq

# 查看错误计数
curl http://localhost:8080/admin/accounts/<account_id> | jq '.error_count'
```

**解决方案**:

```bash
# 手动重置熔断器
curl -X POST http://localhost:8080/admin/accounts/<account_id>/reset

# 或等待自动恢复(默认 300 秒)
```

### 5. 429 限流错误

**症状**: 日志中出现 "Rate limit exceeded (429)"

**检查步骤**:

```bash
# 查看请求计数
curl http://localhost:8080/admin/accounts | jq '.[].request_count'

# 查看指标
curl http://localhost:8080/metrics | grep error_counter
```

**解决方案**:
- 系统会自动触发熔断器并切换账号
- 增加更多账号分散负载
- 降低请求频率

### 6. 内存不足

**症状**: 容器频繁重启或 OOM

**检查步骤**:

```bash
# 查看资源使用
docker stats amq2api

# 查看容器日志
docker compose logs --tail=50
```

**解决方案**:

在 docker-compose.yml 中添加资源限制:

```yaml
services:
  amq2api:
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

---

## 高级配置

### 使用外部 Prometheus

```yaml
services:
  amq2api:
    ports:
      - "8080:8080"
    networks:
      - monitoring

  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    networks:
      - monitoring

networks:
  monitoring:
```

### Nginx 反向代理

```nginx
upstream amq2api {
    server localhost:8080;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://amq2api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## 安全建议

### 1. 环境变量安全

```bash
# .env 文件权限
chmod 600 .env

# 不要提交 .env 到版本控制
echo ".env" >> .gitignore
```

### 2. 容器安全

- ✅ 使用非 root 用户运行(已配置)
- ✅ 最小化基础镜像(python:3.11-slim)
- ✅ 多阶段构建减少镜像大小
- ⚠️ 定期更新依赖和基础镜像

### 3. 网络安全

```yaml
# 仅暴露必要端口
ports:
  - "127.0.0.1:8080:8080"  # 仅本地访问

# 使用 HTTPS(通过反向代理)
```

---

## 性能优化

### 1. 调整工作进程数

在 main.py 中配置 uvicorn:

```python
uvicorn.run(app, host="0.0.0.0", port=port, workers=4)
```

### 2. 使用生产级 ASGI 服务器

```bash
# Dockerfile 中使用 gunicorn
CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8080"]
```

### 3. 资源限制

```yaml
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

---

## 参考文档

- [多账号配置指南](MULTI_ACCOUNT.md)
- [快速参考手册](QUICK_REFERENCE.md)
- [Bug 修复记录](BUGFIXES.md)
- [项目说明](README.md)
- [Docker 官方文档](https://docs.docker.com/)
- [Docker Compose 文档](https://docs.docker.com/compose/)

---

## 常见问题

**Q: Docker 和直接运行有什么区别?**

A: Docker 提供隔离环境和一致性部署,但资源占用略高。直接运行适合开发调试。

**Q: 如何在生产环境部署?**

A: 建议使用 Docker + Nginx 反向代理 + HTTPS + Prometheus 监控的组合。

**Q: 多账号模式下如何分配负载?**

A: 使用 `weighted_round_robin` 策略,通过 `WEIGHT` 参数控制各账号权重。

**Q: Token 缓存保存在哪里?**

A: Docker 卷 `token_cache` 中,挂载到容器的 `/home/appuser/.cache/amazonq/`。

**Q: 如何升级到新版本?**

A: 
```bash
git pull
docker compose down
docker compose up -d --build
```

---

## 技术支持

遇到问题?

1. 查看 [故障排查](#故障排查) 章节
2. 查看项目 Issues
3. 提交新 Issue 并附上:
   - Docker 版本: `docker --version`
   - Docker Compose 版本: `docker compose version`
   - 错误日志: `docker compose logs`
   - 环境配置(脱敏): `.env` 文件内容

---

**祝部署顺利! 🐳**
