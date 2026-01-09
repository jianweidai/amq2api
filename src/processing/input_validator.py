"""
输入验证模块
在发送请求前检查输入长度，避免流开始后才发现错误
"""
import logging
import json
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Amazon Q 输入长度限制（tokens）
# 根据实际测试，Amazon Q 的限制大约在 30000-40000 tokens 左右
# 注意：这个限制是预防性的，实际限制可能更高
# 如果遇到误报，可以通过环境变量 AMAZONQ_MAX_INPUT_TOKENS 调整
import os
AMAZONQ_MAX_INPUT_TOKENS = int(os.getenv("AMAZONQ_MAX_INPUT_TOKENS", "100000"))  # 提高到 100k，更宽松

# 图片 token 估算：每张图片大约消耗的 tokens
# Base64 编码的图片数据量很大，需要特别估算
IMAGE_TOKEN_ESTIMATE_PER_KB = 256  # 每 KB base64 数据约 256 tokens


def _count_tokens(text: str) -> int:
    """
    使用 tiktoken 计算 token 数量
    
    Args:
        text: 要计算的文本
        
    Returns:
        int: token 数量
    """
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception as e:
        # 回退到简化估算：平均每 4 个字符约等于 1 个 token
        logger.debug(f"tiktoken 计数失败，使用简化估算: {e}")
        return max(1, len(text) // 4)


def estimate_image_tokens(image_data: str) -> int:
    """
    估算图片的 token 数量
    
    Args:
        image_data: base64 编码的图片数据
        
    Returns:
        int: 估算的 token 数量
    """
    # Base64 数据大小（KB）
    data_size_kb = len(image_data) / 1024
    # 估算 tokens
    return int(data_size_kb * IMAGE_TOKEN_ESTIMATE_PER_KB)


def estimate_input_tokens(request_data: dict) -> Tuple[int, int, int]:
    """
    估算输入 token 数量，分别统计文本和图片
    
    Args:
        request_data: Claude API 请求数据
        
    Returns:
        Tuple[int, int, int]: (总 tokens, 文本 tokens, 图片 tokens)
    """
    text_tokens = 0
    image_tokens = 0
    
    try:
        # 收集所有文本内容
        text_parts = []
        
        # 统计 system prompt
        system = request_data.get('system', '')
        if system:
            if isinstance(system, str):
                text_parts.append(system)
            elif isinstance(system, list):
                for block in system:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        text_parts.append(block.get('text', ''))
        
        # 统计所有消息内容
        messages = request_data.get('messages', [])
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get('type', '')
                        
                        if block_type == 'text':
                            text_parts.append(block.get('text', ''))
                        elif block_type == 'image':
                            # 统计图片 tokens
                            source = block.get('source', {})
                            if source.get('type') == 'base64':
                                image_data = source.get('data', '')
                                image_tokens += estimate_image_tokens(image_data)
                        elif block_type == 'tool_use':
                            text_parts.append(block.get('name', ''))
                            text_parts.append(json.dumps(block.get('input', {})))
                        elif block_type == 'tool_result':
                            tool_result_content = block.get('content', [])
                            if isinstance(tool_result_content, str):
                                text_parts.append(tool_result_content)
                            elif isinstance(tool_result_content, list):
                                for result_block in tool_result_content:
                                    if isinstance(result_block, dict):
                                        if result_block.get('type') == 'text':
                                            text_parts.append(result_block.get('text', ''))
                                        elif result_block.get('type') == 'image':
                                            # tool_result 中的图片
                                            source = result_block.get('source', {})
                                            if source.get('type') == 'base64':
                                                image_data = source.get('data', '')
                                                image_tokens += estimate_image_tokens(image_data)
                                    elif isinstance(result_block, str):
                                        text_parts.append(result_block)
        
        # 统计 tools 定义
        tools = request_data.get('tools', [])
        for tool in tools:
            text_parts.append(tool.get('name', ''))
            text_parts.append(tool.get('description', ''))
            text_parts.append(json.dumps(tool.get('input_schema', {})))
        
        # 计算文本 tokens
        full_text = '\n'.join(text_parts)
        text_tokens = _count_tokens(full_text)
        
        total_tokens = text_tokens + image_tokens
        
        return total_tokens, text_tokens, image_tokens
        
    except Exception as e:
        logger.warning(f"估算输入 token 失败: {e}")
        return 0, 0, 0


def validate_input_length(
    request_data: dict,
    max_tokens: int = AMAZONQ_MAX_INPUT_TOKENS
) -> Tuple[bool, Optional[str], int]:
    """
    验证输入长度是否在限制范围内
    
    Args:
        request_data: Claude API 请求数据
        max_tokens: 最大允许的 token 数量
        
    Returns:
        Tuple[bool, Optional[str], int]: (是否有效, 错误信息, 估算的 token 数量)
    """
    total_tokens, text_tokens, image_tokens = estimate_input_tokens(request_data)
    
    if total_tokens > max_tokens:
        # 构建详细的错误信息
        error_parts = [f"输入内容过长，超过 Amazon Q 限制"]
        error_parts.append(f"估算总 tokens: {total_tokens:,} (限制: {max_tokens:,})")
        
        if image_tokens > 0:
            error_parts.append(f"其中图片占用: {image_tokens:,} tokens")
            error_parts.append("建议：减少图片数量或压缩图片大小")
        
        if text_tokens > max_tokens * 0.8:
            error_parts.append("建议：减少对话历史或简化 system prompt")
        
        error_message = "。".join(error_parts)
        logger.warning(f"输入验证失败: {error_message}")
        
        return False, error_message, total_tokens
    
    logger.debug(f"输入验证通过: {total_tokens:,} tokens (文本: {text_tokens:,}, 图片: {image_tokens:,})")
    return True, None, total_tokens


def count_images_in_request(request_data: dict) -> int:
    """
    统计请求中的图片数量
    
    Args:
        request_data: Claude API 请求数据
        
    Returns:
        int: 图片数量
    """
    image_count = 0
    
    messages = request_data.get('messages', [])
    for msg in messages:
        content = msg.get('content', '')
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get('type') == 'image':
                        image_count += 1
                    elif block.get('type') == 'tool_result':
                        tool_result_content = block.get('content', [])
                        if isinstance(tool_result_content, list):
                            for result_block in tool_result_content:
                                if isinstance(result_block, dict) and result_block.get('type') == 'image':
                                    image_count += 1
    
    return image_count
