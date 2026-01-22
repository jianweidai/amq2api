"""
测试自动缓存功能

验证改进后的缓存管理器能够自动缓存 system prompt、历史消息和 tools
"""
import pytest
from src.processing.cache_manager import CacheManager


class TestAutoCacheSystem:
    """测试自动缓存 system prompt"""
    
    def test_auto_cache_string_system(self):
        """测试自动缓存字符串格式的 system prompt"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_system=True,
            min_cacheable_tokens=10  # 降低阈值用于测试
        )
        
        request1 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant. " * 50,  # 足够长
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        # 第一次请求 - 未命中
        content1, tokens1 = cache.extract_cacheable_content(request1)
        assert content1 != ""
        assert tokens1 > 0
        assert "[SYSTEM]" in content1
        
        key1 = cache.calculate_cache_key(content1)
        result1 = cache.check_cache(key1, tokens1, len(content1))
        assert not result1.is_hit
        
        # 第二次请求（相同 system） - 命中
        request2 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant. " * 50,
            "messages": [
                {"role": "user", "content": "How are you?"}  # 不同的消息
            ]
        }
        
        content2, tokens2 = cache.extract_cacheable_content(request2)
        key2 = cache.calculate_cache_key(content2)
        result2 = cache.check_cache(key2, tokens2, len(content2))
        
        assert result2.is_hit  # 应该命中！
        assert key1 == key2  # 缓存键相同
    
    def test_auto_cache_array_system(self):
        """测试自动缓存数组格式的 system prompt"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_system=True,
            min_cacheable_tokens=10
        )
        
        request = {
            "model": "claude-sonnet-4.5",
            "system": [
                {"type": "text", "text": "You are a helpful assistant. " * 50}
            ],
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        content, tokens = cache.extract_cacheable_content(request)
        assert content != ""
        assert "[SYSTEM]" in content
        assert tokens > 0
    
    def test_disable_auto_cache_system(self):
        """测试禁用自动缓存 system prompt"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_system=False  # 禁用
        )
        
        request = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant. " * 50,
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        content, tokens = cache.extract_cacheable_content(request)
        assert content == ""  # 应该没有提取到内容
        assert tokens == 0


class TestAutoCacheHistory:
    """测试自动缓存历史消息"""
    
    def test_auto_cache_history_messages(self):
        """测试自动缓存历史消息（除了最后一条）"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_history=True,
            min_cacheable_tokens=10
        )
        
        request1 = {
            "model": "claude-sonnet-4.5",
            "messages": [
                {"role": "user", "content": "Question 1: " + "context " * 50},
                {"role": "assistant", "content": "Answer 1"},
                {"role": "user", "content": "Question 2"}  # 最后一条，不缓存
            ]
        }
        
        content1, tokens1 = cache.extract_cacheable_content(request1)
        assert content1 != ""
        assert "[HISTORY]" in content1
        assert "Question 1" in content1
        assert "Answer 1" in content1
        assert "Question 2" not in content1  # 最后一条不应该在缓存中
        
        key1 = cache.calculate_cache_key(content1)
        result1 = cache.check_cache(key1, tokens1, len(content1))
        assert not result1.is_hit
        
        # 第二次请求（相同历史，不同的最后一条）
        request2 = {
            "model": "claude-sonnet-4.5",
            "messages": [
                {"role": "user", "content": "Question 1: " + "context " * 50},
                {"role": "assistant", "content": "Answer 1"},
                {"role": "user", "content": "Question 3"}  # 不同的最后一条
            ]
        }
        
        content2, tokens2 = cache.extract_cacheable_content(request2)
        key2 = cache.calculate_cache_key(content2)
        result2 = cache.check_cache(key2, tokens2, len(content2))
        
        assert result2.is_hit  # 应该命中！
        assert key1 == key2
    
    def test_single_message_no_history_cache(self):
        """测试单条消息不缓存历史"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_history=True,
            auto_cache_system=False,  # 禁用 system 缓存
            min_cacheable_tokens=10
        )
        
        request = {
            "model": "claude-sonnet-4.5",
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        content, tokens = cache.extract_cacheable_content(request)
        assert content == ""  # 单条消息，没有历史，不缓存


class TestAutoCacheTools:
    """测试自动缓存 tools 定义"""
    
    def test_auto_cache_tools(self):
        """测试自动缓存 tools 定义"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_tools=True,
            auto_cache_system=False,
            auto_cache_history=False,
            min_cacheable_tokens=10
        )
        
        tools = [
            {
                "name": "get_weather",
                "description": "Get weather information",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"}
                    }
                }
            }
        ]
        
        request1 = {
            "model": "claude-sonnet-4.5",
            "tools": tools,
            "messages": [
                {"role": "user", "content": "What's the weather?"}
            ]
        }
        
        content1, tokens1 = cache.extract_cacheable_content(request1)
        assert content1 != ""
        assert "[TOOLS]" in content1
        assert "get_weather" in content1
        
        key1 = cache.calculate_cache_key(content1)
        result1 = cache.check_cache(key1, tokens1, len(content1))
        assert not result1.is_hit
        
        # 第二次请求（相同 tools）
        request2 = {
            "model": "claude-sonnet-4.5",
            "tools": tools,
            "messages": [
                {"role": "user", "content": "What's the temperature?"}  # 不同消息
            ]
        }
        
        content2, tokens2 = cache.extract_cacheable_content(request2)
        key2 = cache.calculate_cache_key(content2)
        result2 = cache.check_cache(key2, tokens2, len(content2))
        
        assert result2.is_hit  # 应该命中！


