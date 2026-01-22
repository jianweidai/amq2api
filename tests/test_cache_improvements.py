"""
测试缓存管理器的改进功能

测试范围：
- 阶段 1: 后台清理任务 + 并发安全
- 阶段 2: 内存监控 + 紧急清理
- 阶段 3: 缓存键冲突检测
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from src.processing.cache_manager import CacheManager, CacheResult


class TestPhase1BackgroundCleanup:
    """阶段 1: 后台清理任务 + 并发安全测试"""
    
    @pytest.mark.asyncio
    async def test_background_cleanup_starts_and_stops(self):
        """测试后台清理任务能正常启动和停止"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        # 启动后台清理
        await cache.start_background_cleanup()
        assert cache._cleanup_task is not None
        assert not cache._cleanup_task.done()
        
        # 停止后台清理
        await cache.stop_background_cleanup()
        assert cache._cleanup_task.done()
    
    @pytest.mark.asyncio
    async def test_background_cleanup_removes_expired_entries(self):
        """测试后台清理能自动删除过期条目"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        # 添加一个条目
        key = cache.calculate_cache_key("test content")
        result = await cache.check_cache_async(key, 100, 12)
        assert not result.is_hit
        assert cache.size == 1
        
        # 手动修改 TTL 为 1 秒用于测试
        cache._ttl = 1
        
        # 启动后台清理（间隔设置为 2 秒用于测试）
        cache._cleanup_interval = 2
        await cache.start_background_cleanup()
        
        # 等待 3 秒，让条目过期并被清理
        await asyncio.sleep(3)
        
        # 验证条目已被清理
        assert cache.size == 0
        
        await cache.stop_background_cleanup()
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self):
        """测试并发访问缓存的安全性"""
        cache = CacheManager(ttl_seconds=60, max_entries=1000)
        
        async def access_cache(content: str, token_count: int):
            key = cache.calculate_cache_key(content)
            result = await cache.check_cache_async(key, token_count, len(content))
            return result.is_hit
        
        # 并发访问相同的缓存键
        tasks = [
            access_cache("test content", 100)
            for _ in range(50)
        ]
        results = await asyncio.gather(*tasks)
        
        # 第一次应该是未命中，后续应该是命中
        assert results[0] == False  # 第一次未命中
        assert all(results[1:])  # 后续都命中
        assert cache.size == 1  # 只有一个条目


class TestPhase2MemoryMonitoring:
    """阶段 2: 内存监控 + 紧急清理测试"""
    
    def test_memory_estimation(self):
        """测试内存使用估算"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        # 添加一些条目
        for i in range(10):
            key = cache.calculate_cache_key(f"content {i}")
            cache.check_cache(key, 1000, len(f"content {i}"))
        
        # 获取内存估算
        memory_info = cache.estimate_memory_usage()
        
        assert memory_info['bytes'] > 0
        assert memory_info['mb'] > 0
        assert memory_info['entries'] == 10
        assert memory_info['max_entries'] == 100
        assert 'warning' in memory_info
        assert 'critical' in memory_info
    
    def test_emergency_cleanup(self):
        """测试紧急清理功能"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        # 添加 100 个条目
        for i in range(100):
            key = cache.calculate_cache_key(f"content {i}")
            cache.check_cache(key, 100, len(f"content {i}"))
        
        assert cache.size == 100
        
        # 执行紧急清理（应该删除 50%）
        cleaned = cache.emergency_cleanup()
        
        assert cleaned == 50
        assert cache.size == 50
    
    @pytest.mark.asyncio
    async def test_memory_warning_triggers_batch_eviction(self):
        """测试内存警告触发批量淘汰"""
        # 使用较小的 max_entries 来触发淘汰
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        # 添加条目直到触发淘汰
        for i in range(110):
            content = f"content {i}"
            key = cache.calculate_cache_key(content)
            await cache.check_cache_async(key, 100, len(content))
        
        # 由于批量淘汰，缓存大小应该小于 110
        assert cache.size < 110
        assert cache.size <= 100


class TestPhase3CollisionDetection:
    """阶段 3: 缓存键冲突检测测试"""
    
    @pytest.mark.asyncio
    async def test_cache_key_includes_length(self):
        """测试缓存键包含内容长度"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        content = "test content"
        key = cache.calculate_cache_key(content)
        
        # 验证键格式为 "hash:length"
        assert ':' in key
        parts = key.split(':')
        assert len(parts) == 2
        assert parts[1] == str(len(content))
    
    @pytest.mark.asyncio
    async def test_collision_detection_with_different_lengths(self):
        """测试不同长度内容的冲突检测"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        content1 = "test"
        content2 = "test content"
        
        key1 = cache.calculate_cache_key(content1)
        key2 = cache.calculate_cache_key(content2)
        
        # 添加第一个条目
        result1 = await cache.check_cache_async(key1, 10, len(content1))
        assert not result1.is_hit
        
        # 添加第二个条目（不同长度）
        result2 = await cache.check_cache_async(key2, 20, len(content2))
        assert not result2.is_hit
        
        # 两个条目应该都存在
        assert cache.size == 2
    
    @pytest.mark.asyncio
    async def test_collision_detection_removes_mismatched_entry(self):
        """测试冲突检测会删除长度不匹配的条目"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        content = "test content"
        key = cache.calculate_cache_key(content)
        
        # 添加条目
        result1 = await cache.check_cache_async(key, 100, len(content))
        assert not result1.is_hit
        assert cache.size == 1
        
        # 手动修改缓存条目的长度（模拟冲突）
        cache._cache[key].content_length = 999
        
        # 再次检查缓存，应该检测到冲突并删除旧条目
        result2 = await cache.check_cache_async(key, 100, len(content))
        assert not result2.is_hit  # 应该是未命中（旧条目被删除）
        assert cache.size == 1  # 新条目被添加
        
        # 验证新条目的长度正确
        assert cache._cache[key].content_length == len(content)
    
    def test_backward_compatibility_without_content_length(self):
        """测试向后兼容：不提供 content_length 时跳过冲突检测"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        content = "test content"
        key = cache.calculate_cache_key(content)
        
        # 不提供 content_length（默认为 0）
        result1 = cache.check_cache(key, 100)
        assert not result1.is_hit
        
        # 再次检查，应该命中（没有冲突检测）
        result2 = cache.check_cache(key, 100)
        assert result2.is_hit


class TestIntegration:
    """集成测试：测试所有改进功能协同工作"""
    
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """测试完整的缓存生命周期"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        # 手动修改 TTL 为 2 秒用于测试
        cache._ttl = 2
        
        # 启动后台清理
        cache._cleanup_interval = 1
        await cache.start_background_cleanup()
        
        try:
            # 1. 添加一些条目
            for i in range(10):
                content = f"content {i}"
                key = cache.calculate_cache_key(content)
                result = await cache.check_cache_async(key, 100, len(content))
                assert not result.is_hit
            
            assert cache.size == 10
            
            # 2. 验证缓存命中
            content = "content 5"
            key = cache.calculate_cache_key(content)
            result = await cache.check_cache_async(key, 100, len(content))
            assert result.is_hit
            
            # 3. 检查内存使用
            memory_info = cache.estimate_memory_usage()
            assert memory_info['entries'] == 10
            assert memory_info['mb'] > 0
            
            # 4. 等待条目过期
            await asyncio.sleep(3)
            
            # 5. 验证过期条目被清理
            assert cache.size == 0
            
            # 6. 获取统计信息
            stats = cache.get_statistics()
            assert stats.hit_count > 0
            assert stats.miss_count > 0
            assert stats.eviction_count > 0
            
        finally:
            await cache.stop_background_cleanup()
    
    @pytest.mark.asyncio
    async def test_statistics_tracking(self):
        """测试统计信息跟踪"""
        cache = CacheManager(ttl_seconds=60, max_entries=100)
        
        # 添加条目（未命中）
        for i in range(5):
            content = f"content {i}"
            key = cache.calculate_cache_key(content)
            await cache.check_cache_async(key, 100, len(content))
        
        # 访问已存在的条目（命中）
        for i in range(5):
            content = f"content {i}"
            key = cache.calculate_cache_key(content)
            await cache.check_cache_async(key, 100, len(content))
        
        stats = cache.get_statistics()
        assert stats.miss_count == 5
        assert stats.hit_count == 5
        assert stats.hit_rate == 0.5
        assert stats.total_requests == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
