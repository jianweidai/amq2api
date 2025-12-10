"""
Custom API 格式转换器
- 将 Claude API 格式转换为 OpenAI API 格式 (请求)
- 将 OpenAI API 格式转换为 Claude API 格式 (响应)
"""
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Union, AsyncIterator, Tuple

from models import ClaudeRequest, ClaudeTool

logger = logging.getLogger(__name__)

# Thinking 模式相关常量
THINKING_START_TAG = "<thinking>"
THINKING_END_TAG = "</thinking>"
THINKING_HINT = "<thinking_mode>interleaved</thinking_mode><max_thinking_length>16000</max_thinking_length>"


# ============================================================================
# OpenAI → Claude 响应转换
# ============================================================================

class OpenAIStreamState:
    """OpenAI 流式响应状态管理"""
    
    def __init__(self, model: str = "claude-sonnet-4.5", request_id: Optional[str] = None, thinking_enabled: bool = False):
        self.model = model
        self.request_id = request_id or f"msg_{uuid.uuid4().hex[:24]}"
        self.content_block_index = -1
        self.current_tool_call_index = -1
        self.tool_calls: Dict[int, Dict[str, Any]] = {}  # index -> tool call info
        self.message_started = False
        self.content_block_started = False
        self.input_tokens = 0
        self.output_tokens = 0
        self.finish_reason: Optional[str] = None
        # 缓存统计
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0
        # Thinking 模式支持
        self.thinking_enabled = thinking_enabled
        self.in_thinking_block = False
        self.thinking_buffer = ""
        self.current_block_type: Optional[str] = None  # "text" or "thinking"


