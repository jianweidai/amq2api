# 多账号部署检查清单

## 📋 部署前准备

### 1. 环境准备
- [ ] Python 3.8+ 已安装
- [ ] pip3 可用
- [ ] 有多个可用的 Amazon Q 账号
- [ ] 已获取每个账号的凭证信息

### 2. 获取账号凭证
对于每个 Amazon Q 账号,需要获取:
- [ ] `REFRESH_TOKEN`: 刷新令牌
- [ ] `CLIENT_ID`: 客户端 ID
- [ ] `CLIENT_SECRET`: 客户端密钥
- [ ] `PROFILE_ARN`: Profile ARN(可选,仅组织账号)

## 🔧 安装步骤

### Step 1: 安装依赖
```bash
# 检查 Python 版本
python3 --version

# 安装依赖
pip3 install -r requirements.txt

# 验证安装
pip3 list | grep -E "(fastapi|httpx|prometheus)"
```

**预期输出**:
```
fastapi                  0.115.0
httpx                    0.27.0
prometheus-client        0.21.0
```

### Step 2: 创建配置文件

#### 选项 A: 单账号模式(快速测试)
```bash
# 复制示例文件
cp .env.multi_account.example .env

# 编辑配置,注释掉 AMAZONQ_ACCOUNT_COUNT
vim .env
```

在 `.env` 中:
```bash
# 注释掉或设置为 0
# AMAZONQ_ACCOUNT_COUNT=0

# 填写单账号信息
AMAZONQ_REFRESH_TOKEN=your_actual_refresh_token
AMAZONQ_CLIENT_ID=your_actual_client_id
AMAZONQ_CLIENT_SECRET=your_actual_client_secret
AMAZONQ_PROFILE_ARN=  # 留空(除非是组织账号)
```

#### 选项 B: 多账号模式(生产推荐)
```bash
# 复制示例文件
cp .env.multi_account.example .env

# 编辑配置
vim .env
```

在 `.env` 中:
```bash
# 设置账号数量
AMAZONQ_ACCOUNT_COUNT=3  # 根据实际账号数量调整

# 配置账号 1
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=your_actual_refresh_token_1
AMAZONQ_ACCOUNT_1_CLIENT_ID=your_actual_client_id_1
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=your_actual_client_secret_1
AMAZONQ_ACCOUNT_1_PROFILE_ARN=
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true

# 配置账号 2
AMAZONQ_ACCOUNT_2_ID=backup
AMAZONQ_ACCOUNT_2_REFRESH_TOKEN=your_actual_refresh_token_2
AMAZONQ_ACCOUNT_2_CLIENT_ID=your_actual_client_id_2
AMAZONQ_ACCOUNT_2_CLIENT_SECRET=your_actual_client_secret_2
AMAZONQ_ACCOUNT_2_PROFILE_ARN=
AMAZONQ_ACCOUNT_2_WEIGHT=5
AMAZONQ_ACCOUNT_2_ENABLED=true

# 配置账号 3
AMAZONQ_ACCOUNT_3_ID=fallback
AMAZONQ_ACCOUNT_3_REFRESH_TOKEN=your_actual_refresh_token_3
AMAZONQ_ACCOUNT_3_CLIENT_ID=your_actual_client_id_3
AMAZONQ_ACCOUNT_3_CLIENT_SECRET=your_actual_client_secret_3
AMAZONQ_ACCOUNT_3_PROFILE_ARN=
AMAZONQ_ACCOUNT_3_WEIGHT=3
AMAZONQ_ACCOUNT_3_ENABLED=true

# 负载均衡配置
LOAD_BALANCE_STRATEGY=weighted_round_robin

# 熔断器配置
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_ERROR_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300

# 健康检查间隔
HEALTH_CHECK_INTERVAL=300
```

### Step 3: 验证配置
```bash
# 检查 .env 文件存在
ls -la .env

# 验证必需字段不为空(示例)
grep -E "AMAZONQ_ACCOUNT_1_REFRESH_TOKEN|AMAZONQ_REFRESH_TOKEN" .env
```

### Step 4: 验证实现完整性
```bash
# 运行验证脚本
python3 verify_implementation.py
```

**预期输出**:
```
================================================================================
✓ 所有检查通过! 多账号实现结构完整。
================================================================================
```

## 🚀 启动服务

### 本地启动
```bash
# 方式 1: 使用启动脚本
./start.sh

# 方式 2: 直接运行
python3 main.py
```

### 检查启动日志
启动成功应看到:
```
INFO - Initializing configuration...
INFO - Configuration initialized successfully
INFO - Initializing account pool...
INFO - Account pool initialized with X accounts
INFO - Starting health check task...
INFO - Application startup complete
INFO - Uvicorn running on http://0.0.0.0:8080
```

## ✅ 部署验证

### 1. 健康检查
```bash
# 服务状态
curl http://localhost:8080/health

# 预期响应
{
  "status": "healthy",
  "accounts": {
    "total": 3,
    "available": 3,
    "unavailable": 0
  }
}
```

### 2. 账号统计
```bash
# 查看所有账号
curl http://localhost:8080/accounts/stats

# 预期响应
{
  "total_accounts": 3,
  "available_accounts": 3,
  "accounts": [
    {
      "id": "primary",
      "enabled": true,
      "weight": 10,
      "request_count": 0,
      "success_count": 0,
      "error_count": 0,
      "circuit_breaker_open": false,
      ...
    },
    ...
  ]
}
```

