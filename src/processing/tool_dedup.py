"""
工具调用去重模块
检测并标记重复的工具调用，帮助 AI 避免无意义的重复操作
"""
import hashlib
import time
import json
import os
import logging
from typing import Dict, Optional, Any, Tuple
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    input_hash: str
    input_preview: str  # 输入预览（前100字符）
    result_preview: str  # 结果预览（前200字符）
    call_count: int = 1
    first_call_time: float = field(default_factory=time.time)
    last_call_time: float = field(default_factory=time.time)
    session_keys: set = field(default_factory=set)


class ToolDedupManager:
    """工具调用去重管理器"""
    
    # 单例实例
    _instance: Optional['ToolDedupManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 工具调用缓存: {cache_key: ToolCallRecord}
        self._cache: OrderedDict[str, ToolCallRecord] = OrderedDict()
        
        # 最大缓存条目数
        self.max_entries = 500
        
        # 缓存过期时间（秒）- 5 分钟
        self.ttl = 300
        
        # 重复调用阈值 - 超过此次数才警告
        self.warn_threshold = 2
        
        # 短时间重复检测窗口（秒）
        self.short_window = 60
        
        self._initialized = True
        logger.info("ToolDedupManager 初始化完成")
    
    def is_enabled(self) -> bool:
        """检查是否启用工具去重"""
        value = os.environ.get("ENABLE_TOOL_DEDUP", "true").lower()
        return value not in ("false", "0", "no", "off")
    
    def _compute_cache_key(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        计算缓存 key
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
        
        Returns:
            缓存 key (MD5 哈希)
        """
        # 对输入参数排序后序列化
        sorted_input = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
        key_content = f"{tool_name}:{sorted_input}"
        return hashlib.md5(key_content.encode()).hexdigest()
    
    def _get_input_preview(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """获取输入预览"""
        if tool_name == "Bash":
            return tool_input.get("command", "")[:100]
        elif tool_name == "Read":
            return tool_input.get("file_path", "")[:100]
        else:
            return json.dumps(tool_input, ensure_ascii=False)[:100]
    
    def _cleanup_expired(self):
        """清理过期的缓存条目"""
        now = time.time()
        expired_keys = [
            key for key, record in self._cache.items()
            if now - record.last_call_time > self.ttl
        ]
        for key in expired_keys:
            del self._cache[key]
        
        # 如果仍然超过最大条目数，删除最旧的
        while len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
    
    def record_tool_call(
        self, 
        tool_name: str, 
        tool_input: Dict[str, Any],
        session_key: Optional[str] = None
    ) -> Tuple[str, int, bool]:
        """
        记录工具调用
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            session_key: 会话标识
        
        Returns:
            Tuple[cache_key, call_count, is_duplicate_in_short_window]
        """
        if not self.is_enabled():
            return "", 0, False
        
        self._cleanup_expired()
        
        cache_key = self._compute_cache_key(tool_name, tool_input)
        now = time.time()
        
        if cache_key in self._cache:
            record = self._cache[cache_key]
            record.call_count += 1
            
            # 检查是否在短时间窗口内重复
            is_short_window_dup = (now - record.last_call_time) < self.short_window
            
            record.last_call_time = now
            if session_key:
                record.session_keys.add(session_key)
            
            # 移动到末尾（LRU）
            self._cache.move_to_end(cache_key)
            
            logger.info(
                f"[TOOL_DEDUP] 检测到重复调用: {tool_name} "
                f"(count={record.call_count}, short_window={is_short_window_dup}, "
                f"input={record.input_preview[:50]}...)"
            )
            
            return cache_key, record.call_count, is_short_window_dup
        else:
            # 新的调用 - 先检查是否需要淘汰旧条目
            while len(self._cache) >= self.max_entries:
                self._cache.popitem(last=False)
            
            record = ToolCallRecord(
                tool_name=tool_name,
                input_hash=cache_key,
                input_preview=self._get_input_preview(tool_name, tool_input),
                result_preview="",  # 稍后更新
                session_keys={session_key} if session_key else set()
            )
            self._cache[cache_key] = record
            
            return cache_key, 1, False
    
    def update_result(self, cache_key: str, result: str):
        """更新工具调用结果"""
        if cache_key in self._cache:
            self._cache[cache_key].result_preview = result[:200]
    
    def get_dedup_warning(
        self, 
        tool_name: str, 
        tool_input: Dict[str, Any],
        call_count: int,
        is_short_window_dup: bool
    ) -> Optional[str]:
        """
        获取去重警告信息
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            call_count: 调用次数
            is_short_window_dup: 是否在短时间窗口内重复
        
        Returns:
            警告信息，如果不需要警告则返回 None
        """
        if not self.is_enabled():
            return None
        
        # 只有超过阈值且在短时间窗口内才警告
        if call_count <= self.warn_threshold or not is_short_window_dup:
            return None
        
        input_preview = self._get_input_preview(tool_name, tool_input)
        
        warning = (
            f"\n\n[⚠️ DUPLICATE TOOL CALL DETECTED]\n"
            f"This exact {tool_name} call has been executed {call_count} times recently.\n"
            f"Input: {input_preview[:80]}{'...' if len(input_preview) > 80 else ''}\n"
            f"The result is identical to previous calls.\n"
            f"IMPORTANT: Please use the information you already have and move forward. "
            f"Do NOT call this tool again with the same parameters.\n"
            f"[END DUPLICATE WARNING]"
        )
        
        return warning
    
    def check_and_warn(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_key: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """
        检查工具调用并返回警告（如果需要）
        
        这是一个便捷方法，组合了 record_tool_call 和 get_dedup_warning
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            session_key: 会话标识
        
        Returns:
            Tuple[cache_key, warning_message]
        """
        cache_key, call_count, is_short_dup = self.record_tool_call(
            tool_name, tool_input, session_key
        )
        
        warning = self.get_dedup_warning(
            tool_name, tool_input, call_count, is_short_dup
        )
        
        return cache_key, warning
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        self._cleanup_expired()
        
        total_calls = sum(r.call_count for r in self._cache.values())
        duplicate_calls = sum(
            r.call_count - 1 for r in self._cache.values() if r.call_count > 1
        )
        
        # 按工具名称统计
        by_tool: Dict[str, int] = {}
        for record in self._cache.values():
            by_tool[record.tool_name] = by_tool.get(record.tool_name, 0) + record.call_count
        
        return {
            "enabled": self.is_enabled(),
            "cache_entries": len(self._cache),
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl,
            "total_calls_tracked": total_calls,
            "duplicate_calls": duplicate_calls,
            "by_tool": by_tool
        }


# 全局实例
_dedup_manager: Optional[ToolDedupManager] = None


def get_dedup_manager() -> ToolDedupManager:
    """获取去重管理器单例"""
    global _dedup_manager
    if _dedup_manager is None:
        _dedup_manager = ToolDedupManager()
    return _dedup_manager
