# Implementation Plan: Cache Optimization

## Overview

本实现计划将优化现有的缓存管理器，通过更激进的缓存策略来提高缓存命中率。主要改动包括延长默认 TTL、实现滑动窗口 TTL、增加缓存容量、优化 LRU 淘汰策略、添加缓存统计和预热功能。

## Tasks

- [x] 1. 添加 CacheStatistics 数据类
  - 在 cache_manager.py 中添加 CacheStatistics dataclass
  - 包含 hit_count, miss_count, eviction_count 字段
  - 添加 hit_rate 和 total_requests 计算属性
  - _Requirements: 5.1, 5.2_

- [x] 2. 更新 CacheManager 配置常量和初始化
  - [x] 2.1 更新默认值和范围常量
    - DEFAULT_TTL_SECONDS: 300 → 86400 (24小时)
    - MAX_TTL_SECONDS: 86400 → 604800 (7天)
    - DEFAULT_MAX_ENTRIES: 1000 → 5000
    - 添加 MIN_TTL_SECONDS = 60, MIN_MAX_ENTRIES = 100, MAX_MAX_ENTRIES = 100000
    - _Requirements: 1.1, 1.3, 3.1, 3.3_
  - [x] 2.2 添加配置验证逻辑
    - 在 __init__ 中验证 ttl_seconds 范围 [60, 604800]
    - 在 __init__ 中验证 max_entries 范围 [100, 100000]
    - 超出范围时抛出 ValueError
    - _Requirements: 1.3, 3.3_
  - [ ]* 2.3 Write property test for configuration validation
    - **Property 2: Configuration Validation**
    - **Validates: Requirements 1.3, 3.3**

- [x] 3. 实现滑动窗口 TTL
  - [x] 3.1 修改 _evict_expired 方法
    - 使用 last_accessed + TTL 判断过期，而非 created_at + TTL
    - _Requirements: 2.2_
  - [x] 3.2 修改 check_cache 方法的缓存命中逻辑
    - 命中时更新 entry.last_accessed 为当前时间
    - _Requirements: 2.1_
  - [ ]* 3.3 Write property test for sliding window TTL
    - **Property 1: Sliding Window TTL**
    - **Validates: Requirements 2.1, 2.2, 2.3**

- [x] 4. 实现批量 LRU 淘汰
  - [x] 4.1 添加 BATCH_EVICTION_PERCENT 常量 (10%)
    - _Requirements: 4.2_
  - [x] 4.2 重写 _evict_lru 为 _evict_lru_batch
    - 计算淘汰数量: max(1, len(cache) * 10 / 100)
    - 按 (last_accessed, token_count) 排序
    - 淘汰最旧且最小的条目
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ]* 4.3 Write property test for LRU eviction
    - **Property 3: LRU Eviction Correctness**
    - **Validates: Requirements 4.1**
  - [ ]* 4.4 Write property test for batch eviction with token priority
    - **Property 4: Batch Eviction with Token Priority**
    - **Validates: Requirements 4.2, 4.3**

- [x] 5. 集成缓存统计
  - [x] 5.1 在 CacheManager 中添加 _stats 字段
    - 初始化为 CacheStatistics()
    - _Requirements: 5.1_
  - [x] 5.2 在 check_cache 中更新统计
    - 命中时增加 hit_count
    - 未命中时增加 miss_count
    - _Requirements: 5.1_
  - [x] 5.3 在淘汰方法中更新 eviction_count
    - _Requirements: 5.1_
  - [x] 5.4 添加 get_statistics() 和 clear() 方法
    - get_statistics() 返回当前统计
    - clear() 清空缓存并重置统计
    - _Requirements: 5.2, 5.3_
  - [ ]* 5.5 Write property test for statistics accuracy
    - **Property 5: Statistics Accuracy**
    - **Validates: Requirements 5.1, 5.2**

- [x] 6. 实现缓存预热功能
  - [x] 6.1 添加 prewarm(contents: List[str]) 方法
    - 遍历内容列表，为每个创建缓存条目
    - 使用 _estimate_token_count 估算 token 数
    - 尊重 max_entries 容量限制
    - 返回实际添加的条目数
    - _Requirements: 6.1, 6.2, 6.3_
  - [ ]* 6.2 Write property test for prewarm behavior
    - **Property 6: Prewarm Behavior**
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 7. 更新配置模块
  - [x] 7.1 更新 config.py 中的默认值
    - cache_ttl_seconds: 300 → 86400
    - max_cache_entries: 1000 → 5000
    - _Requirements: 1.1, 3.1_

- [x] 8. Checkpoint - 确保所有测试通过
  - 运行所有现有测试确保兼容性
  - 运行新增的属性测试
  - 如有问题请询问用户

- [x] 9. 添加便捷属性方法
  - 添加 size, ttl, max_entries 属性
  - 方便外部查询缓存状态
  - _Requirements: 5.2_

- [x] 10. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 滑动窗口 TTL 是提高命中率的关键改进
- 批量淘汰减少了频繁淘汰的开销
- 统计功能帮助监控缓存效率
