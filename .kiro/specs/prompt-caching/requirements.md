# Requirements Document

## Introduction

本功能为 amq2api 代理服务添加 Anthropic Prompt Caching 支持。Prompt Caching 是 Anthropic 提供的一项功能，允许缓存请求中的前缀部分（如 system prompt、对话历史），从而降低成本和延迟。由于后端（Amazon Q 和 Gemini）不支持真正的缓存，本功能将模拟缓存行为，在响应中返回符合 Claude API 规范的缓存统计信息。

## Glossary

- **Prompt Caching**: Anthropic 的提示缓存功能，通过缓存请求前缀来减少重复处理
- **cache_control**: Claude API 中用于标记需要缓存内容的控制字段
- **cache_creation_input_tokens**: 首次创建缓存时消耗的 token 数量
- **cache_read_input_tokens**: 从缓存读取时消耗的 token 数量
- **input_tokens**: 未缓存的输入 token 数量
- **ephemeral**: 临时缓存类型，TTL 约 5 分钟
- **Proxy Service**: 本项目的代理服务（amq2api）
- **Upstream Backend**: 后端服务（Amazon Q 或 Gemini）

## Requirements

### Requirement 1

**User Story:** As a Claude API client developer, I want the proxy to accept cache_control parameters in requests, so that my existing code using Prompt Caching can work without modification.

#### Acceptance Criteria

1. WHEN a request contains cache_control in system prompt blocks THEN the Proxy Service SHALL accept and parse the cache_control field without error
2. WHEN a request contains cache_control in message content blocks THEN the Proxy Service SHALL accept and parse the cache_control field without error
3. WHEN cache_control contains type "ephemeral" THEN the Proxy Service SHALL recognize it as a valid cache type
4. WHEN a request does not contain cache_control THEN the Proxy Service SHALL process the request normally without caching behavior

### Requirement 2

**User Story:** As a Claude API client developer, I want the proxy to return cache-related token statistics in responses, so that I can track caching behavior and costs.

#### Acceptance Criteria

1. WHEN a response is generated THEN the Proxy Service SHALL include cache_creation_input_tokens in the usage statistics
2. WHEN a response is generated THEN the Proxy Service SHALL include cache_read_input_tokens in the usage statistics
3. WHEN the request contains cacheable content (with cache_control) THEN the Proxy Service SHALL calculate and return appropriate cache token counts
4. WHEN serializing usage statistics to JSON THEN the Proxy Service SHALL output cache_creation_input_tokens and cache_read_input_tokens fields

### Requirement 3

**User Story:** As a system operator, I want the proxy to simulate cache hit/miss behavior, so that clients receive realistic caching statistics even though the backend doesn't support caching.

#### Acceptance Criteria

1. WHEN a request with cache_control is received for the first time (cache miss) THEN the Proxy Service SHALL report tokens as cache_creation_input_tokens
2. WHEN a request with identical cached prefix is received within TTL (cache hit) THEN the Proxy Service SHALL report tokens as cache_read_input_tokens
3. WHEN the cache TTL (5 minutes) expires THEN the Proxy Service SHALL treat subsequent requests as cache misses
4. WHEN calculating cache keys THEN the Proxy Service SHALL use a hash of the cacheable content prefix

### Requirement 4

**User Story:** As a system operator, I want the caching simulation to be configurable, so that I can enable or disable it based on deployment needs.

#### Acceptance Criteria

1. WHEN ENABLE_CACHE_SIMULATION environment variable is set to "true" THEN the Proxy Service SHALL enable cache simulation
2. WHEN ENABLE_CACHE_SIMULATION is not set or set to "false" THEN the Proxy Service SHALL disable cache simulation and report all tokens as input_tokens
3. WHEN CACHE_TTL_SECONDS environment variable is set THEN the Proxy Service SHALL use the specified TTL value
4. WHEN CACHE_TTL_SECONDS is not set THEN the Proxy Service SHALL use the default TTL of 300 seconds (5 minutes)

### Requirement 5

**User Story:** As a developer, I want the cache statistics to be recorded in the usage tracking system, so that I can analyze caching patterns and costs.

#### Acceptance Criteria

1. WHEN recording usage to database THEN the Proxy Service SHALL store cache_creation_input_tokens as a separate field
2. WHEN recording usage to database THEN the Proxy Service SHALL store cache_read_input_tokens as a separate field
3. WHEN querying usage summary THEN the Proxy Service SHALL include aggregated cache token statistics
4. WHEN the usage table schema is updated THEN the Proxy Service SHALL migrate existing data with zero values for new cache fields

### Requirement 6

**User Story:** As a Claude API client developer, I want the message_start event to include cache statistics, so that I can see caching information at the beginning of the response stream.

#### Acceptance Criteria

1. WHEN generating message_start SSE event THEN the Proxy Service SHALL include cache_creation_input_tokens in the usage object
2. WHEN generating message_start SSE event THEN the Proxy Service SHALL include cache_read_input_tokens in the usage object
3. WHEN generating message_delta SSE event with final usage THEN the Proxy Service SHALL include cache token statistics

### Requirement 7

**User Story:** As a system operator, I want the cache to be stored efficiently, so that memory usage remains bounded even with many unique cache entries.

#### Acceptance Criteria

1. WHEN the cache entry count exceeds MAX_CACHE_ENTRIES (default 1000) THEN the Proxy Service SHALL evict the oldest entries
2. WHEN a cache entry is accessed THEN the Proxy Service SHALL update its last access time for LRU eviction
3. WHEN the system starts THEN the Proxy Service SHALL initialize an empty in-memory cache
4. WHEN calculating cache key THEN the Proxy Service SHALL use SHA-256 hash of the cacheable content
