# Design Document: Prompt Caching

## Overview

本设计文档描述了为 amq2api 代理服务添加 Anthropic Prompt Caching 支持的技术方案。由于后端服务（Amazon Q 和 Gemini）不支持原生的 Prompt Caching，本方案采用模拟缓存的方式，在代理层实现缓存统计功能，使客户端能够获得符合 Claude API 规范的缓存相关响应。

### 核心目标

1. 兼容 Claude API 的 cache_control 参数
2. 返回符合规范的缓存 token 统计信息
3. 模拟缓存命中/未命中行为
4. 可配置的缓存模拟开关

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
│  │  1. Parse cache_control from request                     │   │
│  │  2. Extract cacheable content prefix                     │   │
│  │  3. Calculate cache key (SHA-256)                        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     cache_manager.py (NEW)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   CacheManager                            │   │
│  │  - in_memory_cache: Dict[str, CacheEntry]                │   │
│  │  - check_cache(key) -> CacheResult                       │   │
│  │  - update_cache(key, token_count)                        │   │
│  │  - evict_expired()                                       │   │
│  │  - evict_lru()                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   stream_handler_new.py                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              AmazonQStreamHandler                         │   │
│  │  - cache_creation_input_tokens: int                      │   │
│  │  - cache_read_input_tokens: int                          │   │
│  │  - Build SSE events with cache stats                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     usage_tracker.py                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  record_usage() - 新增 cache token 字段                   │   │
│  │  get_usage_summary() - 包含 cache 统计                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. CacheManager (新模块: cache_manager.py)

负责管理缓存状态和计算缓存统计。

```python
@dataclass
class CacheEntry:
    """缓存条目"""
    key: str                    # SHA-256 hash of cacheable content
    token_count: int            # Number of tokens in cached content
    created_at: datetime        # When the cache entry was created
    last_accessed: datetime     # Last access time for LRU
    
@dataclass
class CacheResult:
    """缓存查询结果"""
    is_hit: bool                          # Whether cache was hit
    cache_creation_input_tokens: int      # Tokens for cache creation (miss)
    cache_read_input_tokens: int          # Tokens read from cache (hit)

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 1000):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
    
    def calculate_cache_key(self, content: str) -> str:
        """计算缓存键（SHA-256）"""
        
    def check_cache(self, key: str, token_count: int) -> CacheResult:
        """检查缓存并返回结果"""
        
    def extract_cacheable_content(self, request_data: dict) -> tuple[str, int]:
        """从请求中提取可缓存内容和 token 数"""
        
    def _evict_expired(self) -> None:
        """清理过期条目"""
        
    def _evict_lru(self) -> None:
        """LRU 淘汰"""
```

### 2. 请求解析增强 (models.py)

扩展现有模型以支持 cache_control。

```python
@dataclass
class CacheControl:
    """缓存控制"""
    type: Literal["ephemeral"] = "ephemeral"

@dataclass
class ClaudeTextContentWithCache:
    """带缓存控制的文本内容块"""
    type: Literal["text"] = "text"
    text: str = ""
    cache_control: Optional[CacheControl] = None
```

### 3. 流处理器增强 (stream_handler_new.py)

在 AmazonQStreamHandler 中添加缓存统计字段。

```python
class AmazonQStreamHandler:
    def __init__(self, ...):
        # 新增缓存统计字段
        self.cache_creation_input_tokens: int = 0
        self.cache_read_input_tokens: int = 0
```

### 4. 使用量追踪增强 (usage_tracker.py)

扩展数据库 schema 和记录函数。

```python
def record_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,  # 新增
    cache_read_input_tokens: int = 0,       # 新增
    account_id: Optional[str] = None,
    channel: str = "amazonq"
) -> str:
    """记录使用量（含缓存统计）"""
```

### 5. SSE 事件构建增强 (parser.py)

更新事件构建函数以包含缓存统计。

```python
def build_claude_message_start_event(
    conversation_id: str,
    model: str,
    input_tokens: int,
    cache_creation_input_tokens: int = 0,  # 新增
    cache_read_input_tokens: int = 0        # 新增
) -> str:
    """构建 message_start 事件"""
```

## Data Models

### CacheEntry

| 字段 | 类型 | 说明 |
|------|------|------|
| key | str | SHA-256 哈希键 |
| token_count | int | 缓存内容的 token 数 |
| created_at | datetime | 创建时间 |
| last_accessed | datetime | 最后访问时间 |

### Usage Table Schema (更新)

