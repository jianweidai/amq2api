"""
会话绑定模块
将同一会话的请求绑定到同一个账号和 conversationId，避免工具重复调用问题

修复并发问题：使用锁机制确保同一会话的绑定操作是原子的
"""
import hashlib
import time
import uuid
import os
import logging
import threading
from typing import Dict, Optional, Tuple, Any
from collections import OrderedDict

logger = logging.getLogger(__name__)

# 会话绑定缓存：{session_key: (account_id, conversation_id, timestamp, account_type)}
# 使用 OrderedDict 实现 LRU 缓存
_session_bindings: OrderedDict[str, Tuple[str, str, float, str]] = OrderedDict()

# 锁：确保并发访问时的线程安全
_bindings_lock = threading.RLock()

# 每个 session_key 的独立锁，用于确保"检查-绑定"操作的原子性
_session_locks: Dict[str, threading.RLock] = {}
_session_locks_lock = threading.Lock()  # 保护 _session_locks 字典的锁

# 最大缓存条目数
MAX_BINDINGS = 1000

# 绑定过期时间（秒）- 30 分钟
BINDING_TTL = 1800

# 是否启用会话绑定（可通过环境变量 ENABLE_SESSION_BINDING 控制）
# 默认启用，设置为 "false" 或 "0" 禁用
def is_session_binding_enabled() -> bool:
    """检查是否启用会话绑定"""
    value = os.environ.get("ENABLE_SESSION_BINDING", "true").lower()
    return value not in ("false", "0", "no", "off")


def _get_session_lock(session_key: str) -> threading.RLock:
    """
    获取指定 session_key 的锁
    
    这确保同一 session 的并发请求会串行执行绑定检查
    """
    with _session_locks_lock:
        if session_key not in _session_locks:
            _session_locks[session_key] = threading.RLock()
            # 定期清理过期的锁（简单策略：锁数量超过阈值时清理）
            if len(_session_locks) > MAX_BINDINGS * 2:
                _cleanup_session_locks()
        return _session_locks[session_key]


def _cleanup_session_locks():
    """清理不再使用的 session 锁"""
    # 只保留当前绑定中存在的 session 的锁
    with _bindings_lock:
        active_sessions = set(_session_bindings.keys())
    
    keys_to_remove = [k for k in _session_locks.keys() if k not in active_sessions]
    for key in keys_to_remove:
        del _session_locks[key]
    
    if keys_to_remove:
        logger.debug(f"清理了 {len(keys_to_remove)} 个不再使用的 session 锁")


def _extract_system_text(system: Any) -> str:
    """
    从 system prompt 中提取纯文本内容
    
    Args:
        system: system prompt（字符串或数组格式）
    
    Returns:
        提取的文本内容
    """
    if isinstance(system, str):
        return system
    
    if isinstance(system, list):
        system_texts = []
        for item in system:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    system_texts.append(item.get("text", ""))
                elif "text" in item:
                    system_texts.append(item.get("text", ""))
            elif isinstance(item, str):
                system_texts.append(item)
        return "\n".join(system_texts)
    
    return ""


def _compute_session_key(request_data: Dict[str, Any]) -> str:
    """
    计算会话标识 key
    
    基于 system prompt 的核心部分生成稳定的会话标识。
    
    设计原则：
    1. 只使用 system prompt 的前 200 字符（核心身份标识）
    2. 不使用消息内容（并发请求的消息可能不同）
    3. 不使用模型名称（同一会话可能有不同模型的并发请求）
    
    这样可以确保同一 IDE 会话的所有请求（主请求、token 计数、预加载、工具调用等）
    都能绑定到同一个账号。
    
    Args:
        request_data: Claude API 请求数据
    
    Returns:
        会话标识 key（MD5 哈希）
    """
    # 只使用 system prompt 的前 200 字符作为会话标识
    # 这是最稳定的部分，包含 AI 的身份定义（如 "You are Kiro..."）
    system = _extract_system_text(request_data.get("system", ""))
    
    if system:
        # 只取前 200 字符，这通常包含核心身份信息
        key_content = f"system:{system[:200]}"
    else:
        # 如果没有 system prompt，使用第一条消息的前 100 字符
        messages = request_data.get("messages", [])
        if messages:
            first_msg = messages[0]
            content = first_msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        text_parts.append(item)
                content = "\n".join(text_parts)
            key_content = f"first_msg:{content[:100]}"
        else:
            # 兜底：使用空字符串
            key_content = "empty"
    
    return hashlib.md5(key_content.encode()).hexdigest()


