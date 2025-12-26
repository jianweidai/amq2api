"""
测试缓存预热功能
"""
import pytest
from src.processing.cache_manager import CacheManager


class TestPrewarm:
    """测试 prewarm 方法"""
    
    def test_prewarm_adds_entries(self):
        """测试预热添加条目"""
        manager = CacheManager(ttl_seconds=3600, max_entries=1000)
        contents = ["content1", "content2", "content3"]
        
        added = manager.prewarm(contents)
        
        assert added == 3
        assert len(manager._cache) == 3
    
    def test_prewarm_returns_added_count(self):
        """测试预热返回实际添加数量"""
        manager = CacheManager(ttl_seconds=3600, max_entries=1000)
        contents = ["hello world", "test content"]
        
        added = manager.prewarm(contents)
        
        assert added == 2
    
    def test_prewarm_respects_capacity_limit(self):
        """测试预热尊重容量限制"""
        manager = CacheManager(ttl_seconds=3600, max_entries=100)
        # 创建超过容量的内容列表
        contents = [f"content_{i}" for i in range(150)]
        
        added = manager.prewarm(contents)
        
        assert added == 100
        assert len(manager._cache) == 100
    
    def test_prewarm_skips_duplicates(self):
        """测试预热跳过重复内容"""
        manager = CacheManager(ttl_seconds=3600, max_entries=1000)
        contents = ["same", "same", "same", "different"]
        
        added = manager.prewarm(contents)
        
        assert added == 2  # "same" 只添加一次 + "different"
        assert len(manager._cache) == 2
    
    def test_prewarm_empty_list(self):
        """测试预热空列表"""
        manager = CacheManager(ttl_seconds=3600, max_entries=1000)
        
        added = manager.prewarm([])
        
        assert added == 0
        assert len(manager._cache) == 0
    
    def test_prewarm_estimates_token_count(self):
        """测试预热使用 token 估算"""
        manager = CacheManager(ttl_seconds=3600, max_entries=1000)
        content = "a" * 100  # 100 字符，约 25 tokens
        
        manager.prewarm([content])
        
        key = manager.calculate_cache_key(content)
        entry = manager._cache[key]
        assert entry.token_count == 25  # 100 / 4 = 25
    
    def test_prewarm_with_existing_cache(self):
        """测试在已有缓存的情况下预热"""
        manager = CacheManager(ttl_seconds=3600, max_entries=100)
        # 先添加一些条目
        manager.check_cache(manager.calculate_cache_key("existing"), 10)
        
        contents = ["new1", "new2"]
        added = manager.prewarm(contents)
        
        assert added == 2
        assert len(manager._cache) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