async def convert_openai_stream_to_claude(
    openai_stream: AsyncIterator[bytes],
    model: str = "claude-sonnet-4.5",
    input_tokens: int = 0,
    thinking_enabled: bool = False,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> AsyncIterator[str]:
    """
    将 OpenAI SSE 流转换为 Claude SSE 流
    
    Args:
        openai_stream: OpenAI SSE 字节流
        model: 模型名称
        input_tokens: 输入 token 数量
        thinking_enabled: 是否启用 thinking 模式
        cache_creation_input_tokens: 缓存创建 token 数
        cache_read_input_tokens: 缓存读取 token 数
    
    Yields:
        str: Claude 格式的 SSE 事件
    """
    state = OpenAIStreamState(model=model, thinking_enabled=thinking_enabled)
    state.input_tokens = input_tokens
    state.cache_creation_input_tokens = cache_creation_input_tokens
    state.cache_read_input_tokens = cache_read_input_tokens
    buffer = ""
    
    try:
        async for chunk in openai_stream:
            # 解码字节流
            try:
                text = chunk.decode('utf-8')
            except UnicodeDecodeError:
                logger.warning("Failed to decode chunk as UTF-8")
                continue
            
            buffer += text
            
            # 按行处理 SSE 事件
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith(':'):
                    continue
                
                # 解析 data: 行
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    
                    # 检查流结束标记
                    if data_str == '[DONE]':
                        # 关闭当前内容块
                        if state.content_block_started:
                            yield _build_content_block_stop(state.content_block_index)
                            state.content_block_started = False
                        
                        # 发送 message_delta 和 message_stop
                        yield _build_message_stop(
                            state.input_tokens,
                            state.output_tokens,
                            state.finish_reason,
                            state.cache_creation_input_tokens,
                            state.cache_read_input_tokens
                        )
                        return
                    
                    # 解析 JSON 数据
                    try:
                        openai_event = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse OpenAI event: {data_str}")
                        continue
                    
                    # 转换事件
                    for claude_event in convert_openai_delta_to_claude_events(openai_event, state):
                        yield claude_event
        
        # 处理剩余的 buffer
        if buffer.strip():
            line = buffer.strip()
            if line.startswith('data:'):
                data_str = line[5:].strip()
                if data_str != '[DONE]':
                    try:
                        openai_event = json.loads(data_str)
                        for claude_event in convert_openai_delta_to_claude_events(openai_event, state):
                            yield claude_event
                    except json.JSONDecodeError:
                        pass
        
        # 确保流正确结束
        if state.content_block_started:
            yield _build_content_block_stop(state.content_block_index)
        
        if state.message_started:
            yield _build_message_stop(
                state.input_tokens,
                state.output_tokens,
                state.finish_reason,
                state.cache_creation_input_tokens,
                state.cache_read_input_tokens
            )
    
    except Exception as e:
        logger.error(f"Error converting OpenAI stream: {e}", exc_info=True)
        raise


def convert_openai_delta_to_claude_events(
    openai_event: Dict[str, Any],
    state: OpenAIStreamState
) -> List[str]:
    """
    将 OpenAI delta 事件转换为 Claude SSE 事件列表
    
    Args:
        openai_event: OpenAI 流式事件
        state: 流状态管理器
    
    Returns:
        List[str]: Claude SSE 事件列表
    """
    events: List[str] = []
    
    # 发送 message_start (仅一次)
    if not state.message_started:
        events.append(_build_message_start(
            state.request_id,
            state.model,
            state.input_tokens,
            state.cache_creation_input_tokens,
            state.cache_read_input_tokens
        ))
        events.append(_build_ping())
        state.message_started = True
    
    # 提取 choices
    choices = openai_event.get('choices', [])
    if not choices:
        # 检查是否有 usage 信息
        usage = openai_event.get('usage')
        if usage:
            claude_usage = convert_openai_usage_to_claude(usage)
            state.input_tokens = claude_usage.get('input_tokens', state.input_tokens)
            state.output_tokens = claude_usage.get('output_tokens', state.output_tokens)
        return events
    
    choice = choices[0]
    delta = choice.get('delta', {})
    finish_reason = choice.get('finish_reason')
    
    if finish_reason:
        state.finish_reason = _convert_finish_reason(finish_reason)
    
    # 处理文本内容
    content = delta.get('content')
    if content:
        # 如果当前有 tool call 块，先关闭它
        if state.current_tool_call_index >= 0 and state.content_block_started:
            events.append(_build_content_block_stop(state.content_block_index))
            state.content_block_started = False
            state.current_tool_call_index = -1
        
        # 如果启用了 thinking 模式，解析 <thinking> 标签
        if state.thinking_enabled:
            thinking_events = _process_thinking_content(content, state)
            events.extend(thinking_events)
        else:
            # 普通模式：直接作为文本处理
            # 开始新的文本块
            if not state.content_block_started or state.current_tool_call_index >= 0:
                state.content_block_index += 1
                events.append(_build_content_block_start(state.content_block_index, "text"))
                state.content_block_started = True
                state.current_tool_call_index = -1
                state.current_block_type = "text"
            
            # 发送文本 delta
            events.append(_build_text_delta(state.content_block_index, content))
    
    # 处理 tool_calls
    tool_calls = delta.get('tool_calls', [])
    for tc in tool_calls:
        tc_index = tc.get('index', 0)
        tc_id = tc.get('id')
        tc_function = tc.get('function', {})
        tc_name = tc_function.get('name')
        tc_arguments = tc_function.get('arguments', '')
        
        # 检查是否是新的 tool call
        if tc_id or tc_name:
            # 关闭之前的内容块
            if state.content_block_started:
                events.append(_build_content_block_stop(state.content_block_index))
                state.content_block_started = False
            
            # 初始化新的 tool call
            state.content_block_index += 1
            state.current_tool_call_index = tc_index
            
            # Tool ID Preservation: Use the OpenAI tool_call.id directly if provided
            # This ensures the ID returned to Claude Code matches what the backend sent
            # If no ID is provided (some providers may not include it), generate a Claude-style ID
            # This is critical for Requirements 5.1 and 5.4
            tool_use_id = tc_id or f"toolu_{uuid.uuid4().hex[:24]}"
            state.tool_calls[tc_index] = {
                'id': tool_use_id,
                'name': tc_name or '',
                'arguments': ''
            }
            
            # 发送 tool_use content_block_start
            events.append(_build_tool_use_start(
                state.content_block_index,
                tool_use_id,
                tc_name or ''
            ))
            state.content_block_started = True
        
        # 累积 arguments
        if tc_arguments and tc_index in state.tool_calls:
            state.tool_calls[tc_index]['arguments'] += tc_arguments
            # 发送 input_json_delta
            events.append(_build_tool_use_delta(state.content_block_index, tc_arguments))
    
    # 处理 usage (如果在 choice 中)
    usage = openai_event.get('usage')
    if usage:
        claude_usage = convert_openai_usage_to_claude(usage)
        state.input_tokens = claude_usage.get('input_tokens', state.input_tokens)
        state.output_tokens = claude_usage.get('output_tokens', state.output_tokens)
    
    return events


def convert_openai_usage_to_claude(openai_usage: Dict[str, Any]) -> Dict[str, int]:
    """
    将 OpenAI usage 转换为 Claude usage 格式
    
    Args:
        openai_usage: OpenAI usage 对象
            {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
    
    Returns:
        Dict[str, int]: Claude usage 对象
            {
                "input_tokens": 10,
                "output_tokens": 20
            }
    """
    return {
        "input_tokens": openai_usage.get("prompt_tokens", 0),
        "output_tokens": openai_usage.get("completion_tokens", 0)
    }


def convert_openai_error_to_claude(
    openai_error: Dict[str, Any],
    status_code: int = 500
) -> Dict[str, Any]:
    """
    将 OpenAI 错误格式转换为 Claude 错误格式
    
    Args:
        openai_error: OpenAI 错误对象
            {
                "error": {
                    "message": "...",
                    "type": "...",
                    "code": "..."
                }
            }
        status_code: HTTP 状态码
    
    Returns:
        Dict[str, Any]: Claude 错误对象
            {
                "type": "error",
                "error": {
                    "type": "...",
                    "message": "..."
                }
            }
    """
    error_data = openai_error.get('error', {})
    
    # 映射 OpenAI 错误类型到 Claude 错误类型
    openai_type = error_data.get('type', '')
    openai_code = error_data.get('code', '')
    message = error_data.get('message', 'Unknown error')
    
    # 错误类型映射
    error_type_map = {
        'invalid_request_error': 'invalid_request_error',
        'authentication_error': 'authentication_error',
        'permission_error': 'permission_error',
        'not_found_error': 'not_found_error',
        'rate_limit_error': 'rate_limit_error',
        'server_error': 'api_error',
        'service_unavailable': 'overloaded_error',
    }
    
    # 根据状态码推断错误类型
    status_type_map = {
        400: 'invalid_request_error',
        401: 'authentication_error',
        403: 'permission_error',
        404: 'not_found_error',
        429: 'rate_limit_error',
        500: 'api_error',
        502: 'api_error',
        503: 'overloaded_error',
    }
    
    claude_type = error_type_map.get(openai_type) or \
                  error_type_map.get(openai_code) or \
                  status_type_map.get(status_code, 'api_error')
    
    return {
        "type": "error",
        "error": {
            "type": claude_type,
            "message": message
        }
    }


# ============================================================================
# Claude SSE 事件构建辅助函数
# ============================================================================

def _build_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """构建 SSE 事件字符串"""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


def _build_message_start(
    request_id: str,
    model: str,
    input_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> str:
    """构建 message_start 事件"""
    data = {
        "type": "message_start",
        "message": {
            "id": request_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 0,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens
            }
        }
    }
    return _build_sse_event("message_start", data)


def _build_ping() -> str:
    """构建 ping 事件"""
    return _build_sse_event("ping", {"type": "ping"})


def _build_content_block_start(index: int, content_type: str) -> str:
    """构建 content_block_start 事件"""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": content_type, content_type: ""}
    }
    return _build_sse_event("content_block_start", data)


