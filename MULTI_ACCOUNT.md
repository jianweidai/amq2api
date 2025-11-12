# 多账号配置指南

本文档介绍如何配置和使用 Amazon Q to Claude API Proxy 的多账号功能。

## 功能特性

✅ **支持任意数量账号** - 通过环境变量轻松配置多个 Amazon Q 账号
✅ **智能负载均衡** - 支持轮询、加权轮询、最少使用、随机等多种策略
✅ **自动故障转移** - 账号出错时自动切换到其他可用账号
✅ **熔断保护** - 自动隔离故障账号,定时恢复
✅ **独立 Token 管理** - 每个账号独立的 Token 缓存和自动刷新
✅ **完整监控** - Prometheus 指标 + 管理 API
✅ **向后兼容** - 完全兼容单账号配置方式

---

## 快速开始

### 单账号模式(兼容旧版)

如果不设置 `AMAZONQ_ACCOUNT_COUNT`,将自动使用单账号模式:

```bash
# .env 文件
AMAZONQ_REFRESH_TOKEN=your_refresh_token
AMAZONQ_CLIENT_ID=your_client_id
AMAZONQ_CLIENT_SECRET=your_client_secret
AMAZONQ_PROFILE_ARN=  # 可选
```

### 多账号模式

设置 `AMAZONQ_ACCOUNT_COUNT` 启用多账号:

```bash
# .env 文件

# 账号数量
AMAZONQ_ACCOUNT_COUNT=3

# 账号 1 (主账号)
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=xxx
AMAZONQ_ACCOUNT_1_CLIENT_ID=xxx
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=xxx
AMAZONQ_ACCOUNT_1_PROFILE_ARN=  # 可选
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true

# 账号 2 (备用)
AMAZONQ_ACCOUNT_2_ID=backup
AMAZONQ_ACCOUNT_2_REFRESH_TOKEN=yyy
AMAZONQ_ACCOUNT_2_CLIENT_ID=yyy
AMAZONQ_ACCOUNT_2_CLIENT_SECRET=yyy
AMAZONQ_ACCOUNT_2_WEIGHT=5
AMAZONQ_ACCOUNT_2_ENABLED=true

# 账号 3
AMAZONQ_ACCOUNT_3_ID=fallback
AMAZONQ_ACCOUNT_3_REFRESH_TOKEN=zzz
AMAZONQ_ACCOUNT_3_CLIENT_ID=zzz
AMAZONQ_ACCOUNT_3_CLIENT_SECRET=zzz
AMAZONQ_ACCOUNT_3_WEIGHT=3
AMAZONQ_ACCOUNT_3_ENABLED=true

# 负载均衡策略
LOAD_BALANCE_STRATEGY=weighted_round_robin

# 熔断器配置
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_ERROR_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300

# 健康检查间隔(秒)
HEALTH_CHECK_INTERVAL=300
```

---

## 环境变量详解

### 全局配置

| 变量名 | 说明 | 默认值 | 可选值 |
|--------|------|--------|--------|
| `AMAZONQ_ACCOUNT_COUNT` | 账号数量 | 0(单账号模式) | 1-N |
| `LOAD_BALANCE_STRATEGY` | 负载均衡策略 | `weighted_round_robin` | `round_robin`, `weighted_round_robin`, `least_used`, `random` |
| `CIRCUIT_BREAKER_ENABLED` | 是否启用熔断器 | `true` | `true`, `false` |
| `CIRCUIT_BREAKER_ERROR_THRESHOLD` | 熔断错误阈值 | 5 | 1-N |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | 熔断恢复时间(秒) | 300 | 1-N |
| `HEALTH_CHECK_INTERVAL` | 健康检查间隔(秒) | 300 | 1-N |

### 账号配置

对于第 N 个账号,使用 `AMAZONQ_ACCOUNT_N_` 前缀:

