# Design Document: Cache Optimization

## Overview

本设计文档描述了对现有 Prompt Caching 模拟模块的优化方案。主要目标是通过更激进的缓存策略来显著提高缓存命中率。

### 核心优化点

1. **延长默认 TTL**: 从 5 分钟延长到 1 小时
2. **滑动窗口 TTL**: 基于最后访问时间计算过期，而非创建时间
3. **增加缓存容量**: 从 1000 条增加到 5000 条
4. **智能 LRU 淘汰**: 批量淘汰 + 优先淘汰小 token 条目
5. **缓存统计监控**: 追踪命中率等关键指标
6. **缓存预热**: 支持预先填充常用 prompt

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude API Client                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ Request with cache_control
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Request Handler                          │   │
│  │  - Extract cacheable content                              │   │
│  │  - Query CacheManager                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     cache_manager.py (ENHANCED)                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   CacheManager                            │   │
│  │  - ttl_seconds: 3600 (default, was 300)                  │   │
│  │  - max_entries: 5000 (default, was 1000)                 │   │
│  │  - Sliding window TTL (based on last_accessed)           │   │
│  │  - Batch LRU eviction (10% at a time)                    │   │
│  │  - Statistics tracking (hits, misses, evictions)         │   │
│  │  - Prewarm support                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   CacheStatistics                         │   │
│  │  - hit_count: int                                        │   │
│  │  - miss_count: int                                       │   │
│  │  - eviction_count: int                                   │   │
│  │  - hit_rate: float (calculated)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         config.py                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  - CACHE_TTL_SECONDS: 3600 (default)                     │   │
│  │  - MAX_CACHE_ENTRIES: 5000 (default)                     │   │
│  │  - CACHE_BATCH_EVICTION_PERCENT: 10 (default)            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. CacheEntry (增强)

```python
@dataclass
class CacheEntry:
    """缓存条目"""
    key: str                    # SHA-256 hash of cacheable content
    token_count: int            # Number of tokens in cached content
    created_at: datetime        # When the cache entry was created
    last_accessed: datetime     # Last access time (used for sliding window TTL)
```

### 2. CacheStatistics (新增)

```python
@dataclass
class CacheStatistics:
    """缓存统计信息"""
    hit_count: int = 0          # 缓存命中次数
    miss_count: int = 0         # 缓存未命中次数
    eviction_count: int = 0     # 淘汰次数
    
    @property
    def hit_rate(self) -> float:
        """计算缓存命中率"""
        total = self.hit_count + self.miss_count
        if total == 0:
            return 0.0
        return self.hit_count / total
    
    @property
    def total_requests(self) -> int:
        """总请求数"""
        return self.hit_count + self.miss_count
```

### 3. CacheManager (增强)

