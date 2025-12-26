"""测试 CacheStatistics 数据类"""
from src.processing.cache_manager import CacheStatistics


def test_default_values():
    """测试默认值"""
    stats = CacheStatistics()
    assert stats.hit_count == 0
    assert stats.miss_count == 0
    assert stats.eviction_count == 0
    assert stats.hit_rate == 0.0
    assert stats.total_requests == 0


def test_with_values():
    """测试带值的情况"""
    stats = CacheStatistics(hit_count=7, miss_count=3, eviction_count=2)
    assert stats.hit_count == 7
    assert stats.miss_count == 3
    assert stats.eviction_count == 2
    assert stats.hit_rate == 0.7  # 7 / (7 + 3)
    assert stats.total_requests == 10


def test_hit_rate_calculation():
    """测试命中率计算"""
    # 50% hit rate
    stats = CacheStatistics(hit_count=5, miss_count=5)
    assert stats.hit_rate == 0.5
    
    # 100% hit rate
    stats = CacheStatistics(hit_count=10, miss_count=0)
    assert stats.hit_rate == 1.0
    
    # 0% hit rate
    stats = CacheStatistics(hit_count=0, miss_count=10)
    assert stats.hit_rate == 0.0


if __name__ == "__main__":
    test_default_values()
    test_with_values()
    test_hit_rate_calculation()
    print("All CacheStatistics tests passed!")


# ============================================
# CacheManager 统计集成测试
# ============================================

from src.processing.cache_manager import CacheManager


def test_cache_manager_initial_stats():
    """测试 CacheManager 初始统计为零"""
    cm = CacheManager()
    stats = cm.get_statistics()
    assert stats.hit_count == 0
    assert stats.miss_count == 0
    assert stats.eviction_count == 0
    assert stats.hit_rate == 0.0


def test_cache_manager_miss_count():
    """测试缓存未命中时 miss_count 增加"""
    cm = CacheManager()
    key1 = cm.calculate_cache_key('content1')
    key2 = cm.calculate_cache_key('content2')
    
    cm.check_cache(key1, 100)
    cm.check_cache(key2, 200)
    
    stats = cm.get_statistics()
    assert stats.miss_count == 2
    assert stats.hit_count == 0


def test_cache_manager_hit_count():
    """测试缓存命中时 hit_count 增加"""
    cm = CacheManager()
    key = cm.calculate_cache_key('content')
    
    # First access - miss
    cm.check_cache(key, 100)
    # Second access - hit
    cm.check_cache(key, 100)
    # Third access - hit
    cm.check_cache(key, 100)
    
    stats = cm.get_statistics()
    assert stats.miss_count == 1
    assert stats.hit_count == 2
    assert stats.hit_rate == 2/3


def test_cache_manager_clear_resets_stats():
    """测试 clear() 重置统计"""
    cm = CacheManager()
    key = cm.calculate_cache_key('content')
    
    cm.check_cache(key, 100)
    cm.check_cache(key, 100)
    
    stats = cm.get_statistics()
    assert stats.miss_count == 1
    assert stats.hit_count == 1
    
    cm.clear()
    
    stats = cm.get_statistics()
    assert stats.hit_count == 0
    assert stats.miss_count == 0
    assert stats.eviction_count == 0


def test_cache_manager_eviction_count():
    """测试淘汰时 eviction_count 增加"""
    # 使用小容量触发淘汰
    cm = CacheManager(max_entries=100)
    
    # 填满缓存
    for i in range(100):
        key = cm.calculate_cache_key(f'content{i}')
        cm.check_cache(key, 10)
    
    stats = cm.get_statistics()
    assert stats.eviction_count == 0
    
    # 添加一个新条目，触发批量淘汰
    key = cm.calculate_cache_key('new_content')
    cm.check_cache(key, 10)
    
    stats = cm.get_statistics()
    # 批量淘汰 10% = 10 个条目
    assert stats.eviction_count == 10


# ============================================
# CacheManager 便捷属性测试
# ============================================


def test_cache_manager_size_property():
    """测试 size 属性返回当前缓存条目数"""
    cm = CacheManager()
    
    # 初始为空
    assert cm.size == 0
    
    # 添加条目后
    key1 = cm.calculate_cache_key('content1')
    cm.check_cache(key1, 100)
    assert cm.size == 1
    
    key2 = cm.calculate_cache_key('content2')
    cm.check_cache(key2, 200)
    assert cm.size == 2
    
    # 清空后
    cm.clear()
    assert cm.size == 0


def test_cache_manager_ttl_property():
    """测试 ttl 属性返回当前 TTL 设置"""
    # 默认值
    cm = CacheManager()
    assert cm.ttl == CacheManager.DEFAULT_TTL_SECONDS
    
    # 自定义值
    cm2 = CacheManager(ttl_seconds=3600)
    assert cm2.ttl == 3600


def test_cache_manager_max_entries_property():
    """测试 max_entries 属性返回当前最大条目数设置"""
    # 默认值
    cm = CacheManager()
    assert cm.max_entries == CacheManager.DEFAULT_MAX_ENTRIES
    
    # 自定义值
    cm2 = CacheManager(max_entries=1000)
    assert cm2.max_entries == 1000
