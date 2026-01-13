"""
事件解析模块
解析 Amazon Q / CodeWhisperer 事件数据
支持 AWS Event Stream 格式
"""
import json
import logging
import re
import uuid
from typing import Optional, Dict, Any, List, Tuple
from src.models import (
    CodeWhispererEventData,
    MessageStart,
    ContentBlockStart,
    ContentBlockDelta,
    ContentBlockStop,
    MessageStop,
    CodeWhispererToolUse,
    Message,
    ContentBlock,
    Delta,
    Usage
)

logger = logging.getLogger(__name__)


def parse_event_data(json_string: str) -> Optional[CodeWhispererEventData]:
    """
    解析 CodeWhisperer 事件数据

    Args:
        json_string: JSON 字符串

    Returns:
        Optional[CodeWhispererEventData]: 解析成功返回事件对象，失败返回 None
    """
    try:
        # 步骤 1: 解析 JSON
        json_object = json.loads(json_string)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return None

    # 检查是否是字典
    if not isinstance(json_object, dict):
        logger.error("JSON 对象不是字典类型")
        return None

    # 步骤 2: 根据字段匹配不同的事件类型
    try:
        # --- 尝试匹配标准事件（有 "type" 字段）---
        if "type" in json_object:
            event_type = json_object["type"]

            # message_start 事件
            if event_type == "message_start":
                message_data = json_object.get("message", {})
                conversation_id = message_data.get("id") or message_data.get("conversationId")

                if conversation_id:
                    message = Message(
                        conversationId=conversation_id,
                        role=message_data.get("role", "assistant")
                    )
                    return MessageStart(message=message)

            # content_block_start 事件
            elif event_type == "content_block_start":
                if "content_block" in json_object and "index" in json_object:
                    index = json_object["index"]
                    content_type = json_object["content_block"].get("type", "text")

                    content_block = ContentBlock(type=content_type)
                    return ContentBlockStart(index=index, content_block=content_block)

            # content_block_delta 事件
            elif event_type == "content_block_delta":
                if "delta" in json_object and "index" in json_object:
                    delta_data = json_object["delta"]
                    text_chunk = delta_data.get("text")
                    index = json_object["index"]

                    if text_chunk is not None:
                        delta = Delta(
                            type=delta_data.get("type", "text_delta"),
                            text=text_chunk
                        )
                        return ContentBlockDelta(index=index, delta=delta)

            # content_block_stop 事件
            elif event_type == "content_block_stop":
                if "index" in json_object:
                    index = json_object["index"]
                    return ContentBlockStop(index=index)

            # message_stop 事件
            elif event_type == "message_stop":
                stop_reason = json_object.get("stop_reason")
                usage_data = json_object.get("usage")

                usage = None
                if usage_data:
                    usage = Usage(
                        input_tokens=usage_data.get("input_tokens", 0),
                        output_tokens=usage_data.get("output_tokens", 0)
                    )

                return MessageStop(stop_reason=stop_reason, usage=usage)

        # --- 尝试匹配 ToolUse 事件（没有 "type" 字段）---
        if "toolUseId" in json_object and "name" in json_object and "input" in json_object:
            tool_use_id = json_object["toolUseId"]
            name = json_object["name"]
            input_data = json_object["input"]

            return CodeWhispererToolUse(
                toolUseId=tool_use_id,
                name=name,
                input=input_data
            )

        # 如果所有模式都不匹配
        logger.warning(f"未知的事件类型: {json_object}")
        return None

    except Exception as e:
        logger.error(f"解析事件数据时发生错误: {e}")
        return None


def parse_sse_line(line: str) -> Optional[str]:
    """
    解析 SSE 行，提取 data 字段

    Args:
        line: SSE 行（例如 "data: {...}"）

    Returns:
        Optional[str]: 提取的 JSON 字符串，如果不是 data 行则返回 None
    """
    line = line.strip()

    # 跳过空行和注释
    if not line or line.startswith(":"):
        return None

    # 解析 data: 行
    if line.startswith("data:"):
        data = line[5:].strip()  # 移除 "data:" 前缀
        return data

    return None


