# 快速参考指南

## 🚀 快速启动

```bash
# 1. 激活虚拟环境并启动
source venv/bin/activate
python3 main.py

# 2. 或使用后台运行
source venv/bin/activate
nohup python3 main.py > service.log 2>&1 & echo $! > service.pid
```

## 🔍 常用检查命令

### 服务状态
```bash
# 健康检查
curl http://localhost:7999/health

# 账号统计
curl -s http://localhost:7999/accounts/stats | python3 -m json.tool

# 单个账号详情
curl -s http://localhost:7999/accounts/primary | python3 -m json.tool

# Prometheus 指标
curl http://localhost:7999/metrics
```

### 进程管理
```bash
# 查看进程
ps aux | grep "python.*main.py"

# 查看端口占用
lsof -i :7999

# 停止服务
kill $(cat service.pid)

# 查看日志(后台运行时)
tail -f service.log
```

## 📊 管理 API

### 启用/禁用账号
```bash
# 禁用账号
curl -X POST http://localhost:7999/accounts/backup/disable

# 启用账号
curl -X POST http://localhost:7999/accounts/backup/enable
```

### 重置熔断器
```bash
# 重置账号的错误计数和熔断状态
curl -X POST http://localhost:7999/accounts/primary/reset
```

## 🐛 故障排查

### 问题 1: 服务无法启动
```bash
# 检查依赖
pip list | grep -E "fastapi|httpx|prometheus"

# 检查语法
python3 -m py_compile main.py

# 查看错误日志
tail -50 service.log
```

### 问题 2: 端口被占用
```bash
# 查看端口占用
lsof -i :7999

# 杀掉占用进程
kill -9 <PID>

# 或更改端口
export PORT=8080
```

### 问题 3: Token 刷新失败
```bash
# 查看账号状态
curl http://localhost:7999/accounts/stats

# 检查 .env 配置
cat .env | grep AMAZONQ_ACCOUNT

# 重置问题账号
curl -X POST http://localhost:7999/accounts/<account_id>/reset
```

### 问题 4: 所有账号不可用
```bash
# 查看健康状态
curl http://localhost:7999/health

# 查看详细错误(日志)
grep ERROR service.log | tail -20

# 检查熔断器状态
curl -s http://localhost:7999/accounts/stats | jq '.accounts[] | select(.circuit_breaker_open==true)'
```

## 📝 配置相关

### 查看当前配置
```bash
# 查看账号数量
grep AMAZONQ_ACCOUNT_COUNT .env

# 查看负载均衡策略
grep LOAD_BALANCE_STRATEGY .env

# 查看熔断器配置
grep CIRCUIT_BREAKER .env
```

### 修改配置
```bash
# 编辑配置文件
vim .env

# 重启服务生效
kill $(cat service.pid)
source venv/bin/activate && nohup python3 main.py > service.log 2>&1 & echo $! > service.pid
```

## 🧪 测试请求

### 简单测试
```bash
curl -X POST http://localhost:7999/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [
      {"role": "user", "content": "Hello, this is a test"}
    ],
    "max_tokens": 100
  }'
```

### 测试负载均衡
```bash
# 发送10个请求
for i in {1..10}; do
  curl -s -X POST http://localhost:7999/v1/messages \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-sonnet-4-5","messages":[{"role":"user","content":"Test '$i'"}],"max_tokens":50}' \
    > /dev/null
  echo "Request $i sent"
done

# 查看请求分布
curl -s http://localhost:7999/accounts/stats | jq '.accounts[] | {id, request_count}'
```

## 📦 环境变量速查

### 必需配置
```bash
AMAZONQ_ACCOUNT_COUNT=3                    # 账号数量

# 账号 1
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=xxx
AMAZONQ_ACCOUNT_1_CLIENT_ID=xxx
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=xxx
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true
```

### 可选配置
```bash
PORT=7999                                  # 服务端口
LOAD_BALANCE_STRATEGY=weighted_round_robin # 负载均衡策略
CIRCUIT_BREAKER_ENABLED=true               # 熔断器开关
CIRCUIT_BREAKER_ERROR_THRESHOLD=5          # 熔断阈值
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300       # 恢复时间(秒)
HEALTH_CHECK_INTERVAL=300                  # 健康检查间隔(秒)
```

## 📈 监控指标

### Prometheus 指标说明
```bash
# 请求统计
amazonq_requests_total{account_id="primary",status="success"}

# 错误统计
amazonq_errors_total{account_id="primary",error_type="token_refresh"}

# 账号可用性 (0=不可用, 1=可用)
amazonq_account_available{account_id="primary"}

# 响应时间(秒)
amazonq_response_seconds{account_id="primary"}

# 活跃请求数
amazonq_active_requests{account_id="primary"}

# 熔断器打开次数
amazonq_circuit_breaker_opened_total{account_id="primary"}
```

### 查看指标
```bash
# 所有指标
curl http://localhost:7999/metrics

# 筛选特定指标
curl -s http://localhost:7999/metrics | grep "amazonq_requests_total"

# 统计总请求数
curl -s http://localhost:7999/metrics | grep "amazonq_requests_total" | awk '{sum+=$NF} END {print sum}'
```

## 🔧 常见操作

### 添加新账号
1. 编辑 .env,增加账号配置
2. 更新 `AMAZONQ_ACCOUNT_COUNT`
3. 重启服务

### 临时禁用账号
```bash
# API 方式(无需重启)
curl -X POST http://localhost:7999/accounts/backup/disable

# 配置文件方式(需重启)
# 修改 .env: AMAZONQ_ACCOUNT_2_ENABLED=false
# 重启服务
```

### 调整权重
1. 修改 .env: `AMAZONQ_ACCOUNT_1_WEIGHT=20`
2. 重启服务
3. 验证: `curl http://localhost:7999/accounts/stats`

### 切换负载均衡策略
```bash
# 修改 .env
LOAD_BALANCE_STRATEGY=round_robin        # 简单轮询
# LOAD_BALANCE_STRATEGY=weighted_round_robin  # 加权轮询
# LOAD_BALANCE_STRATEGY=least_used           # 最少使用
# LOAD_BALANCE_STRATEGY=random               # 随机

# 重启服务
```

## 📚 文档链接

- **完整文档**: [MULTI_ACCOUNT.md](MULTI_ACCOUNT.md)
- **实现总结**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **部署清单**: [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
- **Bug 修复**: [BUGFIXES.md](BUGFIXES.md)
- **项目说明**: [README.md](README.md)

## ⚡ 快捷命令别名

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc

# 服务管理
alias amq-start='cd /path/to/amq2api && source venv/bin/activate && python3 main.py'
alias amq-stop='kill $(cat /path/to/amq2api/service.pid)'
alias amq-restart='amq-stop && sleep 2 && amq-start'
alias amq-log='tail -f /path/to/amq2api/service.log'

# 状态检查
alias amq-health='curl -s http://localhost:7999/health | jq'
alias amq-stats='curl -s http://localhost:7999/accounts/stats | jq'
alias amq-metrics='curl -s http://localhost:7999/metrics'
```

---

**提示:** 将本文档加入书签,以便快速查找常用命令!