def _build_text_delta(index: int, text: str) -> str:
    """构建文本 content_block_delta 事件"""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "text_delta", "text": text}
    }
    return _build_sse_event("content_block_delta", data)


def _build_content_block_stop(index: int) -> str:
    """构建 content_block_stop 事件"""
    data = {
        "type": "content_block_stop",
        "index": index
    }
    return _build_sse_event("content_block_stop", data)


def _build_tool_use_start(index: int, tool_use_id: str, name: str) -> str:
    """构建 tool_use content_block_start 事件"""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {
            "type": "tool_use",
            "id": tool_use_id,
            "name": name
        }
    }
    return _build_sse_event("content_block_start", data)


def _build_tool_use_delta(index: int, partial_json: str) -> str:
    """构建 tool_use input_json_delta 事件"""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {
            "type": "input_json_delta",
            "partial_json": partial_json
        }
    }
    return _build_sse_event("content_block_delta", data)


def _build_message_stop(
    input_tokens: int,
    output_tokens: int,
    stop_reason: Optional[str],
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> str:
    """构建 message_delta 和 message_stop 事件"""
    # message_delta
    delta_data = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason or "end_turn", "stop_sequence": None},
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens
        }
    }
    delta_event = _build_sse_event("message_delta", delta_data)
    
    # message_stop
    stop_data = {"type": "message_stop"}
    stop_event = _build_sse_event("message_stop", stop_data)
    
    return delta_event + stop_event


