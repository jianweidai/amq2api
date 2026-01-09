# 限流和统计功能使用指南

## 概述

Release 分支现在支持账号级别的 API 调用限流和统计功能，帮助你更好地管理多账号使用。

## 功能特性

### 1. 滑动窗口限流

- 每个账号可以设置独立的每小时调用限制
- 使用滑动窗口算法，精确控制调用频率
- 自动过滤已达到限流的账号
- 默认限制：20 次/小时

### 2. 调用统计

- 实时统计过去 1 小时的调用次数
- 统计过去 24 小时的调用次数
- 统计总调用次数
- 显示剩余配额

### 3. 自动集成

- 与账号选择逻辑集成
- 与冷却机制集成
- 与 Gemini 重试机制集成

## 使用方法

### 查看账号统计

```bash
curl -H "X-Admin-Key: your_admin_key" \
  http://localhost:8080/v2/accounts/{account_id}/stats
```

**响应示例：**
```json
{
  "account_id": "abc-123",
  "calls_last_hour": 15,
  "calls_last_day": 120,
  "total_calls": 500,
  "rate_limit_per_hour": 20,
  "remaining_quota": 5,
  "cooldown_remaining_seconds": 0,
  "is_in_cooldown": false
}
```

### 更新限流配置

通过管理界面或 API 更新账号的 `rate_limit_per_hour` 字段：

```python
from src.auth.account_manager import update_account_rate_limit

# 设置为 50 次/小时
update_account_rate_limit(account_id, 50)
```

### 手动记录调用（高级用法）

```python
from src.auth.account_manager import record_api_call

# 记录一次调用
record_api_call(account_id, model="claude-sonnet-4.5")
```

### 检查限流状态

```python
from src.auth.account_manager import check_rate_limit

# 检查账号是否可用
if check_rate_limit(account_id):
    print("账号可用")
else:
    print("账号已达到限流")
```

## 工作原理

### 滑动窗口算法

系统使用滑动窗口算法来计算限流：

1. 每次 API 调用完成时，记录到 `call_logs` 表
2. 选择账号时，查询过去 1 小时内的调用次数
3. 如果调用次数 >= `rate_limit_per_hour`，则过滤该账号
4. 自动清理过期的调用记录（通过时间戳查询）

### 自动过滤

`get_random_account` 函数会自动过滤：
- 已禁用的账号
- 在冷却期的账号
- 已达到限流的账号
- 配额不足的账号（Gemini）

### Gemini 自动重试

当 Gemini 账号触发 429 错误时：

1. 系统判断是速率限制还是配额耗尽
2. 如果是速率限制：设置 5 分钟冷却
3. 自动选择其他可用的 Gemini 账号
4. 使用新账号重新发起请求
5. 如果没有其他账号，返回 429 错误

## 配置建议

### 根据账号类型设置限流

**Amazon Q 账号：**
- 建议：20-30 次/小时
- 原因：Amazon Q 有较严格的速率限制

**Gemini 账号：**
- 建议：50-100 次/小时
- 原因：Gemini 的 RPM 限制较高

**Custom API 账号：**
- 根据上游 API 的限制设置

### 多账号负载均衡

通过设置不同的 `weight` 和 `rate_limit_per_hour`：

```python
# 高性能账号
update_account(account_id_1, weight=70)
update_account_rate_limit(account_id_1, 100)

# 普通账号
update_account(account_id_2, weight=30)
update_account_rate_limit(account_id_2, 50)
```

## 监控和调试

### 查看所有账号的统计

```python
from src.auth.account_manager import list_all_accounts, get_account_call_stats

accounts = list_all_accounts()
for account in accounts:
    stats = get_account_call_stats(account['id'])
    print(f"{account['label']}: {stats['calls_last_hour']}/{stats['rate_limit_per_hour']}")
```

### 日志监控

系统会记录以下日志：

```
账号 xxx 已达到限流，跳过
账号 xxx 触发速率限制（RPM/TPM），进入 5 分钟冷却期
尝试切换到其他 Gemini 账号重试...
找到新账号 yyy，开始重试
```

## 数据库维护

### 清理旧的调用记录

调用记录会随时间累积，建议定期清理：

```sql
-- SQLite
DELETE FROM call_logs WHERE timestamp < datetime('now', '-7 days');

-- MySQL
DELETE FROM amq2api_call_logs WHERE timestamp < DATE_SUB(NOW(), INTERVAL 7 DAY);
```

### 查看调用记录

```sql
-- 查看最近的调用
SELECT * FROM call_logs ORDER BY timestamp DESC LIMIT 100;

-- 按账号统计
SELECT account_id, COUNT(*) as count 
FROM call_logs 
WHERE timestamp >= datetime('now', '-1 hour')
GROUP BY account_id;
```

## 故障排查

### 问题：所有账号都显示已限流

**可能原因：**
1. `rate_limit_per_hour` 设置过低
2. 调用频率确实过高
3. 时间戳记录错误

**解决方法：**
```python
# 检查限流配置
account = get_account(account_id)
print(account.get('rate_limit_per_hour'))

# 临时提高限流
update_account_rate_limit(account_id, 100)

# 清除调用记录（谨慎使用）
# DELETE FROM call_logs WHERE account_id = 'xxx';
```

### 问题：Gemini 重试不生效

**可能原因：**
1. 使用了 `X-Account-ID` 指定账号
2. 没有其他可用的 Gemini 账号
3. 所有 Gemini 账号都在冷却或限流中

**解决方法：**
- 不要在请求中指定 `X-Account-ID`
- 添加更多 Gemini 账号
- 检查账号的冷却和限流状态

## 最佳实践

1. **合理设置限流**：根据实际使用情况调整
2. **监控统计数据**：定期查看账号使用情况
3. **多账号部署**：至少 2-3 个账号以支持重试
4. **定期清理**：清理 7 天以上的调用记录
5. **日志监控**：关注限流和重试相关的日志

## 相关文档

- [账号管理 API](../API_DETAILS.md)
- [多账号配置](../README.md#多账号管理)
- [Gemini 配置](../README.md#gemini-配置)