class TestCombinedAutoCache:
    """测试组合自动缓存"""
    
    def test_combined_system_and_history(self):
        """测试同时缓存 system 和 history"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_system=True,
            auto_cache_history=True,
            min_cacheable_tokens=10
        )
        
        request = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant. " * 20,
            "messages": [
                {"role": "user", "content": "Question 1: " + "context " * 20},
                {"role": "assistant", "content": "Answer 1"},
                {"role": "user", "content": "Question 2"}
            ]
        }
        
        content, tokens = cache.extract_cacheable_content(request)
        assert content != ""
        assert "[SYSTEM]" in content
        assert "[HISTORY]" in content
        assert "You are a helpful assistant" in content
        assert "Question 1" in content
        assert "Question 2" not in content
    
    def test_cache_control_takes_priority(self):
        """测试 cache_control 标记优先于自动缓存"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_system=True,
            min_cacheable_tokens=10
        )
        
        # 有 cache_control 标记的请求
        request = {
            "model": "claude-sonnet-4.5",
            "system": [
                {
                    "type": "text",
                    "text": "You are a helpful assistant. " * 50,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        content, tokens = cache.extract_cacheable_content(request)
        assert content != ""
        # 应该使用 cache_control 提取的内容，不应该有 [SYSTEM] 标记
        assert "[SYSTEM]" not in content
        assert "You are a helpful assistant" in content


class TestMinCacheableTokens:
    """测试最小可缓存 token 数限制"""
    
    def test_content_too_short(self):
        """测试内容太短时不缓存"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_system=True,
            min_cacheable_tokens=1000  # 设置较高的阈值
        )
        
        request = {
            "model": "claude-sonnet-4.5",
            "system": "Short system prompt",  # 太短
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        content, tokens = cache.extract_cacheable_content(request)
        assert content == ""  # 内容太短，不缓存
        assert tokens == 0
    
    def test_content_long_enough(self):
        """测试内容足够长时缓存"""
        cache = CacheManager(
            ttl_seconds=60,
            max_entries=100,
            auto_cache_system=True,
            min_cacheable_tokens=100
        )
        
        request = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant. " * 50,  # 足够长
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        content, tokens = cache.extract_cacheable_content(request)
        assert content != ""
        assert tokens >= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
