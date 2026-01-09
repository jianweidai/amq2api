"""
Rate Limiter for Admin Login

负责登录请求的速率限制和账号锁定功能。
使用内存存储登录尝试记录。

Requirements:
- 3.4: 速率限制 - 每个 IP 每分钟最多 5 次登录尝试
- 3.5: 账号锁定 - 连续 5 次失败后锁定 15 分钟
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from threading import Lock

# 配置常量
RATE_LIMIT_WINDOW_SECONDS = 60  # 速率限制窗口：60秒
RATE_LIMIT_MAX_ATTEMPTS = 5     # 窗口内最大尝试次数
LOCKOUT_THRESHOLD = 5           # 连续失败次数阈值
LOCKOUT_DURATION_SECONDS = 900  # 锁定时长：15分钟 (900秒)

# 内存存储
_login_attempts: Dict[str, List[datetime]] = {}  # IP -> 登录尝试时间列表
_failed_attempts: Dict[str, int] = {}            # IP -> 连续失败次数
_account_lockouts: Dict[str, datetime] = {}      # IP -> 锁定解除时间

# 线程安全锁
_lock = Lock()


def check_rate_limit(ip_address: str) -> Tuple[bool, Optional[str]]:
    """
    检查是否超过速率限制
    
    Args:
        ip_address: 客户端 IP 地址
        
    Returns:
        Tuple[bool, Optional[str]]: (是否允许, 错误消息)
        - (True, None): 允许请求
        - (False, error_message): 拒绝请求，附带错误消息
    """
    with _lock:
        now = datetime.now()
        
        # 清理过期的尝试记录
        _cleanup_old_attempts(ip_address, now)
        
        # 获取当前窗口内的尝试次数
        attempts = _login_attempts.get(ip_address, [])
        window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
        recent_attempts = [t for t in attempts if t > window_start]
        
        if len(recent_attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
            return (False, "请求过于频繁，请稍后重试")
        
        return (True, None)


def record_login_attempt(ip_address: str, success: bool) -> None:
    """
    记录登录尝试
    
    Args:
        ip_address: 客户端 IP 地址
        success: 登录是否成功
    """
    with _lock:
        now = datetime.now()
        
        # 记录尝试时间（用于速率限制）
        if ip_address not in _login_attempts:
            _login_attempts[ip_address] = []
        _login_attempts[ip_address].append(now)
        
        # 更新连续失败计数
        if success:
            # 登录成功，清除失败计数和锁定状态
            _failed_attempts.pop(ip_address, None)
            _account_lockouts.pop(ip_address, None)
        else:
            # 登录失败，增加失败计数
            _failed_attempts[ip_address] = _failed_attempts.get(ip_address, 0) + 1
            
            # 检查是否需要锁定
            if _failed_attempts[ip_address] >= LOCKOUT_THRESHOLD:
                lockout_until = now + timedelta(seconds=LOCKOUT_DURATION_SECONDS)
                _account_lockouts[ip_address] = lockout_until


def is_account_locked(ip_address: str = None) -> Tuple[bool, Optional[int]]:
    """
    检查账号是否被锁定
    
    Args:
        ip_address: 客户端 IP 地址（可选，如果不提供则检查全局锁定状态）
        
    Returns:
        Tuple[bool, Optional[int]]: (是否锁定, 剩余秒数)
        - (True, remaining_seconds): 账号被锁定
        - (False, None): 账号未锁定
    """
    with _lock:
        now = datetime.now()
        
        if ip_address is None:
            # 检查是否有任何锁定（用于全局状态检查）
            for ip, lockout_until in list(_account_lockouts.items()):
                if lockout_until > now:
                    remaining = int((lockout_until - now).total_seconds())
                    return (True, remaining)
            return (False, None)
        
        # 检查特定 IP 的锁定状态
        lockout_until = _account_lockouts.get(ip_address)
        if lockout_until is None:
            return (False, None)
        
        if lockout_until > now:
            remaining = int((lockout_until - now).total_seconds())
            return (True, remaining)
        
        # 锁定已过期，清除锁定状态
        _account_lockouts.pop(ip_address, None)
        _failed_attempts.pop(ip_address, None)
        return (False, None)


def clear_login_attempts(ip_address: str = None) -> None:
    """
    清除登录尝试记录（用于测试）
    
    Args:
        ip_address: 客户端 IP 地址（可选，如果不提供则清除所有记录）
    """
    with _lock:
        if ip_address is None:
            _login_attempts.clear()
            _failed_attempts.clear()
            _account_lockouts.clear()
        else:
            _login_attempts.pop(ip_address, None)
            _failed_attempts.pop(ip_address, None)
            _account_lockouts.pop(ip_address, None)


def get_failed_attempts_count(ip_address: str) -> int:
    """
    获取连续失败次数（用于测试和调试）
    
    Args:
        ip_address: 客户端 IP 地址
        
    Returns:
        int: 连续失败次数
    """
    with _lock:
        return _failed_attempts.get(ip_address, 0)


def _cleanup_old_attempts(ip_address: str, now: datetime) -> None:
    """
    清理过期的尝试记录（内部函数，需要在锁内调用）
    
    Args:
        ip_address: 客户端 IP 地址
        now: 当前时间
    """
    if ip_address in _login_attempts:
        window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
        _login_attempts[ip_address] = [
            t for t in _login_attempts[ip_address] if t > window_start
        ]
        # 如果列表为空，删除键
        if not _login_attempts[ip_address]:
            del _login_attempts[ip_address]