def _convert_finish_reason(openai_reason: str) -> str:
    """将 OpenAI finish_reason 转换为 Claude stop_reason"""
    reason_map = {
        'stop': 'end_turn',
        'length': 'max_tokens',
        'tool_calls': 'tool_use',
        'content_filter': 'end_turn',
        'function_call': 'tool_use',
    }
    return reason_map.get(openai_reason, 'end_turn')


def _process_thinking_content(content: str, state: OpenAIStreamState) -> List[str]:
    """
    处理可能包含 <thinking> 标签的内容
    
    解析流式内容中的 <thinking>...</thinking> 标签，
    将其转换为 Claude thinking 内容块。
    
    Args:
        content: 流式文本内容
        state: 流状态管理器
    
    Returns:
        List[str]: Claude SSE 事件列表
    """
    events: List[str] = []
    
    # 将内容添加到缓冲区进行解析
    state.thinking_buffer += content
    
    while True:
        if state.in_thinking_block:
            # 当前在 thinking 块中，查找结束标签
            end_idx = state.thinking_buffer.find(THINKING_END_TAG)
            if end_idx != -1:
                # 找到结束标签
                thinking_content = state.thinking_buffer[:end_idx]
                state.thinking_buffer = state.thinking_buffer[end_idx + len(THINKING_END_TAG):]
                
                # 发送 thinking 内容
                if thinking_content:
                    events.append(_build_thinking_delta(state.content_block_index, thinking_content))
                
                # 关闭 thinking 块
                events.append(_build_content_block_stop(state.content_block_index))
                state.content_block_started = False
                state.in_thinking_block = False
                state.current_block_type = None
            else:
                # 没有找到结束标签，发送当前缓冲区内容
                if state.thinking_buffer:
                    events.append(_build_thinking_delta(state.content_block_index, state.thinking_buffer))
                    state.thinking_buffer = ""
                break
        else:
            # 当前不在 thinking 块中，查找开始标签
            start_idx = state.thinking_buffer.find(THINKING_START_TAG)
            if start_idx != -1:
                # 找到开始标签
                # 先处理开始标签之前的普通文本
                text_before = state.thinking_buffer[:start_idx]
                state.thinking_buffer = state.thinking_buffer[start_idx + len(THINKING_START_TAG):]
                
                if text_before:
                    # 发送普通文本
                    if not state.content_block_started or state.current_block_type != "text":
                        if state.content_block_started:
                            events.append(_build_content_block_stop(state.content_block_index))
                        state.content_block_index += 1
                        events.append(_build_content_block_start(state.content_block_index, "text"))
                        state.content_block_started = True
                        state.current_block_type = "text"
                    events.append(_build_text_delta(state.content_block_index, text_before))
                
                # 关闭当前文本块（如果有）
                if state.content_block_started and state.current_block_type == "text":
                    events.append(_build_content_block_stop(state.content_block_index))
                    state.content_block_started = False
                
                # 开始新的 thinking 块
                state.content_block_index += 1
                events.append(_build_thinking_start(state.content_block_index))
                state.content_block_started = True
                state.in_thinking_block = True
                state.current_block_type = "thinking"
            else:
                # 没有找到开始标签
                # 检查缓冲区末尾是否可能是不完整的标签
                potential_tag_start = -1
                for i in range(1, len(THINKING_START_TAG)):
                    if state.thinking_buffer.endswith(THINKING_START_TAG[:i]):
                        potential_tag_start = len(state.thinking_buffer) - i
                        break
                
                if potential_tag_start >= 0:
                    # 可能是不完整的标签，保留这部分
                    text_to_send = state.thinking_buffer[:potential_tag_start]
                    state.thinking_buffer = state.thinking_buffer[potential_tag_start:]
                else:
                    # 发送全部内容
                    text_to_send = state.thinking_buffer
                    state.thinking_buffer = ""
                
                if text_to_send:
                    # 发送普通文本
                    if not state.content_block_started or state.current_block_type != "text":
                        if state.content_block_started:
                            events.append(_build_content_block_stop(state.content_block_index))
                        state.content_block_index += 1
                        events.append(_build_content_block_start(state.content_block_index, "text"))
                        state.content_block_started = True
                        state.current_block_type = "text"
                    events.append(_build_text_delta(state.content_block_index, text_to_send))
                break
    
    return events


