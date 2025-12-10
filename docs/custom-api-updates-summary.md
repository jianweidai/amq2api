# Custom API 功能更新总结

## 更新日期：2024-12-11

本文档总结了 custom_api 模块的主要功能更新，包括 thinking 模式支持、缓存模拟、token 统计等。

---

## 1. Thinking 模式支持（OpenAI 格式转 Claude 思考）

### 背景

Claude API 原生支持 `thinking` 参数来启用扩展思考模式，但 OpenAI 格式的 API 不支持此功能。为了让使用 OpenAI 格式的第三方 API 也能在 Claude Code 中显示思考过程，我们实现了一个转换层。

### 实现原理

通过三个阶段的转换实现 thinking 模式：

#### 阶段 1：请求转换（注入思考提示）

在 `custom_api/converter.py` 中定义思考提示词：

```python
THINKING_HINT = """
<important_instruction>
You MUST wrap your internal reasoning process in <thinking>...</thinking> tags before providing your final response.
Structure your response as:
<thinking>
[Your step-by-step reasoning, analysis, and thought process here]
</thinking>

[Your final response to the user here]
</important_instruction>
"""
```

当检测到请求中包含 `thinking` 参数时，将此提示注入到 system prompt 中：

```python
def convert_claude_to_openai_request(claude_request: dict) -> tuple[dict, bool]:
    thinking_enabled = False
    if "thinking" in claude_request:
        thinking_enabled = True
        del openai_request["thinking"]
    
    # 如果启用思考，注入提示到 system prompt
    if thinking_enabled:
        thinking_system = THINKING_HINT
        if system_content:
            thinking_system = THINKING_HINT + "\n\n" + system_content
        # 添加到 messages 开头
```

#### 阶段 2：历史消息转换

将历史消息中的 Claude thinking 块转换为 `<thinking>` 标签格式：

```python
def _convert_content_to_openai(content) -> str:
    # 处理 thinking 类型的内容块
    if block.get("type") == "thinking":
        text_parts.append(f"<thinking>{block.get('thinking', '')}</thinking>")
```

#### 阶段 3：响应流转换（解析思考标签）

在 `OpenAIStreamState` 类中实现流式解析：

```python
class OpenAIStreamState:
    def __init__(self):
        self.thinking_buffer = ""      # 思考内容缓冲
        self.in_thinking = False       # 是否在思考块中
        self.thinking_emitted = False  # 是否已发送思考块
        self.pending_text = ""         # 待处理文本
```

解析逻辑：
1. 检测 `<thinking>` 开始标签 → 进入思考模式
2. 收集思考内容到 buffer
3. 检测 `</thinking>` 结束标签 → 发送 `thinking` content block
4. 后续内容作为普通 `text` content block 发送

### 使用方式

在 Claude Code 或其他客户端中正常启用 thinking 模式即可，custom_api 会自动处理转换。

---

## 2. 缓存模拟功能

### 实现位置

- `main.py`: `create_custom_api_message` 端点中的缓存提取逻辑
- `custom_api/handler.py`: 传递缓存参数
- `custom_api/converter.py`: 在 SSE 事件中包含缓存统计

### 工作原理

1. 从请求中提取带有 `cache_control: {"type": "ephemeral"}` 标记的内容
2. 计算缓存创建和读取的 token 数
3. 在响应的 `message_start` 和 `message_stop` 事件中返回缓存统计

```python
# OpenAIStreamState 中的缓存字段
self.cache_creation_input_tokens = 0
self.cache_read_input_tokens = 0
```

---

## 3. Token 统计功能

### 实现位置

- `custom_api/handler.py`: `handle_openai_format_stream` 和 `handle_claude_format_stream`
- `usage_tracker.py`: 统一的 token 记录模块

### 记录方式

```python
from usage_tracker import record_token_usage

# 在流结束时记录
record_token_usage(
    channel="custom_api",
    input_tokens=input_tokens,
    output_tokens=output_tokens
)
```

使用 `channel="custom_api"` 区分于其他渠道（如 Amazon Q）。

---

## 4. 其他更新

### API Base URL 自动补全

在 `custom_api/handler.py` 中，自动为 API Base URL 添加 `/v1` 前缀：

```python
if not api_base.rstrip('/').endswith('/v1'):
    api_base = api_base.rstrip('/') + '/v1'
```

### 遥测端点

在 `main.py` 中添加静默端点处理 Claude Code 遥测请求：

```python
@app.post("/api/event_logging/batch")
async def event_logging_batch():
    return {"status": "ok"}
```

### 缓存配置

`.env.example` 中新增配置项：

```env
# Prompt Caching
ENABLE_CACHE_SIMULATION=false
CACHE_TTL_SECONDS=300
MAX_CACHE_ENTRIES=1000
ZERO_INPUT_TOKEN_MODELS=
```

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `custom_api/converter.py` | 请求/响应转换，thinking 模式核心实现 |
| `custom_api/handler.py` | 请求处理，token 统计，缓存参数传递 |
| `main.py` | API 端点，缓存模拟逻辑 |
| `usage_tracker.py` | Token 使用记录 |
| `.env.example` | 配置示例 |

---

## 测试

所有 60 个测试用例通过：

```bash
python -m pytest --tb=short -q
# 60 passed
```
