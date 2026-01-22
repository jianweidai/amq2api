"""
缓存管理模块
实现 Anthropic Prompt Caching 的模拟功能

改进历史:
- 阶段 1: 添加后台清理任务 + 并发安全 (asyncio.Lock)
- 阶段 2: 添加内存监控 + 紧急清理机制
- 阶段 3: 添加缓存键冲突检测（长度校验）
"""
import hashlib
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, List

logger = logging.getLogger(__name__)


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
    content_length: int = 0     # 阶段 3: 内容长度（用于冲突检测）


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
    CLEANUP_INTERVAL_SECONDS = 300  # 后台清理间隔: 5 分钟
    
    # 阶段 2: 内存监控配置
    MEMORY_WARNING_THRESHOLD_MB = 100   # 内存警告阈值: 100MB
    MEMORY_CRITICAL_THRESHOLD_MB = 200  # 内存临界阈值: 200MB
    EMERGENCY_EVICTION_PERCENT = 50     # 紧急清理百分比: 50%
    
    def __init__(
        self, 
        ttl_seconds: int = DEFAULT_TTL_SECONDS, 
        max_entries: int = DEFAULT_MAX_ENTRIES,
        auto_cache_system: bool = True,
        auto_cache_history: bool = True,
        auto_cache_tools: bool = True,
        min_cacheable_tokens: int = 1024
    ):
        """
        初始化缓存管理器
        
        Args:
            ttl_seconds: 缓存条目的生存时间（秒），默认 86400 秒（24 小时）
            max_entries: 最大缓存条目数，默认 5000
            auto_cache_system: 自动缓存 system prompt（默认 True）
            auto_cache_history: 自动缓存历史消息（默认 True）
            auto_cache_tools: 自动缓存 tools 定义（默认 True）
            min_cacheable_tokens: 最小可缓存 token 数（默认 1024，符合 Anthropic 要求）
            
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
        
        # 自动缓存配置
        self._auto_cache_system = auto_cache_system
        self._auto_cache_history = auto_cache_history
        self._auto_cache_tools = auto_cache_tools
        self._min_cacheable_tokens = min_cacheable_tokens
        
        # 阶段 1: 并发安全 - 添加异步锁
        self._lock = asyncio.Lock()
        
        # 阶段 1: 后台清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = self.CLEANUP_INTERVAL_SECONDS
    
    def calculate_cache_key(self, content: str) -> str:
        """
        计算缓存键（SHA-256 + 长度）
        
        阶段 3: 将内容长度编码到键中，用于冲突检测
        
        Args:
            content: 可缓存的内容字符串
            
        Returns:
            格式为 "hash:length" 的缓存键
        """
        hash_value = hashlib.sha256(content.encode('utf-8')).hexdigest()
        # 将长度编码到键中，格式: hash:length
        return f"{hash_value}:{len(content)}"
    
    async def start_background_cleanup(self):
        """
        阶段 1: 启动后台清理任务
        
        定期清理过期缓存条目，避免在请求处理时阻塞
        """
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(self._cleanup_interval)
                    await self._evict_expired_async()
                    logger.info(
                        f"🧹 后台清理完成 - 当前缓存: {len(self._cache)}/{self._max_entries} 条目, "
                        f"命中率: {self._stats.hit_rate * 100:.2f}%"
                    )
                except asyncio.CancelledError:
                    logger.info("后台清理任务已取消")
                    raise
                except Exception as e:
                    logger.error(f"后台清理任务异常: {e}", exc_info=True)
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(f"✅ 缓存后台清理任务已启动 (间隔: {self._cleanup_interval}s)")
    
    async def stop_background_cleanup(self):
        """
        阶段 1: 停止后台清理任务
        """
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("✅ 缓存后台清理任务已停止")
    
    async def check_cache_async(self, key: str, token_count: int, content_length: int = 0) -> CacheResult:
        """
        阶段 1: 异步版本的缓存检查（带并发安全）
        阶段 3: 添加内容长度参数用于冲突检测
        
        Args:
            key: 缓存键（格式: hash:length）
            token_count: 缓存内容的 token 数量
            content_length: 内容长度（用于冲突检测）
            
        Returns:
            CacheResult 包含命中状态和 token 统计
        """
        async with self._lock:
            now = datetime.now()
            
            if key in self._cache:
                entry = self._cache[key]
                
                # 阶段 3: 二次校验 - 检查内容长度是否匹配
                if content_length > 0:
                    # 从键中提取预期长度
                    try:
                        expected_length = int(key.split(':')[1])
                        if entry.content_length != expected_length:
                            # 检测到哈希冲突！
                            logger.warning(
                                f"🚨 检测到缓存键冲突: {key[:16]}... "
                                f"(存储长度: {entry.content_length}, 预期长度: {expected_length})"
                            )
                            # 删除旧条目，视为未命中
                            del self._cache[key]
                            self._stats.miss_count += 1
                            # 继续创建新条目（下面的 else 分支）
                        else:
                            # 长度匹配，真正的缓存命中
                            entry.last_accessed = now
                            self._stats.hit_count += 1
                            return CacheResult(
                                is_hit=True,
                                cache_creation_input_tokens=0,
                                cache_read_input_tokens=entry.token_count
                            )
                    except (IndexError, ValueError):
                        # 键格式不正确，视为未命中
                        logger.warning(f"⚠️ 缓存键格式错误: {key}")
                        del self._cache[key]
                        self._stats.miss_count += 1
                else:
                    # 没有提供 content_length，跳过冲突检测（向后兼容）
                    entry.last_accessed = now
                    self._stats.hit_count += 1
                    return CacheResult(
                        is_hit=True,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=entry.token_count
                    )
            
            # 缓存未命中或冲突 - 创建新条目
            if key not in self._cache:  # 确保不是从冲突检测跳转过来的
                self._stats.miss_count += 1
            
            # 阶段 2: 在添加新条目前检查内存使用
            if len(self._cache) >= self._max_entries:
                memory_info = self.estimate_memory_usage()
                
                if memory_info['critical']:
                    logger.error(f"🚨 内存使用达到临界值: {memory_info['mb']}MB，执行紧急清理")
                    self.emergency_cleanup()
                elif memory_info['warning']:
                    logger.warning(f"⚠️ 内存使用接近阈值: {memory_info['mb']}MB，执行批量淘汰")
                    self._evict_lru_batch()
                else:
                    self._evict_lru_batch()
            
            self._cache[key] = CacheEntry(
                key=key,
                token_count=token_count,
                created_at=now,
                last_accessed=now,
                content_length=content_length  # 阶段 3: 存储内容长度
            )
            return CacheResult(
                is_hit=False,
                cache_creation_input_tokens=token_count,
                cache_read_input_tokens=0
            )
    
    def check_cache(self, key: str, token_count: int, content_length: int = 0) -> CacheResult:
        """
        同步版本的缓存检查（保留向后兼容）
        阶段 3: 添加内容长度参数用于冲突检测
        
        注意: 推荐使用 check_cache_async() 以获得更好的并发性能
        
        Args:
            key: 缓存键（格式: hash:length）
            token_count: 缓存内容的 token 数量
            content_length: 内容长度（用于冲突检测）
            
        Returns:
            CacheResult 包含命中状态和 token 统计
        """
        # 阶段 1: 移除同步清理，由后台任务处理
        # self._evict_expired()  # 已移除
        
        now = datetime.now()
        
        if key in self._cache:
            entry = self._cache[key]
            
            # 阶段 3: 二次校验 - 检查内容长度是否匹配
            if content_length > 0:
                try:
                    expected_length = int(key.split(':')[1])
                    if entry.content_length != expected_length:
                        # 检测到哈希冲突！
                        logger.warning(
                            f"🚨 检测到缓存键冲突: {key[:16]}... "
                            f"(存储长度: {entry.content_length}, 预期长度: {expected_length})"
                        )
                        del self._cache[key]
                        self._stats.miss_count += 1
                        # 继续创建新条目
                    else:
                        # 长度匹配，真正的缓存命中
                        entry.last_accessed = now
                        self._stats.hit_count += 1
                        return CacheResult(
                            is_hit=True,
                            cache_creation_input_tokens=0,
                            cache_read_input_tokens=entry.token_count
                        )
                except (IndexError, ValueError):
                    logger.warning(f"⚠️ 缓存键格式错误: {key}")
                    del self._cache[key]
                    self._stats.miss_count += 1
            else:
                # 没有提供 content_length，跳过冲突检测
                entry.last_accessed = now
                self._stats.hit_count += 1
                return CacheResult(
                    is_hit=True,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=entry.token_count
                )
        
        # 缓存未命中或冲突 - 创建新条目
        if key not in self._cache:
            self._stats.miss_count += 1
        
        # 先检查是否需要批量 LRU 淘汰
        if len(self._cache) >= self._max_entries:
            self._evict_lru_batch()
        
        self._cache[key] = CacheEntry(
            key=key,
            token_count=token_count,
            created_at=now,
            last_accessed=now,
            content_length=content_length  # 阶段 3: 存储内容长度
        )
        return CacheResult(
            is_hit=False,
            cache_creation_input_tokens=token_count,
            cache_read_input_tokens=0
        )
    
    async def _evict_expired_async(self) -> None:
        """
        阶段 1: 异步版本的过期清理（带并发安全）
        
        使用 last_accessed + TTL 判断过期，而非 created_at + TTL
        """
        async with self._lock:
            now = datetime.now()
            expired_keys = [
                key for key, entry in self._cache.items()
                if (now - entry.last_accessed).total_seconds() > self._ttl
            ]
            for key in expired_keys:
                del self._cache[key]
                self._stats.eviction_count += 1
            
            if expired_keys:
                logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")
    
    def _evict_expired(self) -> None:
        """
        清理过期条目（基于滑动窗口 TTL）
        
        注意: 此方法已被后台清理任务替代，保留仅用于向后兼容
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
    
    def estimate_memory_usage(self) -> Dict[str, Any]:
        """
        阶段 2: 估算缓存内存使用
        
        Returns:
            包含内存使用信息的字典:
            - bytes: 总字节数
            - mb: MB 数（保留2位小数）
            - entries: 缓存条目数
            - warning: 是否达到警告阈值
            - critical: 是否达到临界阈值
        """
        total_bytes = 0
        
        for key, entry in self._cache.items():
            # 估算每个条目的内存占用
            # key (64 字节 SHA-256 hex string)
            total_bytes += sys.getsizeof(key)
            # CacheEntry 对象本身
            total_bytes += sys.getsizeof(entry)
            # token_count 粗略估算（假设每个 token 4 字节）
            total_bytes += entry.token_count * 4
        
        mb = total_bytes / (1024 * 1024)
        
        return {
            'bytes': total_bytes,
            'mb': round(mb, 2),
            'entries': len(self._cache),
            'max_entries': self._max_entries,
            'warning': mb > self.MEMORY_WARNING_THRESHOLD_MB,
            'critical': mb > self.MEMORY_CRITICAL_THRESHOLD_MB
        }
    
    def emergency_cleanup(self) -> int:
        """
        阶段 2: 紧急清理 - 清除 50% 的缓存
        
        在内存使用达到临界值时调用，强制清理一半的缓存条目
        
        Returns:
            清理的条目数
        """
        if not self._cache:
            return 0
        
        evict_count = len(self._cache) * self.EMERGENCY_EVICTION_PERCENT // 100
        evict_count = max(1, evict_count)  # 至少清理 1 个
        
        # 按访问时间排序，删除最旧的 50%
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].last_accessed
        )
        
        cleaned = 0
        for key, _ in sorted_entries[:evict_count]:
            del self._cache[key]
            self._stats.eviction_count += 1
            cleaned += 1
        
        logger.warning(f"🚨 紧急清理完成：删除 {cleaned} 条缓存（{self.EMERGENCY_EVICTION_PERCENT}%）")
        return cleaned
    
    def get_statistics(self) -> CacheStatistics:
        """获取缓存统计信息"""
        return self._stats
    
    def export_statistics(self) -> Dict[str, Any]:
        """
        导出详细统计信息（用于 dashboard 显示）
        
        Returns:
            包含统计、配置、内存使用等完整信息的字典
        """
        memory_info = self.estimate_memory_usage()
        
        return {
            "enabled": True,
            "stats": {
                "hit_count": self._stats.hit_count,
                "miss_count": self._stats.miss_count,
                "hit_rate": round(self._stats.hit_rate * 100, 2),
                "hit_rate_raw": self._stats.hit_rate,
                "eviction_count": self._stats.eviction_count,
                "total_requests": self._stats.total_requests,
            },
            "config": {
                "ttl_seconds": self._ttl,
                "max_entries": self._max_entries,
                "auto_cache_system": self._auto_cache_system,
                "auto_cache_history": self._auto_cache_history,
                "auto_cache_tools": self._auto_cache_tools,
                "min_cacheable_tokens": self._min_cacheable_tokens,
            },
            "memory": {
                "bytes": memory_info['bytes'],
                "mb": memory_info['mb'],
                "warning": memory_info['warning'],
                "critical": memory_info['critical'],
                "warning_threshold_mb": self.MEMORY_WARNING_THRESHOLD_MB,
                "critical_threshold_mb": self.MEMORY_CRITICAL_THRESHOLD_MB,
            },
            "cache": {
                "size": self.size,
                "max_entries": self._max_entries,
                "usage_percent": round((self.size / self._max_entries) * 100, 2) if self._max_entries > 0 else 0,
            }
        }
    
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
                    last_accessed=now,
                    content_length=len(content)  # 阶段 3: 存储内容长度
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
        
        改进策略：
        1. 优先提取带 cache_control 标记的内容（兼容 Anthropic 标准）
        2. 自动缓存 system prompt（如果启用）
        3. 自动缓存历史消息（如果启用）
        4. 自动缓存 tools 定义（如果启用）
        
        Args:
            request_data: Claude API 请求数据字典
            
        Returns:
            Tuple[str, int]: (可缓存内容字符串, token 数量)
            如果没有可缓存内容，返回 ("", 0)
        """
        cacheable_parts: List[str] = []
        
        # 1. 优先提取带 cache_control 标记的内容（保持向后兼容）
        system = request_data.get("system")
        if system:
            system_cacheable = self._extract_cacheable_from_system(system)
            if system_cacheable:
                cacheable_parts.append(system_cacheable)
        
        messages = request_data.get("messages", [])
        for message in messages:
            message_cacheable = self._extract_cacheable_from_message(message)
            if message_cacheable:
                cacheable_parts.append(message_cacheable)
        
        # 2. 如果没有找到带 cache_control 的内容，使用自动缓存策略
        if not cacheable_parts:
            # 2.1 自动缓存 system prompt
            if self._auto_cache_system and system:
                system_text = self._extract_system_text(system)
                if system_text:
                    cacheable_parts.append(f"[SYSTEM]\n{system_text}")
            
            # 2.2 自动缓存历史消息（除了最后一条）
            if self._auto_cache_history and len(messages) > 1:
                history_text = self._extract_history_text(messages[:-1])
                if history_text:
                    cacheable_parts.append(f"[HISTORY]\n{history_text}")
            
            # 2.3 自动缓存 tools 定义
            if self._auto_cache_tools:
                tools = request_data.get("tools")
                if tools:
                    import json
                    tools_text = json.dumps(tools, sort_keys=True, ensure_ascii=False)
                    cacheable_parts.append(f"[TOOLS]\n{tools_text}")
        
        # 3. 合并所有可缓存内容
        if not cacheable_parts:
            return ("", 0)
        
        combined_content = "\n---\n".join(cacheable_parts)
        token_count = self._estimate_token_count(combined_content)
        
        # 4. 检查是否满足最小 token 要求
        if token_count < self._min_cacheable_tokens:
            logger.debug(f"可缓存内容太少（{token_count} tokens < {self._min_cacheable_tokens}），跳过缓存")
            return ("", 0)
        
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
    
    def _extract_system_text(self, system: Any) -> str:
        """
        提取 system prompt 的文本内容（不依赖 cache_control）
        
        Args:
            system: system prompt (字符串或数组)
            
        Returns:
            system prompt 文本
        """
        if isinstance(system, str):
            return system
        
        if not isinstance(system, list):
            return ""
        
        texts: List[str] = []
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    texts.append(text)
        
        return "\n".join(texts)
    
    def _extract_history_text(self, messages: List[Dict[str, Any]]) -> str:
        """
        提取历史消息的文本内容（不依赖 cache_control）
        
        Args:
            messages: 消息列表
            
        Returns:
            历史消息文本
        """
        texts: List[str] = []
        
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            
            if isinstance(content, str):
                texts.append(f"{role}: {content}")
            elif isinstance(content, list):
                message_parts = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        if block_type == "text":
                            message_parts.append(block.get("text", ""))
                        elif block_type == "tool_use":
                            import json
                            name = block.get("name", "")
                            input_data = block.get("input", {})
                            message_parts.append(f"[tool_use:{name}] {json.dumps(input_data)}")
                        elif block_type == "tool_result":
                            tool_use_id = block.get("tool_use_id", "")
                            result_content = block.get("content", "")
                            if isinstance(result_content, str):
                                message_parts.append(f"[tool_result:{tool_use_id}] {result_content}")
                            else:
                                import json
                                message_parts.append(f"[tool_result:{tool_use_id}] {json.dumps(result_content)}")
                
                if message_parts:
                    texts.append(f"{role}: {' '.join(message_parts)}")
        
        return "\n".join(texts)