def _build_thinking_start(index: int) -> str:
    """构建 thinking content_block_start 事件"""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {
            "type": "thinking",
            "thinking": ""
        }
    }
    return _build_sse_event("content_block_start", data)


def _build_thinking_delta(index: int, thinking: str) -> str:
    """构建 thinking content_block_delta 事件"""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {
            "type": "thinking_delta",
            "thinking": thinking
        }
    }
    return _build_sse_event("content_block_delta", data)


def convert_claude_to_openai_request(claude_req: ClaudeRequest, model: str) -> Tuple[Dict[str, Any], bool]:
    """
    将 Claude API 请求转换为 OpenAI chat completion 格式

    Args:
        claude_req: Claude 请求对象
        model: 目标 OpenAI 模型名称

    Returns:
        Tuple[Dict[str, Any], bool]: (OpenAI chat completion 请求字典, thinking_enabled)
    """
    openai_request: Dict[str, Any] = {
        "model": model,
        "messages": [],
        "stream": claude_req.stream,
    }

    # 检测是否启用 thinking 模式
    thinking_enabled = _is_thinking_enabled(claude_req)

    # 处理 system prompt
    system_content = ""
    if claude_req.system:
        system_content = _extract_system_content(claude_req.system)
    
    # 如果启用 thinking，在 system prompt 末尾添加 thinking 提示
    if thinking_enabled:
        if system_content:
            system_content = f"{system_content}\n{THINKING_HINT}"
        else:
            system_content = THINKING_HINT
    
    if system_content:
        openai_request["messages"].append({
            "role": "system",
            "content": system_content
        })

    # 转换消息（包括历史中的 thinking 块）
    openai_messages = convert_claude_messages_to_openai(claude_req.messages, thinking_enabled)
    openai_request["messages"].extend(openai_messages)

    # 设置 max_tokens
    if claude_req.max_tokens:
        openai_request["max_tokens"] = claude_req.max_tokens

    # 设置 temperature
    if claude_req.temperature is not None:
        openai_request["temperature"] = claude_req.temperature

    # 转换工具定义
    if claude_req.tools:
        openai_tools = convert_claude_tools_to_openai(claude_req.tools)
        if openai_tools:
            openai_request["tools"] = openai_tools

    return openai_request, thinking_enabled