def get_bound_account(request_data: Dict[str, Any], account_type: str = "amazonq") -> Optional[str]:
    """
    获取会话绑定的账号 ID
    
    Args:
        request_data: Claude API 请求数据
        account_type: 账号类型
    
    Returns:
        绑定的账号 ID，如果没有绑定或已过期则返回 None
    """
    # 如果禁用会话绑定，直接返回 None
    if not is_session_binding_enabled():
        return None
    
    session_key = _compute_session_key(request_data)
    
    with _bindings_lock:
        if session_key in _session_bindings:
            account_id, conversation_id, timestamp, bound_type = _session_bindings[session_key]
            
            # 检查是否过期
            if time.time() - timestamp > BINDING_TTL:
                del _session_bindings[session_key]
                logger.debug(f"会话绑定已过期: {session_key[:16]}...")
                return None
            
            # 检查账号类型是否匹配
            if bound_type != account_type:
                logger.debug(f"会话绑定类型不匹配: {bound_type} != {account_type}")
                return None
            
            # 移动到末尾（LRU）
            _session_bindings.move_to_end(session_key)
            
            logger.info(f"命中会话绑定: session={session_key[:16]}... -> account={account_id[:8]}..., conv={conversation_id[:8]}...")
            return account_id
    
    return None


def get_bound_conversation_id(request_data: Dict[str, Any], account_type: str = "amazonq") -> Optional[str]:
    """
    获取会话绑定的 conversationId
    
    Args:
        request_data: Claude API 请求数据
        account_type: 账号类型
    
    Returns:
        绑定的 conversationId，如果没有绑定或已过期则返回 None
    """
    # 如果禁用会话绑定，直接返回 None
    if not is_session_binding_enabled():
        return None
    
    session_key = _compute_session_key(request_data)
    
    with _bindings_lock:
        if session_key in _session_bindings:
            account_id, conversation_id, timestamp, bound_type = _session_bindings[session_key]
            
            # 检查是否过期
            if time.time() - timestamp > BINDING_TTL:
                return None
            
            # 检查账号类型是否匹配
            if bound_type != account_type:
                return None
            
            return conversation_id
    
    return None


def get_or_create_binding(
    request_data: Dict[str, Any],
    account_id: str,
    account_type: str = "amazonq",
    conversation_id: Optional[str] = None
) -> Tuple[str, str, bool]:
    """
    原子性地获取或创建会话绑定（解决并发问题的核心方法）
    
    这是一个原子操作：
    1. 如果已存在有效绑定，返回已有绑定
    2. 如果不存在，创建新绑定
    
    这确保了同一 session 的并发请求只会创建一个绑定，后续请求复用该绑定。
    
    Args:
        request_data: Claude API 请求数据
        account_id: 账号 ID（仅在需要创建新绑定时使用）
        account_type: 账号类型
        conversation_id: 对话 ID（如果为 None，则自动生成）
    
    Returns:
        Tuple[account_id, conversation_id, is_new_binding]
        - account_id: 绑定的账号 ID
        - conversation_id: 绑定的对话 ID
        - is_new_binding: 是否是新创建的绑定
    """
    if not is_session_binding_enabled():
        # 禁用时，直接返回传入的账号
        conv_id = conversation_id or str(uuid.uuid4())
        return account_id, conv_id, True
    
    session_key = _compute_session_key(request_data)
    
    # 获取该 session 的锁，确保并发请求串行执行
    session_lock = _get_session_lock(session_key)
    
    with session_lock:
        with _bindings_lock:
            # 再次检查是否已存在绑定（双重检查锁定模式）
            if session_key in _session_bindings:
                existing_account_id, existing_conv_id, timestamp, bound_type = _session_bindings[session_key]
                
                # 检查是否有效
                if time.time() - timestamp <= BINDING_TTL and bound_type == account_type:
                    # 更新时间戳（续期）
                    _session_bindings[session_key] = (existing_account_id, existing_conv_id, time.time(), bound_type)
                    _session_bindings.move_to_end(session_key)
                    
                    logger.info(f"并发请求复用会话绑定: session={session_key[:16]}... -> account={existing_account_id[:8]}..., conv={existing_conv_id[:8]}...")
                    return existing_account_id, existing_conv_id, False
                else:
                    # 已过期或类型不匹配，删除旧绑定
                    del _session_bindings[session_key]
            
            # 清理过期条目
            _cleanup_expired_bindings_internal()
            
            # 如果缓存已满，删除最旧的条目
            while len(_session_bindings) >= MAX_BINDINGS:
                _session_bindings.popitem(last=False)
            
            # 生成或使用提供的 conversationId
            if conversation_id is None:
                conversation_id = str(uuid.uuid4())
            
            # 创建新绑定
            _session_bindings[session_key] = (account_id, conversation_id, time.time(), account_type)
            
            logger.info(f"创建会话绑定: session={session_key[:16]}... -> account={account_id[:8]}..., conv={conversation_id[:8]}... (type={account_type})")
            return account_id, conversation_id, True


