# Design Document: Custom API Account Support

## Overview

本设计为 Claude API 代理服务添加自定义 API 账号支持。用户可以配置第三方 API（OpenAI 或 Claude 格式），使其参与负载均衡。核心挑战是实现 Claude ↔ OpenAI 格式的双向转换，包括消息、工具调用和流式响应。

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code Client                        │
│                    (Claude API Format Request)                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         main.py Router                           │
│                    (Smart Channel Selection)                     │
└─────────────────────────────────────────────────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │   Amazon Q    │   │    Gemini     │   │  Custom API   │
    │   Handler     │   │   Handler     │   │   Handler     │
    └───────────────┘   └───────────────┘   └───────────────┘
                                                    │
                                    ┌───────────────┴───────────────┐
                                    ▼                               ▼
                            ┌───────────────┐               ┌───────────────┐
                            │ Claude Format │               │ OpenAI Format │
                            │  (Passthrough)│               │  (Convert)    │
                            └───────────────┘               └───────────────┘
```

## Components and Interfaces

### 1. Account Manager Extension (`account_manager.py`)

扩展现有账号管理模块，支持 `custom_api` 类型。

```python
# 新增账号类型
ACCOUNT_TYPES = ["amazonq", "gemini", "custom_api"]

# custom_api 账号字段映射
# - label: 账号标签
# - clientId: 不使用，可为空
# - clientSecret: API Key
# - refreshToken: 不使用
# - accessToken: 不使用
# - other: {
#     "api_base": "https://api.openai.com/v1",
#     "model": "gpt-4o",
#     "format": "openai" | "claude"
#   }
```

### 2. Custom API Converter (`custom_api/converter.py`)

负责 Claude ↔ OpenAI 格式转换。

```python
# Claude → OpenAI 请求转换
def convert_claude_to_openai(claude_req: ClaudeRequest) -> Dict[str, Any]:
    """将 Claude 请求转换为 OpenAI 格式"""
    pass

# OpenAI → Claude 响应转换
def convert_openai_delta_to_claude(openai_event: Dict) -> List[str]:
    """将 OpenAI SSE 事件转换为 Claude SSE 事件"""
    pass