def _is_thinking_enabled(claude_req: ClaudeRequest) -> bool:
    """
    检测请求是否启用了 thinking 模式
    
    Args:
        claude_req: Claude 请求对象
    
    Returns:
        bool: 是否启用 thinking
    """
    thinking_param = getattr(claude_req, 'thinking', None)
    if thinking_param:
        if isinstance(thinking_param, bool):
            return thinking_param
        elif isinstance(thinking_param, dict):
            return thinking_param.get('type') == 'enabled' or thinking_param.get('enabled', False)
    return False



def _extract_system_content(system: Union[str, List[Dict[str, Any]]]) -> str:
    """
    从 Claude system 字段提取文本内容

    Args:
        system: Claude system 字段，可以是字符串或内容块列表

    Returns:
        提取的系统提示文本
    """
    if isinstance(system, str):
        return system
    elif isinstance(system, list):
        text_parts = []
        for item in system:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "\n".join(text_parts)
    return ""


def convert_claude_messages_to_openai(messages: List[Any], thinking_enabled: bool = False) -> List[Dict[str, Any]]:
    """
    将 Claude 消息列表转换为 OpenAI 消息格式

    支持转换:
    - 文本消息 (string 和 content blocks)
    - tool_use 转换为 tool_calls
    - tool_result 转换为 tool messages
    - thinking 块转换为 <thinking> 标签包裹的文本

    Args:
        messages: Claude 消息列表
        thinking_enabled: 是否启用 thinking 模式

    Returns:
        OpenAI 消息列表
    """
    openai_messages: List[Dict[str, Any]] = []

    for msg in messages:
        role = msg.role
        content = msg.content

        if role == "user":
            # 处理用户消息
            user_messages = _convert_user_message(content)
            openai_messages.extend(user_messages)
        elif role == "assistant":
            # 处理助手消息
            assistant_msg = _convert_assistant_message(content, thinking_enabled)
            if assistant_msg:
                openai_messages.append(assistant_msg)

    return openai_messages


