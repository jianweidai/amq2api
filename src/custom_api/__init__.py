"""
Custom API 模块
支持将 Claude API 请求转换为 OpenAI 格式，以及将 OpenAI 响应转换回 Claude 格式
"""

from src.custom_api.converter import (
    # Claude → OpenAI 请求转换
    convert_claude_to_openai_request,
    convert_claude_messages_to_openai,
    convert_claude_tools_to_openai,
    # OpenAI → Claude 响应转换
    convert_openai_stream_to_claude,
    convert_openai_delta_to_claude_events,
    convert_openai_usage_to_claude,
    convert_openai_error_to_claude,
    OpenAIStreamState,
)

from src.custom_api.handler import (
    handle_custom_api_request,
    handle_openai_format_stream,
    handle_claude_format_stream,
)

__all__ = [
    # Claude → OpenAI 请求转换
    "convert_claude_to_openai_request",
    "convert_claude_messages_to_openai",
    "convert_claude_tools_to_openai",
    # OpenAI → Claude 响应转换
    "convert_openai_stream_to_claude",
    "convert_openai_delta_to_claude_events",
    "convert_openai_usage_to_claude",
    "convert_openai_error_to_claude",
    "OpenAIStreamState",
    # Handler functions
    "handle_custom_api_request",
    "handle_openai_format_stream",
    "handle_claude_format_stream",
]