```

### 3. Custom API Handler (`custom_api/handler.py`)

处理自定义 API 的请求和响应流。

```python
async def handle_custom_api_stream(
    account: Dict[str, Any],
    claude_req: ClaudeRequest,
    request_data: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """处理自定义 API 的流式响应"""
    pass
```

### 4. Router Extension (`main.py`)

扩展路由逻辑，支持 custom_api 渠道。

```python
def get_random_channel_by_model(model: str) -> Optional[str]:
    """根据模型选择渠道，包含 custom_api"""
    # 现有逻辑 + custom_api 支持
    pass
```

## Data Models

### Custom API Account Schema

```python
{
    "id": "uuid",
    "type": "custom_api",
    "label": "My OpenAI Account",
    "clientId": "",  # 不使用
    "clientSecret": "sk-xxx",  # API Key
    "refreshToken": None,
    "accessToken": None,
    "other": {
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "format": "openai"  # or "claude"
    },
    "enabled": True
}
```

### Claude → OpenAI Message Conversion

| Claude Format | OpenAI Format |
|--------------|---------------|
| `{"role": "user", "content": "text"}` | `{"role": "user", "content": "text"}` |
| `{"role": "user", "content": [{"type": "text", "text": "..."}]}` | `{"role": "user", "content": "..."}` |
| `{"role": "assistant", "content": [{"type": "tool_use", ...}]}` | `{"role": "assistant", "tool_calls": [...]}` |
| `{"role": "user", "content": [{"type": "tool_result", ...}]}` | `{"role": "tool", "tool_call_id": "...", "content": "..."}` |

### Claude → OpenAI Tool Conversion

| Claude Tool | OpenAI Function |
|------------|-----------------|
| `name` | `name` |
| `description` | `description` |
| `input_schema` | `parameters` |

### OpenAI → Claude SSE Event Conversion

| OpenAI Event | Claude Event |
|-------------|--------------|
| `data: {"choices": [{"delta": {"content": "..."}}]}` | `event: content_block_delta\ndata: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "..."}}` |
| `data: {"choices": [{"delta": {"tool_calls": [...]}}]}` | `event: content_block_start\ndata: {"type": "content_block_start", "content_block": {"type": "tool_use", ...}}` |
| `data: [DONE]` | `event: message_stop\ndata: {"type": "message_stop"}` |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following properties have been identified after removing redundancies:

### Property 1: Account Creation Persistence
*For any* valid custom API account data (label, apiBase, apiKey, model, format), after creation, querying the database should return an account with type "custom_api" and all fields matching the input.
**Validates: Requirements 1.2**

### Property 2: Account Update Persistence
*For any* existing custom API account and valid update data, after update, the account should reflect all changes correctly.
**Validates: Requirements 1.4**

### Property 3: Account Deletion
*For any* existing custom API account, after deletion, querying by ID should return None.
**Validates: Requirements 1.5**

### Property 4: Load Balancing Inclusion
*For any* set of enabled accounts including at least one custom_api account, repeated channel selection should eventually return "custom_api".
**Validates: Requirements 2.1**

### Property 5: Disabled Account Exclusion
*For any* disabled custom_api account, it should never be selected by the load balancer.
**Validates: Requirements 2.3**

### Property 6: Claude to OpenAI Message Conversion
*For any* valid Claude message (text, content blocks, tool_use, tool_result), the conversion to OpenAI format should produce a structurally valid OpenAI message.
**Validates: Requirements 3.2, 3.4, 3.5**

### Property 7: Claude to OpenAI Tool Conversion
*For any* valid Claude tool definition, the conversion should produce a valid OpenAI function definition with matching name, description, and parameters.
**Validates: Requirements 3.3**

### Property 8: OpenAI to Claude Delta Conversion
*For any* valid OpenAI streaming delta (text or tool_calls), the conversion should produce valid Claude SSE events.
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 9: Usage Statistics Conversion
*For any* valid OpenAI usage object, the conversion should produce a valid Claude usage object with correct token counts.
**Validates: Requirements 4.4**

### Property 10: Claude Format Passthrough
*For any* request routed to a custom API with format "claude", the request should be forwarded without modification (except for API key header).
**Validates: Requirements 3.6, 4.5**

### Property 11: Tool ID Preservation
*For any* sequence of tool calls and results, the tool_use_id/tool_call_id mapping should be preserved correctly through conversion.
**Validates: Requirements 5.4**

### Property 12: Error Format Conversion
*For any* OpenAI error response, the conversion should produce a valid Claude API error format.
**Validates: Requirements 7.1**

## Error Handling

### API Errors
- OpenAI 4xx errors → Convert to Claude error format with appropriate status code
- OpenAI 5xx errors → Return 502 with upstream error details
- Connection timeout → Return 502 with timeout message
- Connection refused → Return 502 with unreachable message

### Conversion Errors
- Invalid message format → Log warning, attempt best-effort conversion
- Unknown tool format → Skip tool, log error
- Malformed SSE → Skip event, continue stream

## Testing Strategy

### Dual Testing Approach

本功能采用单元测试和属性测试相结合的方式：

1. **单元测试** - 验证具体示例和边界情况
2. **属性测试** - 验证转换逻辑的通用正确性

### Property-Based Testing Library

使用 **Hypothesis** 作为 Python 属性测试库。

```python
from hypothesis import given, strategies as st

@given(st.text())
def test_message_conversion_preserves_content(text):
    """Property 6: Message content should be preserved through conversion"""
    claude_msg = {"role": "user", "content": text}
    openai_msg = convert_claude_message_to_openai(claude_msg)
    assert openai_msg["content"] == text
```

### Test Categories

1. **Converter Tests** (`tests/test_custom_api_converter.py`)
   - Message format conversion (Property 6)
   - Tool definition conversion (Property 7)
   - SSE event conversion (Property 8)
   - Usage conversion (Property 9)
   - Error conversion (Property 12)

2. **Account Manager Tests** (`tests/test_account_manager.py`)
   - Account CRUD operations (Properties 1, 2, 3)
   - Load balancing logic (Properties 4, 5)

3. **Integration Tests** (`tests/test_custom_api_integration.py`)
   - End-to-end request flow
   - Tool call sequences (Property 11)
   - Passthrough mode (Property 10)

### Test Configuration

```python
# pytest.ini or conftest.py
# Hypothesis settings: minimum 100 iterations per property test
from hypothesis import settings
settings.register_profile("ci", max_examples=100)
```
