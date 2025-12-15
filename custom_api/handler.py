"""
Custom API 请求处理器
处理自定义 API 的请求和响应流，支持 OpenAI 和 Claude 格式
"""
import json
import logging
import asyncio
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

# 429 重试配置
MAX_RETRIES = 3  # 最大重试次数
BASE_RETRY_DELAY = 5.0  # 基础重试延迟（秒）
MAX_RETRY_DELAY = 60.0  # 最大重试延迟（秒）


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
    provider = other.get("provider", "")  # 新增：API 提供商（azure, anthropic, openai 等）
    api_key = account.get("clientSecret", "")
    account_id = account.get("id")
    
    logger.info(f"Custom API 请求: format={api_format}, provider={provider}, api_base={api_base}, model={model}")
    
    if api_format == "claude":
        # Claude 格式：根据 provider 决定是否清理请求
        async for event in handle_claude_format_stream(
            api_base=api_base,
            api_key=api_key,
            request_data=request_data,
            account_id=account_id,
            model=claude_req.model,
            provider=provider,  # 传递 provider
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
        """发送请求并返回字节流，支持 429 错误自动重试"""
        retry_count = 0
        last_error = None
        
        while retry_count <= MAX_RETRIES:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                try:
                    async with client.stream(
                        "POST",
                        api_url,
                        json=openai_request,
                        headers=headers
                    ) as response:
                        # 检查响应状态
                        if response.status_code == 429:
                            # 429 速率限制错误 - 尝试重试
                            error_text = await response.aread()
                            error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                            
                            if retry_count < MAX_RETRIES:
                                # 计算重试延迟（指数退避）
                                retry_after = response.headers.get('Retry-After')
                                if retry_after:
                                    try:
                                        delay = min(float(retry_after), MAX_RETRY_DELAY)
                                    except ValueError:
                                        delay = min(BASE_RETRY_DELAY * (2 ** retry_count), MAX_RETRY_DELAY)
                                else:
                                    delay = min(BASE_RETRY_DELAY * (2 ** retry_count), MAX_RETRY_DELAY)
                                
                                retry_count += 1
                                logger.warning(
                                    f"Custom API 429 速率限制，{delay:.1f}秒后重试 "
                                    f"(第 {retry_count}/{MAX_RETRIES} 次): {error_str[:200]}"
                                )
                                await asyncio.sleep(delay)
                                continue  # 重试
                            else:
                                # 重试次数用尽，设置 5 分钟冷却
                                logger.error(f"Custom API 429 重试次数用尽: {error_str}")
                                if account_id:
                                    from account_manager import set_account_cooldown
                                    set_account_cooldown(account_id, 300)  # 5 分钟冷却
                                    logger.warning(f"Custom API 账号 {account_id} 进入 5 分钟冷却期")
                                
                                try:
                                    error_json = json.loads(error_str)
                                except json.JSONDecodeError:
                                    error_json = {"error": {"message": error_str, "type": "rate_limit_error"}}
                                
                                claude_error = convert_openai_error_to_claude(error_json, 429)
                                claude_error["error"]["message"] = "速率限制：账号已进入 5 分钟冷却期，请稍后重试。" + claude_error["error"].get("message", "")
                                error_event = f"event: error\ndata: {json.dumps(claude_error)}\n\n"
                                yield error_event.encode('utf-8')
                                return
                        
                        elif response.status_code != 200:
                            # 其他错误，不重试
                            error_text = await response.aread()
                            error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                            logger.error(f"OpenAI API 错误: {response.status_code} {error_str}")
                            
                            try:
                                error_json = json.loads(error_str)
                            except json.JSONDecodeError:
                                error_json = {"error": {"message": error_str, "type": "api_error"}}
                            
                            claude_error = convert_openai_error_to_claude(error_json, response.status_code)
                            error_event = f"event: error\ndata: {json.dumps(claude_error)}\n\n"
                            yield error_event.encode('utf-8')
                            return
                        
                        # 正常响应，返回字节流
                        if retry_count > 0:
                            logger.info(f"Custom API 429 重试成功 (第 {retry_count} 次)")
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                yield chunk
                        return  # 成功完成，退出重试循环
                                
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
                    return
                    
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
                    return
                    
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
                    return
    
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
    provider: str = "",
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> AsyncIterator[str]:
    """
    处理 Claude 格式的自定义 API 流式响应（透传模式）
    
    根据 provider 决定是否清理请求：
    - provider="azure": 应用 Azure 特殊清理逻辑（移除不支持的字段、转换工具格式等）
    - provider="anthropic" 或空: 直接透传，不清理
    
    Args:
        api_base: API 基础 URL (如 https://api.anthropic.com)
        api_key: API 密钥
        request_data: 原始 Claude 请求数据
        account_id: 账号 ID（用于 token 统计）
        model: 模型名称
        provider: API 提供商（azure, anthropic 等）
        cache_creation_input_tokens: 缓存创建 token 数
        cache_read_input_tokens: 缓存读取 token 数
    
    Yields:
        str: Claude 格式的 SSE 事件（直接透传）
    """
    # 根据 provider 决定是否清理请求
    if provider == "azure":
        # Azure 需要特殊处理：移除不支持的字段、转换工具格式等
        request_data = _clean_claude_request_for_azure(request_data)
    # 官方 Anthropic API 或其他：直接透传，不清理
    
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
                if response.status_code == 429:
                    # 429 速率限制，设置 5 分钟冷却
                    error_text = await response.aread()
                    error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                    logger.error(f"Claude API 429 速率限制: {error_str}")
                    
                    if account_id:
                        from account_manager import set_account_cooldown
                        set_account_cooldown(account_id, 300)  # 5 分钟冷却
                        logger.warning(f"Custom API (Claude格式) 账号 {account_id} 进入 5 分钟冷却期")
                    
                    error_response = {
                        "type": "error",
                        "error": {
                            "type": "rate_limit_error",
                            "message": "速率限制：账号已进入 5 分钟冷却期，请稍后重试"
                        }
                    }
                    error_event = f"event: error\ndata: {json.dumps(error_response)}\n\n"
                    yield error_event
                    return
                
                elif response.status_code != 200:
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


def _clean_claude_request_for_azure(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    为 Azure Anthropic API 清理 Claude 请求数据
    
    Azure 的 Anthropic API 有一些限制：
    1. 不支持某些扩展字段（context_management, betas 等）
    2. 工具格式需要转换为标准格式（不支持 custom 类型包装）
    3. 所有消息必须有非空 content（除了最后一条 assistant 消息）
    
    Args:
        request_data: 原始请求数据
    
    Returns:
        清理后的请求数据
    """
    # 深拷贝以避免修改原始数据
    import copy
    cleaned = copy.deepcopy(request_data)
    
    # 移除不支持的顶层字段
    unsupported_fields = [
        "context_management",  # Azure 不支持
        "betas",  # beta 功能
        "anthropic_beta",  # beta 功能
    ]
    for field in unsupported_fields:
        if field in cleaned:
            logger.debug(f"移除不支持的字段: {field}")
            del cleaned[field]
    
    # 清理 messages 字段：确保所有消息都有非空 content
    if "messages" in cleaned and isinstance(cleaned["messages"], list):
        cleaned_messages = []
        for idx, msg in enumerate(cleaned["messages"]):
            if isinstance(msg, dict):
                content = msg.get("content")
                role = msg.get("role", "")
                
                # 检查 content 是否为空
                is_empty = False
                if content is None:
                    is_empty = True
                elif isinstance(content, str) and not content.strip():
                    is_empty = True
                elif isinstance(content, list) and len(content) == 0:
                    is_empty = True
                
                if is_empty:
                    # 最后一条 assistant 消息可以为空
                    is_last = (idx == len(cleaned["messages"]) - 1)
                    if role == "assistant" and is_last:
                        cleaned_messages.append(msg)
                    else:
                        logger.debug(f"跳过空内容消息 {idx}: role={role}")
                else:
                    cleaned_messages.append(msg)
            else:
                cleaned_messages.append(msg)
        
        cleaned["messages"] = cleaned_messages
    
    # 清理 tools 字段
    if "tools" in cleaned and isinstance(cleaned["tools"], list):
        cleaned_tools = []
        for idx, tool in enumerate(cleaned["tools"]):
            if isinstance(tool, dict):
                tool_type = tool.get("type")
                
                # 记录原始工具信息用于调试
                logger.debug(f"处理工具 {idx}: type={tool_type}, keys={list(tool.keys())}")
                
                # Claude 内置工具类型（保持原样）
                builtin_types = [
                    "bash_20250124", "bash_20241022",
                    "text_editor_20250124", "text_editor_20250429", "text_editor_20250728", "text_editor_20241022",
                    "web_search_20250305",
                    "computer_20241022"
                ]
                
                if tool_type in builtin_types:
                    # 内置工具类型，只保留 type 和 name
                    cleaned_tool = {"type": tool_type}
                    if "name" in tool:
                        cleaned_tool["name"] = tool["name"]
                    cleaned_tools.append(cleaned_tool)
                    
                elif tool_type == "custom":
                    # custom 类型工具，提取为标准格式
                    custom_data = tool.get("custom", {})
                    cleaned_tool = {}
                    
                    if custom_data and isinstance(custom_data, dict):
                        for field in ["name", "description", "input_schema"]:
                            if field in custom_data:
                                cleaned_tool[field] = custom_data[field]
                    
                    # 如果 custom 子对象没有字段，尝试从顶层获取
                    if "name" not in cleaned_tool and "name" in tool:
                        cleaned_tool["name"] = tool["name"]
                    if "description" not in cleaned_tool and "description" in tool:
                        cleaned_tool["description"] = tool["description"]
                    if "input_schema" not in cleaned_tool and "input_schema" in tool:
                        cleaned_tool["input_schema"] = tool["input_schema"]
                    
                    if cleaned_tool.get("name"):
                        cleaned_tools.append(cleaned_tool)
                    else:
                        logger.warning(f"跳过无效 custom 工具 {idx}: 缺少 name 字段")
                    
                elif tool_type == "function" or "function" in tool:
                    # OpenAI function 格式，转换为标准 Claude 格式
                    func = tool.get("function", {})
                    cleaned_tool = {}
                    
                    if func:
                        if "name" in func:
                            cleaned_tool["name"] = func["name"]
                        if "description" in func:
                            cleaned_tool["description"] = func["description"]
                        if "parameters" in func:
                            cleaned_tool["input_schema"] = func["parameters"]
                    
                    # 如果 function 子对象没有 name，尝试从顶层获取
                    if "name" not in cleaned_tool and "name" in tool:
                        cleaned_tool["name"] = tool["name"]
                    if "description" not in cleaned_tool and "description" in tool:
                        cleaned_tool["description"] = tool["description"]
                    
                    if cleaned_tool.get("name"):
                        cleaned_tools.append(cleaned_tool)
                    else:
                        logger.warning(f"跳过无效 function 工具 {idx}: 缺少 name 字段")
                
                elif tool_type is None and "name" in tool:
                    # 标准 Claude 工具格式，只保留允许的字段
                    cleaned_tool = {"name": tool["name"]}
                    if "description" in tool:
                        cleaned_tool["description"] = tool["description"]
                    if "input_schema" in tool:
                        cleaned_tool["input_schema"] = tool["input_schema"]
                    if "parameters" in tool:
                        cleaned_tool["input_schema"] = tool["parameters"]
                    cleaned_tools.append(cleaned_tool)
                
                else:
                    # 未知类型，记录警告并跳过
                    logger.warning(f"跳过未知工具类型 {idx}: type={tool_type}, keys={list(tool.keys())}")
            else:
                logger.warning(f"跳过非字典工具 {idx}: {tool}")
        
        cleaned["tools"] = cleaned_tools
        
        # 调试：打印第一个工具的结构
        if cleaned_tools:
            logger.info(f"第一个工具结构: {json.dumps(cleaned_tools[0], ensure_ascii=False)[:500]}")
        logger.info(f"工具清理完成: {len(cleaned['tools'])} 个工具")
    
    return cleaned


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