def _convert_user_message(content: Union[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    转换用户消息

    Args:
        content: Claude 用户消息内容

    Returns:
        OpenAI 消息列表 (可能包含 user 消息和 tool 消息)
    """
    messages: List[Dict[str, Any]] = []

    if isinstance(content, str):
        # 简单字符串内容
        messages.append({
            "role": "user",
            "content": content
        })
    elif isinstance(content, list):
        # 内容块列表
        text_parts: List[str] = []
        tool_results: List[Dict[str, Any]] = []

        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")

                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_result":
                    # 转换 tool_result 为 OpenAI tool message
                    tool_msg = _convert_tool_result_to_openai(block)
                    if tool_msg:
                        tool_results.append(tool_msg)
                elif block_type == "image":
                    # OpenAI 图片格式转换
                    image_content = _convert_image_block(block)
                    if image_content:
                        # 图片需要作为多模态内容处理
                        messages.append({
                            "role": "user",
                            "content": [image_content]
                        })
            elif isinstance(block, str):
                text_parts.append(block)

        # 先添加 tool results (它们需要在用户文本之前)
        messages.extend(tool_results)

        # 添加文本内容
        if text_parts:
            combined_text = "\n".join(text_parts)
            if combined_text.strip():
                messages.append({
                    "role": "user",
                    "content": combined_text
                })

    return messages



def _convert_tool_result_to_openai(block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    将 Claude tool_result 转换为 OpenAI tool message
    
    Tool ID Preservation: Claude's tool_result.tool_use_id is mapped to OpenAI's tool.tool_call_id
    to maintain correct ID mapping. This ensures the backend can correlate results with calls.
    This is critical for Requirements 5.1 and 5.4.

    Args:
        block: Claude tool_result 块

    Returns:
        OpenAI tool message 或 None
    """
    # Preserve the original tool_use_id from Claude
    # This ID must match the tool_call.id from the previous assistant message
    tool_use_id = block.get("tool_use_id")
    if not tool_use_id:
        return None

    # 提取 content
    raw_content = block.get("content", "")
    content_text = ""

    if isinstance(raw_content, str):
        content_text = raw_content
    elif isinstance(raw_content, list):
        text_parts = []
        for item in raw_content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif "text" in item:
                    text_parts.append(item["text"])
            elif isinstance(item, str):
                text_parts.append(item)
        content_text = "\n".join(text_parts)

    return {
        "role": "tool",
        "tool_call_id": tool_use_id,
        "content": content_text
    }


def _convert_image_block(block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    将 Claude 图片块转换为 OpenAI 图片格式

    Args:
        block: Claude image 块

    Returns:
        OpenAI 图片内容块或 None
    """
    source = block.get("source", {})
    if source.get("type") == "base64":
        media_type = source.get("media_type", "image/png")
        data = source.get("data", "")
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{data}"
            }
        }
    return None


def _convert_assistant_message(content: Union[str, List[Any]], thinking_enabled: bool = False) -> Optional[Dict[str, Any]]:
    """
    转换助手消息

    Args:
        content: Claude 助手消息内容
        thinking_enabled: 是否启用 thinking 模式

    Returns:
        OpenAI assistant message 或 None
    """
    if isinstance(content, str):
        return {
            "role": "assistant",
            "content": content
        }
    elif isinstance(content, list):
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")

                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "thinking":
                    # 如果启用 thinking 模式，将 thinking 块转换为 <thinking> 标签包裹的文本
                    # 这样后端可以理解历史中的 thinking 内容
                    if thinking_enabled:
                        thinking_text = block.get("thinking", "")
                        if thinking_text:
                            text_parts.append(f"{THINKING_START_TAG}{thinking_text}{THINKING_END_TAG}")
                    # 如果未启用 thinking，忽略 thinking 块
                elif block_type == "tool_use":
                    # 转换 tool_use 为 OpenAI tool_call
                    tool_call = _convert_tool_use_to_openai(block, len(tool_calls))
                    if tool_call:
                        tool_calls.append(tool_call)
            elif isinstance(block, str):
                text_parts.append(block)

        # 构建 assistant message
        assistant_msg: Dict[str, Any] = {
            "role": "assistant",
        }

        # 添加文本内容
        combined_text = "\n".join(text_parts)
        if combined_text.strip():
            assistant_msg["content"] = combined_text
        else:
            assistant_msg["content"] = None

        # 添加 tool_calls
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        return assistant_msg

    return None



def _convert_tool_use_to_openai(block: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    """
    将 Claude tool_use 转换为 OpenAI tool_call
    
    Tool ID Preservation: Claude's tool_use.id is directly mapped to OpenAI's tool_call.id
    to maintain correct ID mapping through the request/response cycle.
    This is critical for Requirements 5.1 and 5.4.

    Args:
        block: Claude tool_use 块
        index: tool_call 索引

    Returns:
        OpenAI tool_call 或 None
    """
    import json

    # Preserve the original tool_use_id from Claude
    # This ID will be used by the backend and returned in tool_call responses
    tool_id = block.get("id")
    name = block.get("name")
    input_data = block.get("input", {})

    if not tool_id or not name:
        return None

    return {
        "id": tool_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(input_data) if isinstance(input_data, dict) else str(input_data)
        }
    }


def convert_claude_tools_to_openai(tools: List[ClaudeTool]) -> List[Dict[str, Any]]:
    """
    将 Claude 工具定义转换为 OpenAI function 格式

    Args:
        tools: Claude 工具列表

    Returns:
        OpenAI tools 列表
    """
    openai_tools: List[Dict[str, Any]] = []

    for tool in tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema
            }
        }
        openai_tools.append(openai_tool)

    return openai_tools
