# Token 统计实现方案

## 概述

本方案使用 `tiktoken` 库在本地进行 token 近似统计，返回符合 Claude/OpenAI API 标准格式的 usage 数据。

## 依赖安装

```bash
pip install tiktoken
```

## 核心实现

### 1. Token 计数函数

```python
import tiktoken

# 初始化 tokenizer (cl100k_base 用于 GPT-4/3.5)
try:
    ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:
    ENCODING = None

# 可选：从环境变量读取乘数，用于调整计费
TOKEN_COUNT_MULTIPLIER = float(os.getenv("TOKEN_COUNT_MULTIPLIER", "1.0"))

def count_tokens(text: str, apply_multiplier: bool = False) -> int:
    """使用 tiktoken 统计 token 数量"""
    if not text or not ENCODING:
        return 0
    token_count = len(ENCODING.encode(text))
    if apply_multiplier:
        token_count = int(token_count * TOKEN_COUNT_MULTIPLIER)
    return token_count
```

### 2. Input Tokens 统计

在请求处理时统计输入 token：

```python
def calculate_input_tokens(request) -> int:
    text_to_count = ""
    
    # 1. System prompt
    if request.system:
        if isinstance(request.system, str):
            text_to_count += request.system
        elif isinstance(request.system, list):
            for item in request.system:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_to_count += item.get("text", "")
    
    # 2. Messages
    for msg in request.messages:
        if isinstance(msg.content, str):
            text_to_count += msg.content
        elif isinstance(msg.content, list):
            for item in msg.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_to_count += item.get("text", "")
    
    # 3. Tools (可选)
    if request.tools:
        text_to_count += json.dumps([t.model_dump() for t in request.tools], ensure_ascii=False)
    
    return count_tokens(text_to_count, apply_multiplier=True)
```

### 3. Output Tokens 统计

在流式响应结束时统计输出 token：

```python
class StreamHandler:
    def __init__(self, input_tokens: int = 0):
        self.input_tokens = input_tokens
        self.response_buffer = []      # 文本响应
        self.tool_input_buffer = []    # 工具调用输入
    
    def on_text_chunk(self, text: str):
        self.response_buffer.append(text)
    
    def on_tool_input(self, input_json: str):
        self.tool_input_buffer.append(input_json)
    
    def get_output_tokens(self) -> int:
        full_text = "".join(self.response_buffer)
        full_tool_input = "".join(self.tool_input_buffer)
        return count_tokens(full_text) + count_tokens(full_tool_input)
```

## 返回格式

### Claude API 格式 (SSE 流)

```python
def build_message_start(conversation_id: str, model: str, input_tokens: int) -> str:
    data = {
        "type": "message_start",
        "message": {
            "id": conversation_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": 0}
        }
    }
    return f"event: message_start\ndata: {json.dumps(data)}\n\n"

def build_message_delta(output_tokens: int, stop_reason: str = "end_turn") -> str:
    data = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": output_tokens}
    }
    return f"event: message_delta\ndata: {json.dumps(data)}\n\n"
```

### OpenAI API 格式

```python
def build_openai_usage(prompt_tokens: int, completion_tokens: int) -> dict:
    return {
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    }
```

## Token 计数 API 端点

提供独立的 token 计数接口：

```python
@app.post("/v1/messages/count_tokens")
async def count_tokens_endpoint(req: ClaudeRequest):
    """兼容 Claude API 的 token 计数端点"""
    text_to_count = ""
    
    # 统计 system
    if req.system:
        if isinstance(req.system, str):
            text_to_count += req.system
        elif isinstance(req.system, list):
            for item in req.system:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_to_count += item.get("text", "")
    
    # 统计 messages
    for msg in req.messages:
        if isinstance(msg.content, str):
            text_to_count += msg.content
        elif isinstance(msg.content, list):
            for item in msg.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_to_count += item.get("text", "")
    
    # 统计 tools
    if req.tools:
        text_to_count += json.dumps([t.model_dump() for t in req.tools], ensure_ascii=False)
    
    input_tokens = count_tokens(text_to_count, apply_multiplier=True)
    return {"input_tokens": input_tokens}
```

## 注意事项

### 精确度

| 方面 | 说明 |
|------|------|
| Tokenizer | 使用 OpenAI 的 cl100k_base，与 Claude 实际 tokenizer 有差异 |
| 误差范围 | 约 10-20%，对于计费参考和限流控制足够 |
| 未统计项 | 特殊 token（消息边界、角色标记等）未计入 |

### 环境变量

```bash
# 可选：token 数量乘数，用于调整计费
TOKEN_COUNT_MULTIPLIER=1.0
```

### 性能考虑

- tiktoken 是本地计算，无网络开销
- 对于长文本，encoding 操作有一定 CPU 开销
- 建议在流结束时一次性统计，而非每个 chunk 都统计

---

## 关于 Claude Code / ccline 的 Token 统计

Claude Code 等客户端显示的 token 统计**直接来自 API 响应中的 usage 字段**，而不是客户端自己计算的。

工作流程：
1. 客户端发送请求到 API
2. API 返回响应，包含 `usage.input_tokens` 和 `usage.output_tokens`
3. 客户端读取并显示这些数值

所以：
- 如果你的代理服务正确返回 usage 字段，Claude Code 就能显示统计
- 本方案的实现会让 Claude Code 正常显示 token 用量
- 显示的数值是本方案计算的近似值，不是 Claude 官方的精确值
