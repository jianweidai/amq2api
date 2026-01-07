"""
输入验证模块测试
"""
import pytest
from src.processing.input_validator import (
    estimate_input_tokens,
    validate_input_length,
    count_images_in_request,
    estimate_image_tokens,
    AMAZONQ_MAX_INPUT_TOKENS
)


class TestEstimateImageTokens:
    """图片 token 估算测试"""
    
    def test_small_image(self):
        """测试小图片的 token 估算"""
        # 1KB 的 base64 数据
        image_data = "a" * 1024
        tokens = estimate_image_tokens(image_data)
        assert tokens > 0
        assert tokens == 256  # 1KB * 256 tokens/KB
    
    def test_large_image(self):
        """测试大图片的 token 估算"""
        # 100KB 的 base64 数据
        image_data = "a" * (100 * 1024)
        tokens = estimate_image_tokens(image_data)
        assert tokens == 25600  # 100KB * 256 tokens/KB
    
    def test_empty_image(self):
        """测试空图片数据"""
        tokens = estimate_image_tokens("")
        assert tokens == 0


class TestEstimateInputTokens:
    """输入 token 估算测试"""
    
    def test_simple_text_message(self):
        """测试简单文本消息"""
        request_data = {
            "messages": [
                {"role": "user", "content": "Hello, world!"}
            ]
        }
        total, text, image = estimate_input_tokens(request_data)
        assert total > 0
        assert text > 0
        assert image == 0
    
    def test_message_with_system_prompt(self):
        """测试带 system prompt 的消息"""
        request_data = {
            "system": "You are a helpful assistant.",
            "messages": [
                {"role": "user", "content": "Hello!"}
            ]
        }
        total, text, image = estimate_input_tokens(request_data)
        assert total > 0
        assert text > 0
        assert image == 0
    
    def test_message_with_image(self):
        """测试带图片的消息"""
        # 模拟 10KB 的图片
        image_data = "a" * (10 * 1024)
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data
                            }
                        }
                    ]
                }
            ]
        }
        total, text, image = estimate_input_tokens(request_data)
        assert total > 0
        assert text > 0
        assert image > 0
        assert image == 2560  # 10KB * 256 tokens/KB
    
    def test_message_with_tools(self):
        """测试带工具定义的消息"""
        request_data = {
            "messages": [
                {"role": "user", "content": "Use the calculator"}
            ],
            "tools": [
                {
                    "name": "calculator",
                    "description": "A simple calculator",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"}
                        }
                    }
                }
            ]
        }
        total, text, image = estimate_input_tokens(request_data)
        assert total > 0
        assert text > 0
        assert image == 0
    
    def test_message_with_tool_result(self):
        """测试带 tool_result 的消息"""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "test-id",
                            "content": "Result: 42"
                        }
                    ]
                }
            ]
        }
        total, text, image = estimate_input_tokens(request_data)
        assert total > 0
        assert text > 0
    
    def test_system_prompt_as_list(self):
        """测试 system prompt 为列表格式"""
        request_data = {
            "system": [
                {"type": "text", "text": "You are helpful."},
                {"type": "text", "text": "Be concise."}
            ],
            "messages": [
                {"role": "user", "content": "Hi"}
            ]
        }
        total, text, image = estimate_input_tokens(request_data)
        assert total > 0
        assert text > 0


class TestValidateInputLength:
    """输入长度验证测试"""
    
    def test_valid_short_input(self):
        """测试有效的短输入"""
        request_data = {
            "messages": [
                {"role": "user", "content": "Hello!"}
            ]
        }
        is_valid, error, tokens = validate_input_length(request_data)
        assert is_valid is True
        assert error is None
        assert tokens > 0
    
    def test_invalid_long_input(self):
        """测试超长输入"""
        # 创建一个非常长的消息
        long_text = "a" * 500000  # 约 125000 tokens
        request_data = {
            "messages": [
                {"role": "user", "content": long_text}
            ]
        }
        is_valid, error, tokens = validate_input_length(request_data)
        assert is_valid is False
        assert error is not None
        assert "超过" in error or "限制" in error
    
    def test_invalid_large_image(self):
        """测试超大图片"""
        # 创建一个 500KB 的图片（约 128000 tokens）
        image_data = "a" * (500 * 1024)
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's this?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data
                            }
                        }
                    ]
                }
            ]
        }
        is_valid, error, tokens = validate_input_length(request_data)
        assert is_valid is False
        assert error is not None
        assert "图片" in error
    
    def test_custom_max_tokens(self):
        """测试自定义最大 token 限制"""
        request_data = {
            "messages": [
                {"role": "user", "content": "Hello, this is a test message."}
            ]
        }
        # 使用非常小的限制
        is_valid, error, tokens = validate_input_length(request_data, max_tokens=1)
        assert is_valid is False
        assert error is not None


class TestCountImagesInRequest:
    """图片计数测试"""
    
    def test_no_images(self):
        """测试无图片的请求"""
        request_data = {
            "messages": [
                {"role": "user", "content": "Hello!"}
            ]
        }
        count = count_images_in_request(request_data)
        assert count == 0
    
    def test_single_image(self):
        """测试单张图片"""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's this?"},
                        {
                            "type": "image",
                            "source": {"type": "base64", "data": "abc"}
                        }
                    ]
                }
            ]
        }
        count = count_images_in_request(request_data)
        assert count == 1
    
    def test_multiple_images(self):
        """测试多张图片"""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "data": "a"}},
                        {"type": "image", "source": {"type": "base64", "data": "b"}},
                        {"type": "image", "source": {"type": "base64", "data": "c"}}
                    ]
                }
            ]
        }
        count = count_images_in_request(request_data)
        assert count == 3
    
    def test_images_in_tool_result(self):
        """测试 tool_result 中的图片"""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "test",
                            "content": [
                                {"type": "image", "source": {"type": "base64", "data": "x"}}
                            ]
                        }
                    ]
                }
            ]
        }
        count = count_images_in_request(request_data)
        assert count == 1
    
    def test_images_across_messages(self):
        """测试跨消息的图片"""
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "data": "a"}}
                    ]
                },
                {
                    "role": "assistant",
                    "content": "I see an image."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "data": "b"}}
                    ]
                }
            ]
        }
        count = count_images_in_request(request_data)
        assert count == 2
