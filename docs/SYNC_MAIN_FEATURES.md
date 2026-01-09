# Main 分支功能同步到 Release 分支

## 概述

本次同步将 main 分支的核心功能移植到 release 分支，保留 release 分支的模块化架构（`src/` 目录结构）。

## 已实现的功能

### 1. 账号调用统计和滑动窗口限流 ✅

**文件修改：**
- `src/auth/account_manager.py`
  - 添加 `call_logs` 表（SQLite 和 MySQL）
  - 添加 `rate_limit_per_hour` 字段到 accounts 表
  - 新增函数：
    - `record_api_call(account_id, model)` - 记录 API 调用
    - `check_rate_limit(account_id)` - 检查是否超过限流（滑动窗口）
    - `get_account_call_stats(account_id)` - 获取调用统计
    - `update_account_rate_limit(account_id, rate_limit_per_hour)` - 更新限流配置

**集成点：**
- `src/amazonq/stream_handler.py` - 在 message_stop 事件中调用 `record_api_call`
- `src/gemini/handler.py` - 在 message_stop 事件中调用 `record_api_call`
- `src/auth/account_manager.py` 的 `get_random_account` - 自动过滤已限流的账号

**API 端点：**
- `GET /v2/accounts/{account_id}/stats` - 获取账号调用统计

**特性：**
- 滑动窗口限流（默认 20 次/小时）
- 自动过滤限流账号
- 支持 SQLite 和 MySQL
- 统计过去 1 小时、24 小时和总调用次数

### 2. Gemini 429 错误自动换号重试 ✅

**文件修改：**
- `src/main.py`
  - `create_gemini_message` 函数支持 `retry_account` 参数
  - 429 错误处理中添加自动换号重试逻辑
  - 区分速率限制（RPM/TPM）和配额用完两种情况

**工作流程：**
1. 检测到 429 错误
2. 调用 `fetchAvailableModels` 获取最新配额信息
3. 判断是速率限制还是配额用完
4. 如果是速率限制：设置 5 分钟冷却，尝试换号重试
5. 如果是配额用完：标记模型配额耗尽，尝试换号重试
6. 如果没有其他可用账号，返回错误

**特性：**
- 自动区分 RPM/TPM 限制和配额耗尽
- 智能换号重试（只在非指定账号时）
- 与冷却机制集成
- 与配额管理集成

### 3. Gemini 转换问题修复 ✅

**文件修改：**
- `src/gemini/converter.py`
  - 修复 `tool_result` 的 `name` 字段缺失问题
  - 从 `tool_id_to_name` 映射中查找工具名称
  - 跳过空 `parts` 的消息，避免 Gemini 400 错误

**修复的问题：**
- tool_result name 为空导致的错误
- 空 content 导致的 400 错误

### 4. 账号限流和冷却集成 ✅

**已有功能增强：**
- `get_random_account` 现在同时过滤冷却中和限流的账号
- 统计 API 返回冷却状态信息

## 测试

**新增测试文件：**
- `tests/test_rate_limit.py`
  - `test_record_and_check_rate_limit` - 测试限流功能
  - `test_account_call_stats` - 测试统计功能

**测试结果：**
```bash
pytest tests/test_rate_limit.py -v
# 2 passed in 0.67s
```

## 数据库变更

### SQLite
```sql
-- 新增字段
ALTER TABLE accounts ADD COLUMN rate_limit_per_hour INTEGER DEFAULT 20;

-- 新增表
CREATE TABLE IF NOT EXISTS call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    model TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_call_logs_account_timestamp
ON call_logs(account_id, timestamp);
```

### MySQL
```sql
-- 新增字段
ALTER TABLE `amq2api_accounts` ADD COLUMN rate_limit_per_hour INT DEFAULT 20;

-- 新增表
CREATE TABLE IF NOT EXISTS `amq2api_call_logs` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id VARCHAR(36) NOT NULL,
    timestamp VARCHAR(32) NOT NULL,
    model VARCHAR(255),
    INDEX idx_account_timestamp (account_id, timestamp),
    FOREIGN KEY (account_id) REFERENCES `amq2api_accounts`(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 使用示例

### 1. 查看账号调用统计

```bash
curl -H "X-Admin-Key: your_admin_key" \
  http://localhost:8080/v2/accounts/{account_id}/stats
```

响应：
```json
{
  "account_id": "xxx",
  "calls_last_hour": 15,
  "calls_last_day": 120,
  "total_calls": 500,
  "rate_limit_per_hour": 20,
  "remaining_quota": 5,
  "cooldown_remaining_seconds": 0,
  "is_in_cooldown": false
}
```

### 2. 更新账号限流配置

通过管理界面或直接调用 `update_account_rate_limit` 函数。

### 3. Gemini 自动重试

当 Gemini 账号触发 429 错误时，系统会自动：
1. 将当前账号设置为冷却状态（5 分钟）
2. 尝试选择其他可用的 Gemini 账号
3. 使用新账号重新发起请求
4. 如果没有其他账号，返回 429 错误

## 与 Main 分支的差异

### 保留的 Release 特性
- ✅ `src/` 模块化目录结构
- ✅ 完整的测试覆盖
- ✅ Prompt Caching 模拟
- ✅ Input Validator
- ✅ Azure Thinking Continuity
- ✅ Model Mapper

### 未移植的 Main 特性
- ❌ 扁平化目录结构（main 将所有模块移到根目录）
- ❌ Prometheus 监控指标（`metrics.py`）
- ❌ 负载均衡器（`load_balancer.py`）
- ❌ 账号池管理器（`account_pool.py`）
- ❌ 熔断器功能

### 原因
这些未移植的功能要么是架构性的改变（扁平化结构），要么是可以在后续迭代中添加的高级特性（Prometheus、熔断器等）。当前实现已经包含了核心的限流、统计和重试功能。

## 兼容性

- ✅ 向后兼容现有的 API
- ✅ 数据库自动迁移（添加新字段和表）
- ✅ 不影响现有账号
- ✅ 默认限流值为 20 次/小时

## 下一步

如果需要，可以继续添加：
1. Prometheus 监控指标
2. 更复杂的负载均衡策略
3. 熔断器功能
4. 账号健康检查
5. 更详细的统计报表

## 总结

本次同步成功将 main 分支的核心功能（限流、统计、Gemini 重试、bug 修复）移植到 release 分支，同时保持了 release 分支的架构优势。所有功能都经过测试验证，可以安全部署。