```python
class CacheManager:
    """缓存管理器 - 优化版"""
    
    # 配置常量
    MIN_TTL_SECONDS = 60           # 最小 TTL: 1 分钟
    MAX_TTL_SECONDS = 604800       # 最大 TTL: 7 天
    DEFAULT_TTL_SECONDS = 86400    # 默认 TTL: 24 小时 (was 300)
    
    MIN_MAX_ENTRIES = 100          # 最小缓存条目数
    MAX_MAX_ENTRIES = 100000       # 最大缓存条目数
    DEFAULT_MAX_ENTRIES = 5000     # 默认缓存条目数 (was 1000)
    
    BATCH_EVICTION_PERCENT = 10    # 批量淘汰百分比
    
    def __init__(
        self, 
        ttl_seconds: int = DEFAULT_TTL_SECONDS, 
        max_entries: int = DEFAULT_MAX_ENTRIES
    ):
        """
        初始化缓存管理器
        
        Args:
            ttl_seconds: 缓存条目的生存时间（秒），默认 3600 秒（1 小时）
            max_entries: 最大缓存条目数，默认 5000
            
        Raises:
            ValueError: 如果参数超出有效范围
        """
        # 验证并设置 TTL
        if not self.MIN_TTL_SECONDS <= ttl_seconds <= self.MAX_TTL_SECONDS:
            raise ValueError(
                f"ttl_seconds must be between {self.MIN_TTL_SECONDS} and {self.MAX_TTL_SECONDS}"
            )
        
        # 验证并设置 max_entries
        if not self.MIN_MAX_ENTRIES <= max_entries <= self.MAX_MAX_ENTRIES:
            raise ValueError(
                f"max_entries must be between {self.MIN_MAX_ENTRIES} and {self.MAX_MAX_ENTRIES}"
            )
        
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._stats = CacheStatistics()
    
    def check_cache(self, key: str, token_count: int) -> CacheResult:
        """
        检查缓存并返回结果（使用滑动窗口 TTL）
        
        Args:
            key: 缓存键
            token_count: 缓存内容的 token 数量
            
        Returns:
            CacheResult 包含命中状态和 token 统计
        """
        # 先清理过期条目（基于 last_accessed + TTL）
        self._evict_expired()
        
        now = datetime.now()
        
        if key in self._cache:
            # 缓存命中 - 更新 last_accessed（滑动窗口）
            entry = self._cache[key]
            entry.last_accessed = now  # 重置 TTL 倒计时
            self._stats.hit_count += 1
            return CacheResult(
                is_hit=True,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=entry.token_count
            )
        else:
            # 缓存未命中 - 创建新条目
            self._stats.miss_count += 1
            
            # 检查是否需要批量 LRU 淘汰
            if len(self._cache) >= self._max_entries:
                self._evict_lru_batch()
            
            self._cache[key] = CacheEntry(
                key=key,
                token_count=token_count,
                created_at=now,
                last_accessed=now
            )
            return CacheResult(
                is_hit=False,
                cache_creation_input_tokens=token_count,
                cache_read_input_tokens=0
            )
    
    def _evict_expired(self) -> None:
        """
        清理过期条目（基于滑动窗口 TTL）
        
        使用 last_accessed + TTL 判断过期，而非 created_at + TTL
        """
        now = datetime.now()
        expired_keys = [
            key for key, entry in self._cache.items()
            if (now - entry.last_accessed).total_seconds() > self._ttl
        ]
        for key in expired_keys:
            del self._cache[key]
            self._stats.eviction_count += 1
    
    def _evict_lru_batch(self) -> None:
        """
        批量 LRU 淘汰
        
        淘汰 BATCH_EVICTION_PERCENT% 的条目，优先淘汰：
        1. 最久未访问的条目
        2. 在访问时间相近时，优先淘汰 token 数较少的条目
        """
        if not self._cache:
            return
        
        # 计算需要淘汰的数量
        evict_count = max(1, len(self._cache) * self.BATCH_EVICTION_PERCENT // 100)
        
        # 按 (last_accessed, token_count) 排序，最旧且最小的优先淘汰
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: (x[1].last_accessed, x[1].token_count)
        )
        
        # 淘汰前 evict_count 个条目
        for key, _ in sorted_entries[:evict_count]:
            del self._cache[key]
            self._stats.eviction_count += 1
    
    def get_statistics(self) -> CacheStatistics:
        """获取缓存统计信息"""
        return self._stats
    
    def clear(self) -> None:
        """清空缓存并重置统计"""
        self._cache.clear()
        self._stats = CacheStatistics()
    
    def prewarm(self, contents: List[str]) -> int:
        """
        预热缓存
        
        Args:
            contents: 要预热的内容列表
            
        Returns:
            实际添加的条目数
        """
        added = 0
        now = datetime.now()
        
        for content in contents:
            if len(self._cache) >= self._max_entries:
                break
            
            key = self.calculate_cache_key(content)
            if key not in self._cache:
                token_count = self._estimate_token_count(content)
                self._cache[key] = CacheEntry(
                    key=key,
                    token_count=token_count,
                    created_at=now,
                    last_accessed=now  # 预热时设置为当前时间
                )
                added += 1
        
        return added
    
    @property
    def size(self) -> int:
        """当前缓存条目数"""
        return len(self._cache)
    
    @property
    def ttl(self) -> int:
        """当前 TTL 设置"""
        return self._ttl
    
    @property
    def max_entries(self) -> int:
        """当前最大条目数设置"""
        return self._max_entries
```

### 4. 配置更新 (config.py)

```python
# Prompt Caching 模拟配置（优化后的默认值）
enable_cache_simulation: bool = False
cache_ttl_seconds: int = 86400     # 默认 24 小时 (was 300)
max_cache_entries: int = 5000      # 默认 5000 条 (was 1000)
```

## Data Models

### CacheEntry

| 字段 | 类型 | 说明 |
|------|------|------|
| key | str | SHA-256 哈希键 |
| token_count | int | 缓存内容的 token 数 |
| created_at | datetime | 创建时间 |
| last_accessed | datetime | 最后访问时间（用于滑动窗口 TTL） |

### CacheStatistics

