"""
缓存管理模块
实现 Anthropic Prompt Caching 的模拟功能
"""
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, List


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
    """缓存管理器 - 模拟 Anthropic Prompt Caching 行为"""
    
    # Approximate characters per token (rough estimate for mixed content)
    CHARS_PER_TOKEN = 4
    
    # 配置常量
    MIN_TTL_SECONDS = 60           # 最小 TTL: 1 分钟
    MAX_TTL_SECONDS = 604800       # 最大 TTL: 7 天
    DEFAULT_TTL_SECONDS = 86400    # 默认 TTL: 24 小时 (was 300)
    
    MIN_MAX_ENTRIES = 100          # 最小缓存条目数
    MAX_MAX_ENTRIES = 100000       # 最大缓存条目数
    DEFAULT_MAX_ENTRIES = 5000     # 默认缓存条目数 (was 1000)
    
    BATCH_EVICTION_PERCENT = 10    # 批量淘汰百分比
    
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, max_entries: int = DEFAULT_MAX_ENTRIES):
        """
        初始化缓存管理器
        
        Args:
            ttl_seconds: 缓存条目的生存时间（秒），默认 86400 秒（24 小时）
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
    
    def calculate_cache_key(self, content: str) -> str:
        """
        计算缓存键（SHA-256）
        
        Args:
            content: 可缓存的内容字符串
            
        Returns:
            SHA-256 哈希值
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def check_cache(self, key: str, token_count: int) -> CacheResult:
        """
        检查缓存并返回结果
        
        Args:
            key: 缓存键
            token_count: 缓存内容的 token 数量
            
        Returns:
            CacheResult 包含命中状态和 token 统计
        """
        # 先清理过期条目
        self._evict_expired()
        
        now = datetime.now()
        
        if key in self._cache:
            # 缓存命中
            entry = self._cache[key]
            entry.last_accessed = now
            self._stats.hit_count += 1
            return CacheResult(
                is_hit=True,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=entry.token_count
            )
        else:
            # 缓存未命中 - 创建新条目
            self._stats.miss_count += 1
            # 先检查是否需要批量 LRU 淘汰
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
        
        遍历内容列表，为每个创建缓存条目。使用 _estimate_token_count 估算 token 数。
        尊重 max_entries 容量限制。
        
        Args:
            contents: 要预热的内容列表
            
        Returns:
            实际添加的条目数
        """
        added = 0
        now = datetime.now()
        
        for content in contents:
            # 检查是否已达到容量上限
            if len(self._cache) >= self._max_entries:
                break
            
            key = self.calculate_cache_key(content)
            # 只添加不存在的条目
            if key not in self._cache:
                token_count = self._estimate_token_count(content)
                self._cache[key] = CacheEntry(
                    key=key,
                    token_count=token_count,
                    created_at=now,
                    last_accessed=now
                )
                added += 1
        
        return added
    
    def _estimate_token_count(self, text: str) -> int:
        """
        估算文本的 token 数量
        
        使用简单的字符数除以平均字符/token 比率来估算。
        这是一个粗略估计，实际 token 数量取决于具体的 tokenizer。
        
        Args:
            text: 要估算的文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        return max(1, len(text) // self.CHARS_PER_TOKEN)
    
    @property
    def size(self) -> int:
        """当前缓存条目数"""
        return len(self._cache)
    
    @property
    def ttl(self) -> int:
        """当前 TTL 设置（秒）"""
        return self._ttl
    
    @property
    def max_entries(self) -> int:
        """当前最大条目数设置"""
        return self._max_entries
    
    def extract_cacheable_content(self, request_data: Dict[str, Any]) -> Tuple[str, int]:
        """
        从请求中提取可缓存内容和 token 数
        
        解析 system prompt 和 message content blocks 中的 cache_control 标记，
        提取所有标记为可缓存的内容。
        
        Args:
            request_data: Claude API 请求数据字典
            
        Returns:
            Tuple[str, int]: (可缓存内容字符串, token 数量)
            如果没有可缓存内容，返回 ("", 0)
        """
        cacheable_parts: List[str] = []
        
        # 1. 解析 system prompt 中的 cache_control
        system = request_data.get("system")
        if system:
            system_cacheable = self._extract_cacheable_from_system(system)
            if system_cacheable:
                cacheable_parts.append(system_cacheable)
        
        # 2. 解析 messages 中的 cache_control
        messages = request_data.get("messages", [])
        for message in messages:
            message_cacheable = self._extract_cacheable_from_message(message)
            if message_cacheable:
                cacheable_parts.append(message_cacheable)
        
        # 3. 合并所有可缓存内容
        if not cacheable_parts:
            return ("", 0)
        
        combined_content = "\n".join(cacheable_parts)
        token_count = self._estimate_token_count(combined_content)
        
        return (combined_content, token_count)
    
    def _extract_cacheable_from_system(self, system: Any) -> str:
        """
        从 system prompt 中提取可缓存内容
        
        system 可以是:
        - 字符串: 不支持 cache_control
        - 数组: 每个元素可能包含 cache_control
        
        Args:
            system: system prompt (字符串或数组)
            
        Returns:
            可缓存内容字符串，如果没有则返回空字符串
        """
        if isinstance(system, str):
            # 字符串格式不支持 cache_control
            return ""
        
        if not isinstance(system, list):
            return ""
        
        cacheable_texts: List[str] = []
        
        for block in system:
            if not isinstance(block, dict):
                continue
            
            # 检查是否有 cache_control
            cache_control = block.get("cache_control")
            if not cache_control:
                continue
            
            # 验证 cache_control 类型是否为 "ephemeral"
            cache_type = cache_control.get("type") if isinstance(cache_control, dict) else None
            if cache_type != "ephemeral":
                continue
            
            # 提取文本内容
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    cacheable_texts.append(text)
        
        return "\n".join(cacheable_texts)
    
    def _extract_cacheable_from_message(self, message: Dict[str, Any]) -> str:
        """
        从消息中提取可缓存内容
        
        消息的 content 可以是:
        - 字符串: 不支持 cache_control
        - 数组: 每个内容块可能包含 cache_control
        
        Args:
            message: 消息字典
            
        Returns:
            可缓存内容字符串，如果没有则返回空字符串
        """
        content = message.get("content")
        
        if isinstance(content, str):
            # 字符串格式不支持 cache_control
            return ""
        
        if not isinstance(content, list):
            return ""
        
        cacheable_texts: List[str] = []
        
        for block in content:
            if not isinstance(block, dict):
                continue
            
            # 检查是否有 cache_control
            cache_control = block.get("cache_control")
            if not cache_control:
                continue
            
            # 验证 cache_control 类型是否为 "ephemeral"
            cache_type = cache_control.get("type") if isinstance(cache_control, dict) else None
            if cache_type != "ephemeral":
                continue
            
            # 根据内容块类型提取内容
            block_type = block.get("type")
            
            if block_type == "text":
                text = block.get("text", "")
                if text:
                    cacheable_texts.append(text)
            elif block_type == "image":
                # 对于图片，使用 source 的字符串表示
                source = block.get("source", {})
                if source:
                    import json
                    cacheable_texts.append(json.dumps(source, sort_keys=True))
            elif block_type == "tool_use":
                # 对于 tool_use，使用 name 和 input 的组合
                name = block.get("name", "")
                input_data = block.get("input", {})
                if name:
                    import json
                    cacheable_texts.append(f"{name}:{json.dumps(input_data, sort_keys=True)}")
            elif block_type == "tool_result":
                # 对于 tool_result，使用 tool_use_id 和 content
                tool_use_id = block.get("tool_use_id", "")
                result_content = block.get("content", "")
                if tool_use_id:
                    if isinstance(result_content, str):
                        cacheable_texts.append(f"{tool_use_id}:{result_content}")
                    else:
                        import json
                        cacheable_texts.append(f"{tool_use_id}:{json.dumps(result_content, sort_keys=True)}")
        
        return "\n".join(cacheable_texts)