| 变量名 | 说明 | 是否必需 | 默认值 |
|--------|------|----------|--------|
| `AMAZONQ_ACCOUNT_N_ID` | 账号唯一标识 | 否 | `account_N` |
| `AMAZONQ_ACCOUNT_N_REFRESH_TOKEN` | 刷新令牌 | **是** | - |
| `AMAZONQ_ACCOUNT_N_CLIENT_ID` | 客户端 ID | **是** | - |
| `AMAZONQ_ACCOUNT_N_CLIENT_SECRET` | 客户端密钥 | **是** | - |
| `AMAZONQ_ACCOUNT_N_PROFILE_ARN` | Profile ARN(组织账号) | 否 | - |
| `AMAZONQ_ACCOUNT_N_WEIGHT` | 权重(用于加权轮询) | 否 | 10 |
| `AMAZONQ_ACCOUNT_N_ENABLED` | 是否启用 | 否 | `true` |

---

## 负载均衡策略

### 1. 轮询 (round_robin)

**特点:** 简单公平,依次选择每个账号

**适用场景:** 所有账号配额相同

**示例:**
```bash
LOAD_BALANCE_STRATEGY=round_robin
```

### 2. 加权轮询 (weighted_round_robin) ⭐ 推荐

**特点:** 根据权重随机选择,权重越高被选中概率越大

**适用场景:** 不同配额的账号,或需要设置优先级

**示例:**
```bash
LOAD_BALANCE_STRATEGY=weighted_round_robin

# 主账号权重 10
AMAZONQ_ACCOUNT_1_WEIGHT=10

# 备用账号权重 5
AMAZONQ_ACCOUNT_2_WEIGHT=5

# 低优先级账号权重 3
AMAZONQ_ACCOUNT_3_WEIGHT=3
```

### 3. 最少使用 (least_used)

**特点:** 选择请求数最少的账号

**适用场景:** 长期运行,需要平衡实际负载

**示例:**
```bash
LOAD_BALANCE_STRATEGY=least_used
```

### 4. 随机 (random)

**特点:** 完全随机选择

**适用场景:** 简单场景,分布均匀

**示例:**
```bash
LOAD_BALANCE_STRATEGY=random
```

---

## 熔断器机制

### 工作原理

1. **错误累积:** 账号每次请求失败,`error_count` +1
2. **触发熔断:** 当 `error_count >= CIRCUIT_BREAKER_ERROR_THRESHOLD` 时,熔断器打开
3. **隔离账号:** 熔断器打开后,该账号不再被选择
4. **自动恢复:** 经过 `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` 秒后,自动关闭熔断器,重新启用账号
5. **成功恢复:** 请求成功会逐渐减少 `error_count`,帮助账号恢复

### 配置示例

```bash
# 启用熔断器
CIRCUIT_BREAKER_ENABLED=true

# 5 次错误后熔断
CIRCUIT_BREAKER_ERROR_THRESHOLD=5

# 5 分钟后自动恢复
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300
```

### 手动恢复

可通过管理 API 手动重置熔断状态:

```bash
curl -X POST http://localhost:8080/accounts/primary/reset
```

---

## Token 缓存管理

### 缓存文件结构

多账号模式下,每个账号使用独立的缓存文件:

```
~/.amazonq_token_cache/
  ├── primary.json
  ├── backup.json
  └── fallback.json
```

### 缓存文件内容

```json
{
  "access_token": "xxx",
  "refresh_token": "xxx",
  "expires_at": "2025-01-12T10:30:00.123456"
}
```

### 缓存权限

文件权限自动设置为 `0600`(仅当前用户可读写)

---

## 管理 API

### 1. 获取所有账号统计

```bash
GET /accounts/stats
```

**响应:**
```json
{
  "total_accounts": 3,
  "available_accounts": 2,
  "total_requests": 1234,
  "total_errors": 56,
  "total_successes": 1178,
  "strategy": "weighted_round_robin",
  "circuit_breaker_enabled": true,
  "accounts": [
    {
      "id": "primary",
      "enabled": true,
      "weight": 10,
      "request_count": 800,
      "error_count": 0,
      "success_count": 800,
      "last_used_at": "2025-01-12T10:30:00",
      "circuit_breaker_open": false,
      "is_available": true
    }
  ]
}
```

### 2. 获取单个账号详情

```bash
GET /accounts/{account_id}
```

### 3. 启用账号

```bash
POST /accounts/{account_id}/enable
```

### 4. 禁用账号