### 3. 单个账号详情
```bash
# 查看特定账号
curl http://localhost:8080/accounts/primary

# 预期响应
{
  "id": "primary",
  "enabled": true,
  "weight": 10,
  "request_count": 0,
  "success_count": 0,
  "error_count": 0,
  "circuit_breaker_open": false,
  "has_valid_token": true,
  ...
}
```

### 4. Prometheus 指标
```bash
# 查看监控指标
curl http://localhost:8080/metrics

# 预期输出(部分)
# HELP amazonq_requests_total Total number of requests per account
# TYPE amazonq_requests_total counter
amazonq_requests_total{account_id="primary",status="success"} 0.0
...
```

### 5. 测试 API 请求
```bash
# 发送测试请求
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 100,
    "messages": [
      {"role": "user", "content": "Hello, this is a test"}
    ]
  }'

# 应该返回流式响应
```

### 6. 验证负载均衡
```bash
# 发送多个请求
for i in {1..10}; do
  curl -s http://localhost:8080/v1/messages \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-sonnet-4-5","max_tokens":50,"messages":[{"role":"user","content":"Test '$i'"}]}' \
    > /dev/null
  echo "Request $i sent"
done

# 检查请求分布
curl -s http://localhost:8080/accounts/stats | jq '.accounts[] | {id, request_count}'
```

## 🔍 故障排查

### 问题 1: 服务启动失败
```bash
# 检查端口是否被占用
lsof -i :8080

# 检查 .env 文件格式
cat .env | grep -v '^#' | grep -v '^$'

# 检查 Python 模块导入
python3 -c "import fastapi, httpx, prometheus_client"
```

### 问题 2: Token 刷新失败
```bash
# 查看日志中的错误信息
tail -f logs/app.log | grep "Token refresh"

# 验证凭证正确性
# 检查 REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET 是否正确
```

### 问题 3: 账号不可用
```bash
# 检查账号状态
curl http://localhost:8080/accounts/{account_id}

# 重置账号
curl -X POST http://localhost:8080/accounts/{account_id}/reset

# 启用账号
curl -X POST http://localhost:8080/accounts/{account_id}/enable
```

### 问题 4: 熔断器触发
```bash
# 查看熔断状态
curl http://localhost:8080/accounts/stats | jq '.accounts[] | select(.circuit_breaker_open==true)'

# 手动重置
curl -X POST http://localhost:8080/accounts/{account_id}/reset
```

## 📊 监控配置

### Prometheus 配置
在 `prometheus.yml` 中添加:
```yaml
scrape_configs:
  - job_name: 'amazonq-proxy'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### Grafana Dashboard
推荐监控指标:
- `amazonq_requests_total` - 请求总数
- `amazonq_errors_total` - 错误总数
- `amazonq_account_available` - 账号可用性
- `amazonq_response_seconds` - 响应时间
- `amazonq_circuit_breaker_opened_total` - 熔断次数

## 🐳 Docker 部署(可选)

### 构建镜像
```bash
# 确保 Dockerfile 存在
ls -la Dockerfile

# 构建
docker build -t amazonq-proxy:latest .
```

### 运行容器
```bash
# 从 .env 文件运行
docker run -d \
  --name amazonq-proxy \
  -p 8080:8080 \
  --env-file .env \
  amazonq-proxy:latest

# 查看日志
docker logs -f amazonq-proxy

# 检查健康状态
docker exec amazonq-proxy curl http://localhost:8080/health
```

### Docker Compose
```yaml
# docker-compose.yml
version: '3.8'

services:
  amazonq-proxy:
    build: .
    ports:
      - "8080:8080"
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

运行:
```bash
docker compose up -d
docker compose logs -f
```

## 📝 生产部署建议

### 高可用配置
- [ ] 至少 3 个账号
- [ ] 不同权重分配(如 10:5:3)
- [ ] 启用熔断器
- [ ] 配置健康检查

### 安全配置
- [ ] 使用环境变量存储敏感信息
- [ ] 不将 .env 提交到版本控制
- [ ] 定期轮换 Token 和密钥
- [ ] 限制 API 访问(防火墙/反向代理)

### 监控和告警
- [ ] 配置 Prometheus + Grafana
- [ ] 设置账号可用性告警
- [ ] 设置错误率告警(> 10%)
- [ ] 设置熔断次数告警

### 日志管理
- [ ] 配置日志轮转
- [ ] 设置合适的日志级别
- [ ] 集中化日志收集(可选)

### 备份和恢复
- [ ] 备份 .env 配置文件
- [ ] 备份 Token 缓存目录
- [ ] 准备回滚方案

## 📚 参考文档

- 详细使用指南: [MULTI_ACCOUNT.md](MULTI_ACCOUNT.md)
- 实现总结: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- 配置示例: [.env.multi_account.example](.env.multi_account.example)
- 项目说明: [README.md](README.md)

## ✨ 部署完成确认

部署成功的标志:
- [x] 服务正常启动,无错误日志
- [x] `/health` 返回 `healthy` 状态
- [x] `/accounts/stats` 显示所有账号可用
- [x] 测试请求成功返回响应
- [x] `/metrics` 正常输出指标数据
- [x] 负载均衡正常工作(请求分布合理)

---

**部署日期**: ___________
**部署环境**: [ ] 开发 [ ] 测试 [ ] 生产
**账号数量**: ___________
**负载均衡策略**: ___________
**部署人员**: ___________
