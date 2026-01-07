# Azure Thinking Continuity 功能文档

## 概述

本功能解决了多渠道（Gemini、Amazon Q、Custom API）交替使用时，切换到 Azure 渠道后思考链断裂的问题。

### 问题背景

当使用多渠道路由时，不同渠道产生的 thinking 块格式不同：
- **Azure Anthropic API**: 要求 thinking 块必须包含 `signature` 字段
- **Gemini / Amazon Q**: 产生的 thinking 块没有 `signature` 字段

原有实现的问题：
1. 当检测到历史消息中存在无效的 thinking 块（缺少 signature）时，会完全禁用 `thinking` 参数
2. 这导致切换到 Azure 渠道后，新响应无法继续思考，思考链断裂

### Azure API 特殊要求

Azure Anthropic API 有一个重要的限制：
> 当 `thinking` 启用时，最后一条 `assistant` 消息必须以 thinking 块开头

这意味着：
- 如果最后一条 assistant 消息以有效的 thinking 块（有 signature）开头 → thinking 保持启用
- 如果最后一条 assistant 消息没有有效的 thinking 块开头 → 必须禁用 thinking

### 解决方案

根据 Azure API 的要求，实现了以下逻辑：

1. **检查最后一条 assistant 消息**：
   - 如果以有效 thinking 块（有 signature）开头 → 保持 thinking 启用
   - 如果没有有效 thinking 块开头 → 禁用 thinking 功能

2. **当 thinking 保持启用时**：
   - 有效的 thinking 块（有 signature）→ 保留
   - 无效的 thinking 块（无 signature）→ 转换为 `<previous_thinking>` 文本块
   - 有效的 redacted_thinking 块（有 data）→ 保留
   - 无效的 redacted_thinking 块（无 data）→ 移除

3. **当 thinking 被禁用时**：
   - 移除所有 thinking 和 redacted_thinking 块

## 核心实现

### 文件位置

- **主要实现**: `src/custom_api/handler.py`
- **测试文件**: 
  - `tests/test_thinking_fix.py` - 单元测试
  - `tests/test_azure_thinking_properties.py` - 属性测试

### 关键函数

#### `_convert_thinking_block_to_text(block: Dict[str, Any]) -> Dict[str, Any]`

将无效的 thinking 块转换为文本块。

**输入**:
```python
{
    "type": "thinking",
    "thinking": "Let me analyze this problem..."
}
```

**输出**:
```python
{
    "type": "text",
    "text": "<previous_thinking>Let me analyze this problem...</previous_thinking>"
}
```

#### `_clean_claude_request_for_azure(request_data: Dict[str, Any]) -> Dict[str, Any]`

为 Azure Anthropic API 清理 Claude 请求数据。

**处理逻辑**:
1. 移除不支持的顶层字段（`context_management`, `betas` 等）
2. 处理 thinking 块：
   - 有效的（有 signature）→ 保留
   - 无效的（无 signature）→ 转换为 `<previous_thinking>` 文本
3. 处理 redacted_thinking 块：
   - 有效的（有 data）→ 保留
   - 无效的（无 data）→ 移除
4. 保持 thinking 参数启用（不再因无效块而禁用）
5. 清理工具格式
6. 确保消息内容非空

## 处理流程

```
Claude Request (with history from Gemini/Amazon Q)
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  _clean_claude_request_for_azure()                        │
│                                                           │
│  1. Check if thinking is enabled in request               │
│  2. Find last assistant message                           │
│  3. Check if last assistant message starts with valid     │
│     thinking block (has signature)                        │
│     - YES → Keep thinking enabled                         │
│     - NO  → Disable thinking                              │
│  4. For each message:                                     │
│     If thinking enabled:                                  │
│       - Valid thinking block (has signature) → Preserve   │
│       - Invalid thinking block (no signature) → Convert   │
│         to text: <previous_thinking>content</previous_...>│
│       - Valid redacted_thinking → Preserve                │
│       - Invalid redacted_thinking → Remove                │
│     If thinking disabled:                                 │
│       - Remove all thinking/redacted_thinking blocks      │
│  5. Ensure non-empty messages                             │
└──────────────────────────────────────────────────────────┘
        │
        ▼
Cleaned Request (thinking enabled/disabled based on last assistant message)
        │
        ▼
Azure Anthropic API
        │
        ▼
Response with new thinking blocks (with valid signatures)
```