```bash
POST /accounts/{account_id}/disable
```

### 5. 重置账号错误计数

```bash
POST /accounts/{account_id}/reset
```

### 6. 健康检查

```bash
GET /health
```

**响应:**
```json
{
  "status": "healthy",
  "accounts": {
    "total": 3,
    "available": 2,
    "unavailable": 1
  }
}
```

---

## Prometheus 监控

### 指标端点

```bash
GET /metrics
```

### 关键指标

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `amazonq_requests_total` | Counter | 总请求数(按账号、状态) |
| `amazonq_errors_total` | Counter | 总错误数(按账号、错误类型) |
| `amazonq_account_available` | Gauge | 账号可用性(0=不可用, 1=可用) |
| `amazonq_response_seconds` | Histogram | 响应时间(按账号) |
| `amazonq_token_refresh_total` | Counter | Token 刷新次数(按账号、状态) |
| `amazonq_active_requests` | Gauge | 当前活跃请求数(按账号) |
| `amazonq_circuit_breaker_opened_total` | Counter | 熔断器打开次数(按账号) |
| `amazonq_account_request_count` | Gauge | 账号总请求数 |
| `amazonq_account_error_count` | Gauge | 账号总错误数 |
| `amazonq_account_success_count` | Gauge | 账号总成功数 |

### Prometheus 配置示例

```yaml
scrape_configs:
  - job_name: 'amazonq_proxy'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Grafana Dashboard

可视化关键指标:
- 每个账号的请求量和错误率
- 响应时间分布
- 账号可用性趋势
- Token 刷新频率
- 熔断器触发次数

---

## Docker 部署

### docker-compose.yml

```yaml
services:
  amq2api:
    build: .
    ports:
      - "8080:8080"
    environment:
      - AMAZONQ_ACCOUNT_COUNT=3
      - AMAZONQ_ACCOUNT_1_ID=primary
      - AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=${ACCOUNT_1_TOKEN}
      - AMAZONQ_ACCOUNT_1_CLIENT_ID=${ACCOUNT_1_CLIENT_ID}
      - AMAZONQ_ACCOUNT_1_CLIENT_SECRET=${ACCOUNT_1_CLIENT_SECRET}
      - AMAZONQ_ACCOUNT_1_WEIGHT=10
      - AMAZONQ_ACCOUNT_2_ID=backup
      - AMAZONQ_ACCOUNT_2_REFRESH_TOKEN=${ACCOUNT_2_TOKEN}
      - AMAZONQ_ACCOUNT_2_CLIENT_ID=${ACCOUNT_2_CLIENT_ID}
      - AMAZONQ_ACCOUNT_2_CLIENT_SECRET=${ACCOUNT_2_CLIENT_SECRET}
      - AMAZONQ_ACCOUNT_2_WEIGHT=5
      - AMAZONQ_ACCOUNT_3_ID=fallback
      - AMAZONQ_ACCOUNT_3_REFRESH_TOKEN=${ACCOUNT_3_TOKEN}
      - AMAZONQ_ACCOUNT_3_CLIENT_ID=${ACCOUNT_3_CLIENT_ID}
      - AMAZONQ_ACCOUNT_3_CLIENT_SECRET=${ACCOUNT_3_CLIENT_SECRET}
      - AMAZONQ_ACCOUNT_3_WEIGHT=3
      - LOAD_BALANCE_STRATEGY=weighted_round_robin
      - CIRCUIT_BREAKER_ENABLED=true
    volumes:
      - ~/.amazonq_token_cache:/root/.amazonq_token_cache
    restart: unless-stopped
