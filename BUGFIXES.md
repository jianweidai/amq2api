# Bug 修复记录

## 修复日志

### 2025-11-12 修复两个关键问题

#### 问题 1: Asyncio Lock 重入死锁 🔒

**现象:**
- 服务启动时卡在 "Initializing account pool..."
- 无法访问任何端点
- 进程无响应

**根本原因:**
`lifespan` 函数中存在 asyncio.Lock 重入问题:
1. 调用 `await read_global_config()` 获取 `_config_lock`
2. 然后调用 `await load_account_pool()`,内部又调用 `await read_global_config()` 尝试再次获取同一个锁
3. `asyncio.Lock` 不支持重入 → 永久等待

**修复方案:**
修改 [config.py:267-277](config.py#L267-L277) 中的 `load_account_pool()` 函数:
```python
# 修复前
async with _config_lock:
    if _account_pool is not None:
        return _account_pool

    config = await read_global_config()  # ❌ 尝试重入锁!
    ...

# 修复后
async with _config_lock:
    if _account_pool is not None:
        return _account_pool

    # 直接使用全局配置(避免重入锁)
    if _global_config is None:
        raise RuntimeError("Global config must be initialized before loading account pool")

    config = _global_config  # ✅ 直接访问全局变量
    ...
```

**影响文件:**
- [config.py](config.py)

---

#### 问题 2: profile_arn 属性错误 ⚠️

**现象:**
```
AttributeError: 'GlobalConfig' object has no attribute 'profile_arn'
```

**根本原因:**
在多账号架构中:
- `profile_arn` 是**账号级别**的配置(存储在 `AccountConfig` 中)
- 但代码尝试从**全局配置** `GlobalConfig` 获取 `profile_arn`
- 且在选择账号**之前**就尝试转换请求

**问题代码:**
```python
# main.py:236-242 (修复前)
config = await read_global_config()
codewhisperer_req = convert_claude_to_codewhisperer_request(
    claude_req,
    conversation_id=None,
    profile_arn=config.profile_arn  # ❌ GlobalConfig 没有此属性!
)
# ... 之后才选择账号
```

**修复方案:**
调整 [main.py:235-297](main.py#L235-L297) 的执行顺序:
1. ✅ **先选择账号** (带 Token 刷新和重试)
2. ✅ **再使用账号的 profile_arn** 转换请求

```python
# 修复后
# 1. 先选择账号
account = None
for attempt in range(max_retries):
    try:
        pool = await get_account_pool()
        account = await pool.select_account()
        # 刷新 Token...
        break
    except TokenRefreshError:
        # 重试...
        continue

# 2. 使用选中账号的 profile_arn
codewhisperer_req = convert_claude_to_codewhisperer_request(
    claude_req,
    conversation_id=None,
    profile_arn=account.profile_arn  # ✅ 从账号获取
)
```

**额外优化:**
- 删除了重复的账号选择代码(第359-413行)
- 统一账号选择逻辑,避免代码冗余

**影响文件:**
- [main.py](main.py)

---

## 验证测试

### 测试 1: 服务启动
```bash
source venv/bin/activate
python3 main.py
```

**预期结果:**
```
INFO - Account pool initialized with 3 accounts
INFO - Starting health check task...
INFO - Uvicorn running on http://0.0.0.0:7999
```

### 测试 2: 健康检查
```bash
curl http://localhost:7999/health
```

**预期响应:**
```json
{
  "status": "healthy",
  "accounts": {
    "total": 3,
    "available": 3,
    "unavailable": 0
  }
}
```

### 测试 3: 账号统计
```bash
curl http://localhost:7999/accounts/stats
```

**预期响应:**
```json
{
  "total_accounts": 3,
  "available_accounts": 3,
  "strategy": "weighted_round_robin",
  "accounts": [...]
}
```

### 测试 4: 实际请求
```bash
curl -X POST http://localhost:7999/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'
```

**预期结果:**
- ✅ 不再报 `profile_arn` 错误
- ✅ 正确从选中账号获取 profile_arn
- ✅ 请求成功转发到 Amazon Q

---

## 技术总结

### 关键学习点

1. **asyncio.Lock 不支持重入**
   - 不同于 `threading.RLock`
   - 同一任务重复获取会死锁
   - 解决方法:使用全局变量或重新设计锁的粒度

2. **多账号架构的配置层次**
   ```
   GlobalConfig (全局配置)
   ├─ port, api_endpoint, load_balance_strategy
   └─ circuit_breaker_enabled, ...

   AccountConfig (账号配置)
   ├─ id, refresh_token, client_id, client_secret
   ├─ profile_arn  ← 账号级别!
   └─ weight, enabled, ...
   ```

3. **请求处理流程顺序很重要**
   ```
   正确流程:
   1. 选择账号 → 2. 获取账号配置 → 3. 转换请求 → 4. 发送请求

   错误流程:
   1. 转换请求(缺少账号信息) → 2. 选择账号 ← 太晚了!
   ```

---

## 相关文件

- [config.py](config.py) - 配置管理和账号池加载
- [main.py](main.py) - FastAPI 服务和请求处理
- [account_config.py](account_config.py) - 账号配置数据结构
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - 完整实现文档

---

**修复日期:** 2025-11-12
**修复人:** Claude Code
**验证状态:** ✅ 已验证通过