```sql
-- SQLite
ALTER TABLE usage ADD COLUMN cache_creation_input_tokens INTEGER DEFAULT 0;
ALTER TABLE usage ADD COLUMN cache_read_input_tokens INTEGER DEFAULT 0;

-- MySQL
ALTER TABLE amq2api_usage ADD COLUMN cache_creation_input_tokens INT DEFAULT 0;
ALTER TABLE amq2api_usage ADD COLUMN cache_read_input_tokens INT DEFAULT 0;
```

### Claude API Usage Response Format

```json
{
  "input_tokens": 100,
  "output_tokens": 50,
  "cache_creation_input_tokens": 1000,
  "cache_read_input_tokens": 0
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: cache_control parsing consistency

*For any* request containing cache_control in system prompt or message content blocks, parsing the request should successfully extract the cache_control field without error, and the extracted cache_control should match the original input.

**Validates: Requirements 1.1, 1.2**

### Property 2: Usage statistics completeness

*For any* generated response, the usage statistics object should contain all required fields: input_tokens, output_tokens, cache_creation_input_tokens, and cache_read_input_tokens, and serializing then deserializing the usage object should produce an equivalent object.

**Validates: Requirements 2.1, 2.2, 2.4, 6.1, 6.2, 6.3**

### Property 3: Cache miss reports creation tokens

*For any* request with cache_control that results in a cache miss, the response should report the cacheable tokens as cache_creation_input_tokens and cache_read_input_tokens should be zero.

**Validates: Requirements 3.1**

### Property 4: Cache hit reports read tokens

*For any* request with cache_control where the identical cached prefix was previously cached and TTL has not expired, the response should report the cacheable tokens as cache_read_input_tokens and cache_creation_input_tokens should be zero.

**Validates: Requirements 3.2**

### Property 5: Cache TTL expiration

*For any* cached entry, after the TTL period has elapsed, subsequent requests with the same cache key should be treated as cache misses and report cache_creation_input_tokens.

**Validates: Requirements 3.3**

### Property 6: Cache key determinism

*For any* cacheable content string, the calculated cache key should be the SHA-256 hash of that content, and calculating the key multiple times for the same content should produce the same result.

**Validates: Requirements 3.4, 7.4**

### Property 7: Database cache field persistence

*For any* usage record stored in the database, the record should contain cache_creation_input_tokens and cache_read_input_tokens fields, and reading the record back should return the same values that were stored.

**Validates: Requirements 5.1, 5.2**

### Property 8: Usage summary cache aggregation

*For any* set of usage records with cache statistics, the usage summary should correctly aggregate cache_creation_input_tokens and cache_read_input_tokens across all records.

**Validates: Requirements 5.3**

### Property 9: LRU eviction on capacity

*For any* cache state where the entry count exceeds MAX_CACHE_ENTRIES, the cache should evict entries until the count is at or below MAX_CACHE_ENTRIES, and the evicted entries should be the least recently used ones.

**Validates: Requirements 7.1**

### Property 10: LRU access time update

*For any* cache entry that is accessed (cache hit), the entry's last_accessed time should be updated to the current time, affecting its position in the LRU ordering.

**Validates: Requirements 7.2**

## Error Handling

### 1. 缓存解析错误

- 如果 cache_control 格式无效，记录警告日志并忽略缓存控制
- 继续正常处理请求，不返回缓存统计

### 2. 缓存管理器错误

- 如果缓存操作失败，记录错误日志
- 回退到无缓存模式，所有 token 计入 input_tokens

### 3. 数据库迁移错误

- 如果新字段添加失败，记录错误并继续运行
- 缓存统计将不会被持久化，但不影响核心功能

### 4. 内存压力

- 当缓存条目过多时，自动触发 LRU 淘汰
- 设置合理的 MAX_CACHE_ENTRIES 默认值（1000）

## Testing Strategy

### 单元测试

使用 pytest 进行单元测试：

1. **cache_manager.py 测试**
   - 测试缓存键计算
   - 测试缓存命中/未命中逻辑
   - 测试 TTL 过期
   - 测试 LRU 淘汰

2. **请求解析测试**
   - 测试 cache_control 解析
   - 测试可缓存内容提取

3. **SSE 事件测试**
   - 测试 message_start 事件包含缓存字段
   - 测试 message_delta 事件包含缓存字段

### 属性测试

使用 **hypothesis** 库进行属性测试：

- 每个属性测试运行至少 100 次迭代
- 测试标注格式：`**Feature: prompt-caching, Property {number}: {property_text}**`

### 集成测试

1. 端到端测试完整的缓存流程
2. 测试缓存模拟开关的效果
3. 测试数据库记录的正确性
