# Requirements Document

## Introduction

本功能旨在优化现有的 Prompt Caching 模拟模块，通过更激进的缓存策略来提高缓存命中率。当前的缓存配置（5 分钟 TTL）过于保守，导致缓存命中率较低。本次优化将延长缓存保存时间、改进缓存失效策略，并增加缓存预热和访问续期机制，以显著提升缓存效率。

## Glossary

- **Cache_Manager**: 缓存管理器模块，负责管理缓存状态和计算缓存统计
- **TTL (Time To Live)**: 缓存条目的生存时间
- **LRU (Least Recently Used)**: 最近最少使用淘汰策略
- **Cache_Hit_Rate**: 缓存命中率，命中次数除以总请求次数
- **Access_Renewal**: 访问续期，每次访问缓存时延长其 TTL
- **Sliding_Window_TTL**: 滑动窗口 TTL，基于最后访问时间而非创建时间计算过期

## Requirements

### Requirement 1: 延长默认缓存 TTL

**User Story:** As a system operator, I want longer default cache TTL, so that cache entries remain valid for extended periods and improve hit rate.

#### Acceptance Criteria

1. WHEN the Cache_Manager is initialized without custom TTL THEN the Cache_Manager SHALL use a default TTL of 86400 seconds (24 hours)
2. WHEN CACHE_TTL_SECONDS environment variable is set THEN the Cache_Manager SHALL use the specified TTL value
3. WHEN the TTL is configured THEN the Cache_Manager SHALL accept values between 60 seconds and 604800 seconds (7 days)

### Requirement 2: 实现滑动窗口 TTL

**User Story:** As a system operator, I want cache entries to extend their lifetime on access, so that frequently used entries stay in cache longer.

#### Acceptance Criteria

1. WHEN a cache entry is accessed (cache hit) THEN the Cache_Manager SHALL reset the entry's TTL countdown from the current time
2. WHEN checking if an entry is expired THEN the Cache_Manager SHALL compare current time against last_accessed plus TTL, not created_at plus TTL
3. WHEN an entry is accessed multiple times within TTL THEN the Cache_Manager SHALL keep the entry alive as long as accesses continue within TTL intervals

### Requirement 3: 增加最大缓存条目数

**User Story:** As a system operator, I want larger cache capacity, so that more unique prompts can be cached simultaneously.

#### Acceptance Criteria

1. WHEN the Cache_Manager is initialized without custom max_entries THEN the Cache_Manager SHALL use a default of 5000 entries
2. WHEN MAX_CACHE_ENTRIES environment variable is set THEN the Cache_Manager SHALL use the specified value
3. WHEN the max_entries is configured THEN the Cache_Manager SHALL accept values between 100 and 100000

### Requirement 4: 优化 LRU 淘汰策略

**User Story:** As a system operator, I want smarter cache eviction, so that valuable cache entries are preserved while less useful ones are removed.

#### Acceptance Criteria

1. WHEN cache capacity is exceeded THEN the Cache_Manager SHALL evict entries based on last_accessed time (LRU)
2. WHEN multiple entries need eviction THEN the Cache_Manager SHALL evict up to 10% of max_entries in a single batch to reduce eviction frequency
3. WHEN evicting entries THEN the Cache_Manager SHALL prioritize removing entries with lower token counts among equally old entries

### Requirement 5: 添加缓存统计监控

**User Story:** As a system operator, I want to monitor cache performance, so that I can tune cache parameters for optimal hit rate.

#### Acceptance Criteria

1. WHEN cache operations occur THEN the Cache_Manager SHALL track total hits, misses, and evictions
2. WHEN querying cache statistics THEN the Cache_Manager SHALL return hit_count, miss_count, eviction_count, and calculated hit_rate
3. WHEN the cache is cleared or reset THEN the Cache_Manager SHALL reset all statistics counters

### Requirement 6: 支持缓存预热

**User Story:** As a system operator, I want to pre-populate cache with common prompts, so that initial requests can benefit from caching.

#### Acceptance Criteria

1. WHEN a list of content strings is provided for prewarming THEN the Cache_Manager SHALL create cache entries for each without marking them as accessed
2. WHEN prewarming entries THEN the Cache_Manager SHALL use estimated token counts based on content length
3. WHEN prewarming would exceed max_entries THEN the Cache_Manager SHALL only add entries up to the capacity limit

