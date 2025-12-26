"""
Unit tests for extract_cacheable_content method in cache_manager module.
"""
import pytest
from src.processing.cache_manager import CacheManager


class TestExtractCacheableContent:
    """Tests for extract_cacheable_content method"""
    
    def test_empty_request_returns_empty(self):
        """Empty request should return empty content and zero tokens"""
        cm = CacheManager()
        content, token_count = cm.extract_cacheable_content({})
        
        assert content == ""
        assert token_count == 0
    
    def test_no_cache_control_returns_empty(self):
        """Request without cache_control should return empty content"""
        cm = CacheManager()
        request_data = {
            "system": "You are a helpful assistant.",
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == ""
        assert token_count == 0
    
    def test_system_string_no_cache_control(self):
        """System as string doesn't support cache_control"""
        cm = CacheManager()
        request_data = {
            "system": "You are a helpful assistant."
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == ""
        assert token_count == 0
    
    def test_system_array_with_cache_control(self):
        """System as array with cache_control should extract content"""
        cm = CacheManager()
        request_data = {
            "system": [
                {
                    "type": "text",
                    "text": "You are a helpful assistant.",
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == "You are a helpful assistant."
        assert token_count > 0

    
    def test_system_array_without_cache_control(self):
        """System as array without cache_control should return empty"""
        cm = CacheManager()
        request_data = {
            "system": [
                {
                    "type": "text",
                    "text": "You are a helpful assistant."
                }
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == ""
        assert token_count == 0
    
    def test_message_content_with_cache_control(self):
        """Message content with cache_control should extract content"""
        cm = CacheManager()
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "This is cached content.",
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                }
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == "This is cached content."
        assert token_count > 0
    
    def test_message_string_content_no_cache_control(self):
        """Message with string content doesn't support cache_control"""
        cm = CacheManager()
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello world"
                }
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == ""
        assert token_count == 0
    
    def test_multiple_cache_control_blocks(self):
        """Multiple blocks with cache_control should all be extracted"""
        cm = CacheManager()
        request_data = {
            "system": [
                {
                    "type": "text",
                    "text": "System prompt part 1.",
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": "System prompt part 2.",
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "User message cached.",
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                }
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert "System prompt part 1." in content
        assert "System prompt part 2." in content
        assert "User message cached." in content
        assert token_count > 0
    
    def test_invalid_cache_control_type_ignored(self):
        """cache_control with non-ephemeral type should be ignored"""
        cm = CacheManager()
        request_data = {
            "system": [
                {
                    "type": "text",
                    "text": "This should be ignored.",
                    "cache_control": {"type": "invalid_type"}
                }
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == ""
        assert token_count == 0
    
    def test_mixed_cached_and_uncached_content(self):
        """Only content with cache_control should be extracted"""
        cm = CacheManager()
        request_data = {
            "system": [
                {
                    "type": "text",
                    "text": "Cached system prompt.",
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": "Uncached system prompt."
                }
            ]
        }
        content, token_count = cm.extract_cacheable_content(request_data)
        
        assert content == "Cached system prompt."
        assert "Uncached system prompt." not in content
    
    def test_token_count_estimation(self):
        """Token count should be roughly proportional to content length"""
        cm = CacheManager()
        short_request = {
            "system": [
                {
                    "type": "text",
                    "text": "Short",
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        }
        long_request = {
            "system": [
                {
                    "type": "text",
                    "text": "This is a much longer text that should have more tokens.",
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        }
        
        _, short_tokens = cm.extract_cacheable_content(short_request)
        _, long_tokens = cm.extract_cacheable_content(long_request)
        
        assert long_tokens > short_tokens