def build_claude_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    构建 Claude SSE 格式的事件

    Args:
        event_type: 事件类型
        data: 事件数据

    Returns:
        str: SSE 格式的事件字符串
    """
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


def build_claude_message_start_event(
    conversation_id: str,
    model: str = "claude-sonnet-4.5",
    input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> str:
    """构建 message_start 事件
    
    Args:
        conversation_id: 会话 ID
        model: 模型名称
        input_tokens: 输入 token 数量
        cache_creation_input_tokens: 缓存创建时消耗的 token 数量
        cache_read_input_tokens: 从缓存读取的 token 数量
    
    Returns:
        str: SSE 格式的 message_start 事件
    """
    usage = {
        "input_tokens": input_tokens,
        "output_tokens": 0,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens
    }
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
            "usage": usage
        }
    }
    return build_claude_sse_event("message_start", data)


def build_claude_content_block_start_event(index: int, content_type: str = "text") -> str:
    """构建 content_block_start 事件"""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": content_type, content_type: ""}
    }
    return build_claude_sse_event("content_block_start", data)


def build_claude_content_block_delta_event(index: int, text: str, delta_type: str = "text_delta", field_name: str = "text") -> str:
    """构建 content_block_delta 事件"""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": delta_type, field_name: text}
    }
    return build_claude_sse_event("content_block_delta", data)


def build_claude_content_block_stop_event(index: int) -> str:
    """构建 content_block_stop 事件"""
    data = {
        "type": "content_block_stop",
        "index": index
    }
    return build_claude_sse_event("content_block_stop", data)


def build_claude_ping_event() -> str:
    """构建 ping 事件(保持连接活跃)"""
    data = {"type": "ping"}
    return build_claude_sse_event("ping", data)


def build_claude_message_stop_event(
    input_tokens: int,
    output_tokens: int,
    stop_reason: Optional[str] = None,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> str:
    """构建 message_delta 和 message_stop 事件
    
    Args:
        input_tokens: 输入 token 数量
        output_tokens: 输出 token 数量
        stop_reason: 停止原因
        cache_creation_input_tokens: 缓存创建时消耗的 token 数量
        cache_read_input_tokens: 从缓存读取的 token 数量
    
    Returns:
        str: SSE 格式的 message_delta 和 message_stop 事件
    """
    # 先发送 message_delta
    usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens
    }
    delta_data = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason or "end_turn", "stop_sequence": None},
        "usage": usage
    }
    delta_event = build_claude_sse_event("message_delta", delta_data)

    # 再发送 message_stop（包含最终 usage）
    stop_data = {
        "type": "message_stop"
        # "stop_reason": stop_reason or "end_turn",
        # "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}
    }
    stop_event = build_claude_sse_event("message_stop", stop_data)

    return delta_event + stop_event


def build_claude_tool_use_start_event(index: int, tool_use_id: str, tool_name: str) -> str:
    """构建 tool use 类型的 content_block_start 事件"""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {
            "type": "tool_use",
            "id": tool_use_id,
            "name": tool_name
        }
    }
    return build_claude_sse_event("content_block_start", data)


def build_claude_tool_use_input_delta_event(index: int, input_json_delta: str) -> str:
    """构建 tool use input 内容的 content_block_delta 事件"""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {
            "type": "input_json_delta",
            "partial_json": input_json_delta
        }
    }
    return build_claude_sse_event("content_block_delta", data)


# ============================================================================
# Amazon Q Event Stream 特定解析函数
# ============================================================================

def parse_amazonq_event(event_info: Dict[str, Any]) -> Optional[CodeWhispererEventData]:
    """
    解析 Amazon Q Event Stream 事件

    Amazon Q 事件格式：
    - event_type: "initial-response" | "assistantResponseEvent" | "toolUseEvent"
    - payload: {"conversationId": "..."} | {"content": "..."} | {"name": "...", "toolUseId": "...", "input": "...", "stop": true/false}

    Args:
        event_info: 从 Event Stream 提取的事件信息

    Returns:
        Optional[CodeWhispererEventData]: 转换后的事件对象
    """
    event_type = event_info.get('event_type')
    payload = event_info.get('payload')

    if not event_type or not payload:
        return None

    try:
        # initial-response 事件 -> MessageStart
        if event_type == 'initial-response':
            conversation_id = payload.get('conversationId', '')
            import uuid
            message = Message(
                conversationId=conversation_id or str(uuid.uuid4()),
                role="assistant"
            )
            return MessageStart(message=message)

        # assistantResponseEvent 事件 -> ContentBlockDelta
        elif event_type == 'assistantResponseEvent':
            content = payload.get('content', '')
            tool_uses = payload.get('toolUses', [])

            # 如果有文本内容，返回文本增量事件
            if content:
                delta = Delta(
                    type="text_delta",
                    text=content
                )
                # Amazon Q 不提供 index，默认使用 0
                return ContentBlockDelta(index=0, delta=delta)

            # 如果有 toolUses，返回助手响应事件（用于构建完整的助手消息）
            if tool_uses:
                # 这表示助手响应的结束，包含 toolUses
                return AssistantResponseEnd(
                    tool_uses=tool_uses,
                    message_id=payload.get('messageId', '')
                )

        # toolUseEvent 事件 -> 需要特殊处理
        elif event_type == 'toolUseEvent':
            # 这是工具调用事件，需要累积 input 片段
            # 返回 None，让 stream_handler 通过 event_type 检测并处理
            return None

        return None

    except Exception as e:
        logger.error(f"解析 Amazon Q 事件失败: {e}")
        return None


# ============================================================================
# 工具调用去重函数（移植自 KiroGate）
# ============================================================================

def generate_tool_call_id() -> str:
    """
    生成唯一的 tool_call_id
    
    Returns:
        格式为 'call_xxxxxxxx' 的唯一标识符
    """
    return f"call_{uuid.uuid4().hex[:12]}"


def find_matching_brace(text: str, start_pos: int) -> int:
    """
    找到与指定位置的开括号匹配的闭括号位置
    
    使用 bracket counting 来正确处理嵌套 JSON。
    正确处理字符串中的括号和转义字符。
    
    Args:
        text: 要搜索的文本
        start_pos: 开括号 '{' 的位置
        
    Returns:
        闭括号的位置，如果未找到则返回 -1
        
    Example:
        >>> find_matching_brace('{"a": {"b": 1}}', 0)
        14
        >>> find_matching_brace('{"a": "{}"}', 0)
        10
    """
    if start_pos >= len(text) or text[start_pos] != '{':
        return -1
    
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_pos, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\' and in_string:
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return i
    
    return -1


def parse_bracket_tool_calls(response_text: str) -> List[Dict[str, Any]]:
    """
    解析 [Called func_name with args: {...}] 格式的工具调用
    
    某些模型会以文本格式返回工具调用，而不是结构化 JSON。
    此函数从文本中提取这些调用。
    
    Args:
        response_text: 模型响应文本
        
    Returns:
        OpenAI 格式的工具调用列表
        
    Example:
        >>> text = '[Called get_weather with args: {"city": "London"}]'
        >>> calls = parse_bracket_tool_calls(text)
        >>> calls[0]["function"]["name"]
        'get_weather'
    """
    if not response_text or "[Called" not in response_text:
        return []
    
    tool_calls = []
    pattern = r'\[Called\s+(\w+)\s+with\s+args:\s*'
    
    for match in re.finditer(pattern, response_text, re.IGNORECASE):
        func_name = match.group(1)
        args_start = match.end()
        
        # 查找 JSON 的开始位置
        json_start = response_text.find('{', args_start)
        if json_start == -1:
            continue
        
        # 使用括号匹配找到 JSON 的结束位置
        json_end = find_matching_brace(response_text, json_start)
        if json_end == -1:
            continue
        
        json_str = response_text[json_start:json_end + 1]
        
        try:
            args = json.loads(json_str)
            tool_call_id = generate_tool_call_id()
            tool_calls.append({
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": func_name,
                    "arguments": json.dumps(args)
                }
            })
        except json.JSONDecodeError:
            logger.warning(f"无法解析工具调用参数: {json_str[:100]}")
    
    return tool_calls


def deduplicate_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    去除重复的工具调用
    
    去重基于两个标准：
    1. 按 ID 去重 - 如果存在多个具有相同 ID 的工具调用，
       保留参数更完整（非空 "{}"）的那个
    2. 按 name+arguments 去重 - 删除完全相同的调用
    
    Args:
        tool_calls: 工具调用列表
        
    Returns:
        去重后的工具调用列表
    """
    if not tool_calls:
        return []
    
    # 阶段 1: 按 ID 去重，保留参数更完整的版本
    by_id: Dict[str, Dict[str, Any]] = {}
    no_id_calls = []
    
    for tc in tool_calls:
        tc_id = tc.get("id", "")
        if not tc_id:
            # 没有 ID 的调用单独处理
            no_id_calls.append(tc)
            continue
        
        existing = by_id.get(tc_id)
        if existing is None:
            by_id[tc_id] = tc
        else:
            # 存在重复 ID，保留参数更完整的版本
            existing_args = existing.get("function", {}).get("arguments", "{}")
            current_args = tc.get("function", {}).get("arguments", "{}")
            
            # 优先选择非空参数，或更长的参数
            if current_args != "{}" and (existing_args == "{}" or len(current_args) > len(existing_args)):
                logger.debug(f"替换工具调用 {tc_id}，使用更完整的参数: {len(existing_args)} -> {len(current_args)}")
                by_id[tc_id] = tc
    
    # 收集所有有 ID 的调用
    result_with_id = list(by_id.values())
    
    # 阶段 2: 按 name+arguments 去重
    seen = set()
    unique = []
    
    for tc in result_with_id + no_id_calls:
        # 防止 function 为 None
        func = tc.get("function") or {}
        func_name = func.get("name") or ""
        func_args = func.get("arguments") or "{}"
        key = f"{func_name}-{func_args}"
        
        if key not in seen:
            seen.add(key)
            unique.append(tc)
    
    if len(tool_calls) != len(unique):
        logger.info(f"[TOOL_DEDUP] 工具调用去重: {len(tool_calls)} -> {len(unique)}")
    
    return unique


def normalize_tool_call_arguments(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    标准化工具调用的参数字段
    
    确保 arguments 字段是有效的 JSON 字符串。
    
    Args:
        tool_call: 工具调用字典
        
    Returns:
        标准化后的工具调用
    """
    func = tool_call.get("function", {})
    args = func.get("arguments", "")
    tool_name = func.get("name", "unknown")
    
    if isinstance(args, str):
        if args.strip():
            try:
                parsed = json.loads(args)
                # 确保结果是 JSON 字符串
                tool_call["function"]["arguments"] = json.dumps(parsed)
            except json.JSONDecodeError as e:
                logger.warning(f"无法解析工具 '{tool_name}' 的参数: {e}. 原始值: {args[:200]}")
                tool_call["function"]["arguments"] = "{}"
        else:
            tool_call["function"]["arguments"] = "{}"
    elif isinstance(args, dict):
        # 如果已经是字典，序列化为字符串
        tool_call["function"]["arguments"] = json.dumps(args)
    else:
        tool_call["function"]["arguments"] = "{}"
    
    return tool_call