## 数据结构

### 输入数据结构

```python
# Claude 请求中的 thinking 块（来自其他渠道，无 signature）
{
    "type": "thinking",
    "thinking": "Let me think about this..."
}

# Claude 请求中的 thinking 块（来自 Azure，有 signature）
{
    "type": "thinking",
    "thinking": "Let me think about this...",
    "signature": "abc123..."
}

# Claude 请求中的 redacted_thinking 块
{
    "type": "redacted_thinking",
    "data": "encrypted_data..."
}
```

### 输出数据结构

```python
# 转换后的文本块
{
    "type": "text",
    "text": "<previous_thinking>Let me think about this...</previous_thinking>"
}
```

## 正确性属性

本功能通过以下属性测试验证正确性：

| 属性 | 描述 | 验证需求 |
|------|------|----------|
| Property 1 | Thinking parameter preservation - 请求中 thinking 启用时，清理后保持启用 | 1.1, 1.2 |
| Property 2 | Invalid thinking block conversion - 无 signature 的 thinking 块被转换为文本 | 2.1, 2.2 |
| Property 3 | Valid thinking block preservation - 有 signature 的 thinking 块被保留 | 2.3 |
| Property 4 | Content block order preservation - 内容块顺序保持不变 | 2.4 |
| Property 5 | Thinking disabled removes all - thinking 禁用时移除所有 thinking 内容 | 1.3, 3.3 |
| Property 6 | Valid redacted_thinking preservation - 有效的 redacted_thinking 块被保留 | 3.1 |
| Property 7 | Invalid redacted_thinking removal - 无效的 redacted_thinking 块被移除 | 3.2 |
| Property 8 | Non-empty message guarantee - 空消息被跳过（最后一条 assistant 消息除外） | 4.1, 4.3 |
| Property 9 | Backward compatibility - 向后兼容现有行为 | 5.1, 5.2 |

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| thinking 块缺少 `thinking` 字段 | 转换为空文本块 `<previous_thinking></previous_thinking>` |
| redacted_thinking 块缺少 `data` 字段 | 静默移除该块 |
| 消息转换后内容为空 | 跳过该消息（最后一条 assistant 消息除外） |
| 非字典类型的内容块 | 保留原样 |

## 测试

### 运行测试

```bash
# 运行所有相关测试
pytest tests/test_thinking_fix.py tests/test_azure_thinking_properties.py -v

# 只运行属性测试
pytest tests/test_azure_thinking_properties.py -v

# 只运行单元测试
pytest tests/test_thinking_fix.py -v
```

### 测试覆盖

- **单元测试** (`test_thinking_fix.py`): 7 个测试用例
  - 基本 thinking 块清理
  - 内容块顺序保持
  - 空消息处理
  - thinking 启用时的转换
  - thinking 禁用时的移除
  - 向后兼容性（无 thinking 块）
  - 向后兼容性（全部有效 thinking 块）

- **属性测试** (`test_azure_thinking_properties.py`): 7 个测试用例
  - 有效 thinking 块保留
  - 多个有效 thinking 块保留
  - 有效 redacted_thinking 块保留
  - 多个有效 redacted_thinking 块保留
  - 无效 redacted_thinking 块移除
  - 多个无效 redacted_thinking 块移除
  - 混合有效/无效 redacted_thinking 块

## 向后兼容性

本功能保持向后兼容：

1. **无 thinking 块的请求**: 处理方式与之前完全一致
2. **全部有效 thinking 块的请求**: 所有有效块被保留，行为不变
3. **非 Azure 提供商**: `_clean_claude_request_for_azure` 函数不会被调用

## 相关文档

- [Thinking Mode Implementation](./thinking-mode-implementation.md) - 完整的 thinking 模式实现文档
- [API Details](./API_DETAILS.md) - API 详细说明
