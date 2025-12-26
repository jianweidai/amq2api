"""
Amazon Q 后端模块
包含请求转换、事件解析和流处理
"""

from src.amazonq.converter import (
    convert_claude_to_codewhisperer_request,
    codewhisperer_request_to_dict,
)

from src.amazonq.parser import (
    parse_event_data,
    parse_sse_line,
    build_claude_sse_event,
    build_claude_message_start_event,
    build_claude_content_block_start_event,
    build_claude_content_block_delta_event,
    build_claude_content_block_stop_event,
    build_claude_ping_event,
    build_claude_message_stop_event,
    build_claude_tool_use_start_event,
    build_claude_tool_use_input_delta_event,
    parse_amazonq_event,
)

from src.amazonq.event_stream_parser import (
    EventStreamParser,
    extract_event_info,
)

from src.amazonq.stream_handler import handle_amazonq_stream

__all__ = [
    # converter
    "convert_claude_to_codewhisperer_request",
    "codewhisperer_request_to_dict",
    # parser
    "parse_event_data",
    "parse_sse_line",
    "build_claude_sse_event",
    "build_claude_message_start_event",
    "build_claude_content_block_start_event",
    "build_claude_content_block_delta_event",
    "build_claude_content_block_stop_event",
    "build_claude_ping_event",
    "build_claude_message_stop_event",
    "build_claude_tool_use_start_event",
    "build_claude_tool_use_input_delta_event",
    "parse_amazonq_event",
    # event_stream_parser
    "EventStreamParser",
    "extract_event_info",
    # stream_handler
    "handle_amazonq_stream",
]
