"""
Custom API 请求处理器
处理自定义 API 的请求和响应流，支持 OpenAI 和 Claude 格式
"""
import json
import logging
import httpx
from typing import Dict, Any, Optional, AsyncIterator

from models import ClaudeRequest
from .converter import (
    convert_claude_to_openai_request,
    convert_openai_stream_to_claude,
    convert_openai_error_to_claude,
)

logger = logging.getLogger(__name__)

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 300.0


async def handle_custom_api_request(
    account: Dict[str, Any],
    claude_req: ClaudeRequest,
    request_data: Dict[str, Any],
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> AsyncIterator[str]:
    """
    处理自定义 API 请求的主入口
    
    根据账号配置的 format 字段决定转换路径：
    - format="openai": 转换为 OpenAI 格式发送，响应转换回 Claude 格式
    - format="claude": 直接透传请求和响应
    
    Args:
        account: 自定义 API 账号信息
        claude_req: Claude 请求对象
        request_data: 原始请求数据字典
        cache_creation_input_tokens: 缓存创建 token 数
        cache_read_input_tokens: 缓存读取 token 数
    
    Yields:
        str: Claude 格式的 SSE 事件
    """
    # 从账号配置中提取信息
    other = account.get("other", {})
    if isinstance(other, str):
        try:
            other = json.loads(other)
        except json.JSONDecodeError:
            other = {}
    
    api_format = other.get("format", "openai")
    api_base = other.get("api_base", "")
    model = other.get("model", "gpt-4o")
    api_key = account.get("clientSecret", "")
    account_id = account.get("id")
    
    logger.info(f"Custom API 请求: format={api_format}, api_base={api_base}, model={model}")
    
    if api_format == "claude":
        # Claude 格式：透传
        async for event in handle_claude_format_stream(
            api_base=api_base,
            api_key=api_key,
            request_data=request_data,
            account_id=account_id,
            model=claude_req.model,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens
        ):
            yield event
    else:
        # OpenAI 格式：转换
        async for event in handle_openai_format_stream(
            api_base=api_base,
            api_key=api_key,
            model=model,
            claude_req=claude_req,
            account_id=account_id,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens
        ):
            yield event


async def handle_openai_format_stream(
    api_base: str,
    api_key: str,
    model: str,
    claude_req: ClaudeRequest,
    account_id: Optional[str] = None,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> AsyncIterator[str]:
    """
    处理 OpenAI 格式的自定义 API 流式响应
    
    将 Claude 请求转换为 OpenAI 格式，发送到目标 API，
    然后将 OpenAI 流式响应转换回 Claude 格式。
    
    Args:
        api_base: API 基础 URL (如 https://api.openai.com/v1)
        api_key: API 密钥
        model: 目标模型名称
        claude_req: Claude 请求对象
        account_id: 账号 ID（用于 token 统计）
        cache_creation_input_tokens: 缓存创建 token 数
        cache_read_input_tokens: 缓存读取 token 数
    
    Yields:
        str: Claude 格式的 SSE 事件
    """
    # 转换请求为 OpenAI 格式（同时返回 thinking_enabled 状态）
    openai_request, thinking_enabled = convert_claude_to_openai_request(claude_req, model)
    
    if thinking_enabled:
        logger.info("Thinking 模式已启用")
    
    # 确保启用流式响应
    openai_request["stream"] = True
    # 请求包含 usage 信息
    openai_request["stream_options"] = {"include_usage": True}
    
    # 构建 API URL
    # 自动添加 /v1 前缀（如果用户没有填写）
    base = api_base.rstrip('/')
    if not base.endswith('/v1'):
        base = f"{base}/v1"
    api_url = f"{base}/chat/completions"
    
    # 构建请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    logger.info(f"发送 OpenAI 格式请求到: {api_url}")
    
    # 估算输入 token 数量（简单估算）
    input_tokens = _estimate_input_tokens(openai_request)
    
    async def openai_byte_stream() -> AsyncIterator[bytes]:
        """发送请求并返回字节流"""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            try:
                async with client.stream(
                    "POST",
                    api_url,
                    json=openai_request,
                    headers=headers
                ) as response:
                    # 检查响应状态
                    if response.status_code != 200:
                        error_text = await response.aread()
                        error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                        logger.error(f"OpenAI API 错误: {response.status_code} {error_str}")
                        
                        # 转换错误为 Claude 格式
                        try:
                            error_json = json.loads(error_str)
                        except json.JSONDecodeError:
                            error_json = {"error": {"message": error_str, "type": "api_error"}}
                        
                        claude_error = convert_openai_error_to_claude(error_json, response.status_code)
                        error_event = f"event: error\ndata: {json.dumps(claude_error)}\n\n"
                        yield error_event.encode('utf-8')
                        return
                    
                    # 正常响应，返回字节流
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
                            
            except httpx.TimeoutException as e:
                logger.error(f"Custom API 超时: {e}")
                error_response = {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"上游 API 超时: {str(e)}"
                    }
                }
                error_event = f"event: error\ndata: {json.dumps(error_response)}\n\n"
                yield error_event.encode('utf-8')
                
            except httpx.ConnectError as e:
                logger.error(f"Custom API 连接失败: {e}")
                error_response = {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"无法连接到上游 API: {str(e)}"
                    }
                }
                error_event = f"event: error\ndata: {json.dumps(error_response)}\n\n"
                yield error_event.encode('utf-8')
                
            except httpx.RequestError as e:
                logger.error(f"Custom API 请求错误: {e}")
                error_response = {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"上游 API 请求错误: {str(e)}"
                    }
                }
                error_event = f"event: error\ndata: {json.dumps(error_response)}\n\n"
                yield error_event.encode('utf-8')
    
    # 转换 OpenAI 流为 Claude 流，并跟踪 token 使用量
    output_tokens = 0
    
    async for claude_event in convert_openai_stream_to_claude(
        openai_byte_stream(),
        model=claude_req.model,
        input_tokens=input_tokens,
        thinking_enabled=thinking_enabled,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens
    ):
        # 从 message_delta 事件中提取 output_tokens
        if 'event: message_delta' in claude_event:
            try:
                # 解析事件数据
                for line in claude_event.split('\n'):
                    if line.startswith('data:'):
                        data = json.loads(line[5:].strip())
                        if data.get('type') == 'message_delta':
                            usage = data.get('usage', {})
                            output_tokens = usage.get('output_tokens', output_tokens)
            except (json.JSONDecodeError, KeyError):
                pass
        
        # 在流结束时记录 token 使用量
        if 'event: message_stop' in claude_event:
            try:
                from usage_tracker import record_usage
                record_usage(
                    model=claude_req.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    account_id=account_id,
                    channel="custom_api",
                    cache_creation_input_tokens=cache_creation_input_tokens,
                    cache_read_input_tokens=cache_read_input_tokens
                )
                logger.info(f"Custom API Token 统计 - 输入: {input_tokens}, 输出: {output_tokens}, "
                           f"缓存创建: {cache_creation_input_tokens}, 缓存读取: {cache_read_input_tokens}")
            except Exception as e:
                logger.error(f"记录 Custom API token 使用量失败: {e}")
        
        yield claude_event