def bind_session_to_account(
    request_data: Dict[str, Any], 
    account_id: str, 
    account_type: str = "amazonq",
    conversation_id: Optional[str] = None
) -> Tuple[str, str]:
    """
    将会话绑定到账号和 conversationId
    
    注意：推荐使用 get_or_create_binding() 来处理并发情况。
    此方法保留用于向后兼容。
    
    Args:
        request_data: Claude API 请求数据
        account_id: 账号 ID
        account_type: 账号类型
        conversation_id: 对话 ID（如果为 None，则自动生成）
    
    Returns:
        Tuple[str, str]: (会话 key, conversationId)
    """
    session_key = _compute_session_key(request_data)
    
    with _bindings_lock:
        # 清理过期条目
        _cleanup_expired_bindings_internal()
        
        # 如果缓存已满，删除最旧的条目
        while len(_session_bindings) >= MAX_BINDINGS:
            _session_bindings.popitem(last=False)
        
        # 生成或使用提供的 conversationId
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
        
        # 添加新绑定
        _session_bindings[session_key] = (account_id, conversation_id, time.time(), account_type)
    
    logger.info(f"创建会话绑定: session={session_key[:16]}... -> account={account_id[:8]}..., conv={conversation_id[:8]}... (type={account_type})")
    return session_key, conversation_id


def unbind_session(request_data: Dict[str, Any]) -> bool:
    """
    解除会话绑定（当账号不可用时调用）
    
    Args:
        request_data: Claude API 请求数据
    
    Returns:
        是否成功解除绑定
    """
    session_key = _compute_session_key(request_data)
    
    with _bindings_lock:
        if session_key in _session_bindings:
            del _session_bindings[session_key]
            logger.info(f"解除会话绑定: session={session_key[:16]}...")
            return True
    
    return False


def _cleanup_expired_bindings_internal() -> int:
    """
    清理过期的绑定（内部使用，不加锁）
    
    Returns:
        清理的条目数
    """
    now = time.time()
    expired_keys = [
        key for key, (_, _, timestamp, _) in _session_bindings.items()
        if now - timestamp > BINDING_TTL
    ]
    
    for key in expired_keys:
        del _session_bindings[key]
    
    if expired_keys:
        logger.debug(f"清理了 {len(expired_keys)} 个过期的会话绑定")
    
    return len(expired_keys)


def _cleanup_expired_bindings() -> int:
    """
    清理过期的绑定（外部使用，加锁）
    
    Returns:
        清理的条目数
    """
    with _bindings_lock:
        return _cleanup_expired_bindings_internal()


def get_binding_stats() -> Dict[str, Any]:
    """
    获取绑定统计信息
    
    Returns:
        统计信息字典
    """
    with _bindings_lock:
        _cleanup_expired_bindings_internal()
        
        return {
            "total_bindings": len(_session_bindings),
            "max_bindings": MAX_BINDINGS,
            "ttl_seconds": BINDING_TTL,
            "session_locks_count": len(_session_locks)
        }