| 字段 | 类型 | 说明 |
|------|------|------|
| hit_count | int | 缓存命中次数 |
| miss_count | int | 缓存未命中次数 |
| eviction_count | int | 淘汰次数 |
| hit_rate | float | 计算属性：命中率 |
| total_requests | int | 计算属性：总请求数 |

### 配置参数对比

| 参数 | 旧默认值 | 新默认值 | 说明 |
|------|----------|----------|------|
| CACHE_TTL_SECONDS | 300 (5分钟) | 86400 (24小时) | 缓存生存时间 |
| MAX_CACHE_ENTRIES | 1000 | 5000 | 最大缓存条目数 |
| MAX_TTL_SECONDS | 86400 (24小时) | 604800 (7天) | 最大可配置 TTL |
| TTL 计算方式 | created_at + TTL | last_accessed + TTL | 滑动窗口 |
| 淘汰策略 | 单条淘汰 | 批量淘汰 10% | 减少淘汰频率 |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Sliding Window TTL

*For any* cache entry, its expiration should be calculated based on `last_accessed + TTL`, not `created_at + TTL`. When an entry is accessed, its `last_accessed` time should be updated to the current time, effectively resetting the TTL countdown. As long as accesses continue within TTL intervals, the entry should remain valid indefinitely.

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: Configuration Validation

*For any* TTL value, it should be accepted if and only if it falls within the range [60, 604800] seconds (1 minute to 7 days). *For any* max_entries value, it should be accepted if and only if it falls within the range [100, 100000]. Values outside these ranges should raise a ValueError.

**Validates: Requirements 1.3, 3.3**

### Property 3: LRU Eviction Correctness

*For any* cache at maximum capacity, when a new entry is added, the least recently accessed entry (based on `last_accessed` time) should be evicted. The evicted entry should always be the one with the oldest `last_accessed` timestamp.

**Validates: Requirements 4.1**

### Property 4: Batch Eviction with Token Priority

*For any* cache that triggers eviction, the eviction should remove approximately 10% of max_entries in a single batch. Among entries with similar `last_accessed` times, entries with lower `token_count` should be evicted first.

**Validates: Requirements 4.2, 4.3**

### Property 5: Statistics Accuracy

*For any* sequence of cache operations (hits, misses, evictions), the statistics counters should accurately reflect the number of each operation type. The `hit_rate` should equal `hit_count / (hit_count + miss_count)`, and `total_requests` should equal `hit_count + miss_count`.

**Validates: Requirements 5.1, 5.2**

### Property 6: Prewarm Behavior

*For any* list of content strings provided for prewarming, the cache should create entries for each unique content up to the capacity limit. Prewarmed entries should have `token_count` estimated from content length. If prewarming would exceed `max_entries`, only entries up to the capacity limit should be added.

**Validates: Requirements 6.1, 6.2, 6.3**

## Error Handling

### 1. 配置验证错误

- 如果 TTL 超出 [60, 86400] 范围，抛出 `ValueError`
- 如果 max_entries 超出 [100, 100000] 范围，抛出 `ValueError`
- 错误消息应明确说明有效范围

### 2. 缓存操作错误

- 缓存操作应该是线程安全的（如果需要多线程支持）
- 任何缓存操作失败都应该记录日志并优雅降级

### 3. 预热错误

- 如果预热内容为空，返回 0
- 如果预热超出容量，只添加到容量上限

## Testing Strategy

### 单元测试

使用 pytest 进行单元测试：

1. **默认值测试**
   - 测试默认 TTL 为 3600 秒
   - 测试默认 max_entries 为 5000

2. **配置验证测试**
   - 测试有效范围内的配置
   - 测试超出范围的配置抛出异常

3. **滑动窗口 TTL 测试**
   - 测试访问后 TTL 重置
   - 测试基于 last_accessed 的过期判断

4. **批量淘汰测试**
   - 测试淘汰数量为 10%
   - 测试淘汰优先级（时间 + token 数）

5. **统计测试**
   - 测试命中/未命中计数
   - 测试命中率计算

6. **预热测试**
   - 测试预热添加条目
   - 测试预热容量限制

### 属性测试

使用 **hypothesis** 库进行属性测试：

- 每个属性测试运行至少 100 次迭代
- 测试标注格式：`**Feature: cache-optimization, Property {number}: {property_text}**`

### 集成测试

1. 测试与现有代码的兼容性
2. 测试环境变量配置加载
3. 测试长时间运行下的缓存行为