async def handle_claude_format_stream(
    api_base: str,
    api_key: str,
    request_data: Dict[str, Any],
    account_id: Optional[str] = None,
    model: str = "claude-sonnet-4.5",
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> AsyncIterator[str]:
    """
    处理 Claude 格式的自定义 API 流式响应（透传模式）
    
    直接将请求转发到目标 API，不进行格式转换。
    响应也直接透传回客户端。
    
    Args:
        api_base: API 基础 URL (如 https://api.anthropic.com)
        api_key: API 密钥
        request_data: 原始 Claude 请求数据
        account_id: 账号 ID（用于 token 统计）
        model: 模型名称
        cache_creation_input_tokens: 缓存创建 token 数
        cache_read_input_tokens: 缓存读取 token 数
    
    Yields:
        str: Claude 格式的 SSE 事件（直接透传）
    """
    # 用于跟踪 token 使用量
    input_tokens = 0
    output_tokens = 0
    # 构建 API URL
    api_url = f"{api_base.rstrip('/')}/v1/messages"
    
    # 构建请求头（Claude API 格式）
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    
    logger.info(f"透传 Claude 格式请求到: {api_url}")
    
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            async with client.stream(
                "POST",
                api_url,
                json=request_data,
                headers=headers
            ) as response:
                # 检查响应状态
                if response.status_code != 200:
                    error_text = await response.aread()
                    error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                    logger.error(f"Claude API 错误: {response.status_code} {error_str}")
                    
                    # 直接返回错误（已经是 Claude 格式）
                    try:
                        error_json = json.loads(error_str)
                        error_event = f"event: error\ndata: {json.dumps(error_json)}\n\n"
                    except json.JSONDecodeError:
                        error_response = {
                            "type": "error",
                            "error": {
                                "type": "api_error",
                                "message": error_str
                            }
                        }
                        error_event = f"event: error\ndata: {json.dumps(error_response)}\n\n"
                    yield error_event
                    return
                
                # 透传响应流，同时提取 token 统计
                buffer = ""
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    
                    try:
                        text = chunk.decode('utf-8')
                    except UnicodeDecodeError:
                        logger.warning("Failed to decode chunk as UTF-8")
                        continue
                    
                    buffer += text
                    
                    # 按 SSE 事件分割
                    while '\n\n' in buffer:
                        event_text, buffer = buffer.split('\n\n', 1)
                        if event_text.strip():
                            # 从事件中提取 token 统计
                            for line in event_text.split('\n'):
                                if line.startswith('data:'):
                                    try:
                                        data = json.loads(line[5:].strip())
                                        event_type = data.get('type')
                                        if event_type == 'message_start':
                                            usage = data.get('message', {}).get('usage', {})
                                            input_tokens = usage.get('input_tokens', input_tokens)
                                        elif event_type == 'message_delta':
                                            usage = data.get('usage', {})
                                            output_tokens = usage.get('output_tokens', output_tokens)
                                        elif event_type == 'message_stop':
                                            # 记录 token 使用量
                                            try:
                                                from usage_tracker import record_usage
                                                record_usage(
                                                    model=model,
                                                    input_tokens=input_tokens,
                                                    output_tokens=output_tokens,
                                                    account_id=account_id,
                                                    channel="custom_api",
                                                    cache_creation_input_tokens=cache_creation_input_tokens,
                                                    cache_read_input_tokens=cache_read_input_tokens
                                                )
                                                logger.info(f"Custom API (Claude) Token 统计 - 输入: {input_tokens}, 输出: {output_tokens}, "
                                                           f"缓存创建: {cache_creation_input_tokens}, 缓存读取: {cache_read_input_tokens}")
                                            except Exception as e:
                                                logger.error(f"记录 Custom API token 使用量失败: {e}")
                                    except json.JSONDecodeError:
                                        pass
                            yield event_text + '\n\n'
                
                # 处理剩余的 buffer
                if buffer.strip():
                    yield buffer + '\n\n'
                    
        except httpx.TimeoutException as e:
            logger.error(f"Custom API (Claude format) 超时: {e}")
            error_response = {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"上游 API 超时: {str(e)}"
                }
            }
            yield f"event: error\ndata: {json.dumps(error_response)}\n\n"
            
        except httpx.ConnectError as e:
            logger.error(f"Custom API (Claude format) 连接失败: {e}")
            error_response = {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"无法连接到上游 API: {str(e)}"
                }
            }
            yield f"event: error\ndata: {json.dumps(error_response)}\n\n"
            
        except httpx.RequestError as e:
            logger.error(f"Custom API (Claude format) 请求错误: {e}")
            error_response = {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"上游 API 请求错误: {str(e)}"
                }
            }
            yield f"event: error\ndata: {json.dumps(error_response)}\n\n"


def _estimate_input_tokens(openai_request: Dict[str, Any]) -> int:
    """
    估算 OpenAI 请求的输入 token 数量
    
    简单估算：每 4 个字符约等于 1 个 token
    
    Args:
        openai_request: OpenAI 请求字典
    
    Returns:
        int: 估算的 token 数量
    """
    total_chars = 0
    
    # 统计消息内容
    for msg in openai_request.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total_chars += len(item["text"])
    
    # 统计工具定义
    for tool in openai_request.get("tools", []):
        func = tool.get("function", {})
        total_chars += len(func.get("name", ""))
        total_chars += len(func.get("description", ""))
        total_chars += len(json.dumps(func.get("parameters", {})))
    
    # 简单估算：每 4 个字符约 1 个 token
    return max(1, total_chars // 4)