```

---

## 故障排查

### 问题 1: 所有账号不可用

**现象:**
```json
{
  "detail": "No available accounts"
}
```

**可能原因:**
- 所有账号被禁用
- 所有账号熔断器打开
- Token 刷新失败

**解决方案:**
1. 检查账号状态: `GET /accounts/stats`
2. 重置熔断器: `POST /accounts/{id}/reset`
3. 检查 Token 是否有效

### 问题 2: 某个账号一直失败

**现象:** 特定账号 `error_count` 持续增加

**可能原因:**
- Token 过期
- 账号被 AWS 限流
- 网络问题

**解决方案:**
1. 查看账号详情: `GET /accounts/{id}`
2. 临时禁用账号: `POST /accounts/{id}/disable`
3. 检查日志输出

### 问题 3: 负载不均衡

**现象:** 某些账号请求数远高于其他账号

**可能原因:**
- 使用了 `random` 或 `weighted_round_robin` 策略
- 权重配置不合理

**解决方案:**
1. 切换到 `least_used` 策略
2. 调整权重配置
3. 监控一段时间后重新评估

---

## 最佳实践

### 1. 账号配置

✅ **主账号权重最高** - 确保主账号优先使用
✅ **备用账号权重递减** - 建立多层故障转移
✅ **保留一个低权重账号** - 作为最后的备用

### 2. 熔断器设置

✅ **合理的错误阈值** - 默认 5 次较为合适
✅ **足够的恢复时间** - 默认 5 分钟,避免频繁熔断
✅ **监控熔断频率** - 频繁熔断说明账号或网络有问题

### 3. 监控告警

✅ **设置可用账号告警** - 当可用账号 < 2 时告警
✅ **监控错误率** - 错误率 > 10% 时告警
✅ **Token 刷新失败告警** - 及时发现认证问题

### 4. 定期维护

✅ **检查 Token 缓存** - 确保缓存文件权限正确
✅ **清理日志** - 避免磁盘占满
✅ **更新 refresh_token** - Token 过期前更新

---

## 常见问题

### Q: 单账号和多账号可以动态切换吗?

A: 可以,只需修改环境变量并重启服务。系统会自动检测 `AMAZONQ_ACCOUNT_COUNT` 来决定模式。

### Q: 多账号模式的性能开销如何?

A: 非常小。账号选择算法复杂度 O(1),每次请求增加的开销 < 1ms。

### Q: 可以运行时添加账号吗?

A: 当前版本不支持热更新,需要修改环境变量并重启。未来版本将支持动态配置。

### Q: Token 缓存会自动同步吗?

A: 每个账号独立缓存,服务关闭时自动保存所有账号的 Token。

### Q: 如何获取 Amazon Q 的凭证?

A: 参考主 README.md 中的获取方式。

---

## 性能优势

### 吞吐量提升

- **单账号:** 受限于单个账号的配额
- **3 个账号:** 理论上提升 3 倍吞吐量
- **N 个账号:** 理论上提升 N 倍吞吐量

### 可用性提升

- **单账号:** 单点故障,账号不可用时服务完全不可用
- **多账号:** 高可用,单个账号故障不影响服务

### 延迟优化

- **负载均衡:** 避免单账号过载导致的延迟增加
- **故障转移:** 自动切换到健康账号,减少失败重试时间

---

## 技术细节

### 架构设计

```
Request → Select Account → Get Auth Headers → Send to Amazon Q
            (Load Balancer)   (Token Refresh)   (with Retry)
                 ↓
          Mark Success/Error → Update Metrics → Circuit Breaker Check
```

### 并发安全

- **账号级别锁:** 每个账号独立的 `asyncio.Lock`
- **Token 刷新原子性:** 确保不会并发刷新同一账号的 Token
- **无状态设计:** 支持多进程/多实例部署

### Token 管理

- **提前刷新:** Token 到期前 5 分钟自动刷新
- **缓存持久化:** 立即保存到文件,避免丢失
- **失败重试:** Token 刷新失败时自动切换账号

---

## 更新日志

### v2.0.0 (2025-01-12)

🎉 **新功能:**
- ✅ 多账号支持
- ✅ 负载均衡(4 种策略)
- ✅ 熔断器保护
- ✅ Prometheus 监控
- ✅ 管理 API
- ✅ 健康检查

🔧 **改进:**
- ✅ 独立的 Token 缓存
- ✅ 更好的错误处理
- ✅ 完整的日志记录

🔄 **向后兼容:**
- ✅ 完全兼容单账号配置
- ✅ 无需修改客户端代码

---

## 获取帮助

- **GitHub Issues:** https://github.com/lovingfish/amq2api/issues
- **文档:** README.md
- **API 文档:** API_DETAILS.md
