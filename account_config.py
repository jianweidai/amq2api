"""
账号配置数据结构

定义单个 Amazon Q 账号的配置信息和运行时状态
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class LoadBalanceStrategy(str, Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"  # 简单轮询
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"  # 加权轮询
    LEAST_USED = "least_used"  # 最少使用
    RANDOM = "random"  # 随机选择


@dataclass
class AccountConfig:
    """
    单个 Amazon Q 账号配置

    包含账号凭证、运行时状态和统计信息
    """
    # 账号标识
    id: str

    # 认证凭证
    refresh_token: str
    client_id: str
    client_secret: str
    profile_arn: Optional[str] = None

    # 运行时 Token 状态
    access_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None

    # 负载均衡配置
    weight: int = 10  # 权重,默认 10
    enabled: bool = True  # 是否启用

    # 统计信息
    request_count: int = 0  # 总请求数
    error_count: int = 0  # 错误计数
    success_count: int = 0  # 成功计数
    last_used_at: Optional[datetime] = None  # 最后使用时间
    last_error_at: Optional[datetime] = None  # 最后错误时间
    last_success_at: Optional[datetime] = None  # 最后成功时间

    # 熔断状态
    circuit_breaker_open: bool = False  # 熔断器是否打开
    circuit_breaker_open_until: Optional[datetime] = None  # 熔断器打开至

    def is_available(self) -> bool:
        """
        判断账号是否可用

        Returns:
            bool: 账号可用返回 True,否则返回 False
        """
        if not self.enabled:
            return False

        # 检查熔断状态
        if self.circuit_breaker_open:
            if self.circuit_breaker_open_until:
                # 如果到达恢复时间,自动关闭熔断器
                if datetime.now() >= self.circuit_breaker_open_until:
                    self.circuit_breaker_open = False
                    self.circuit_breaker_open_until = None
                    self.error_count = 0  # 重置错误计数
                    return True
                return False
            return False

        return True

    def mark_success(self):
        """标记请求成功"""
        self.success_count += 1
        self.last_success_at = datetime.now()
        self.last_used_at = datetime.now()
        # 成功后可以减少错误计数(逐渐恢复)
        if self.error_count > 0:
            self.error_count = max(0, self.error_count - 1)

    def mark_error(self):
        """标记请求错误"""
        self.error_count += 1
        self.last_error_at = datetime.now()
        self.last_used_at = datetime.now()

    def to_dict(self) -> dict:
        """
        转换为字典格式

        Returns:
            dict: 账号信息字典(不包含敏感信息)
        """
        return {
            "id": self.id,
            "enabled": self.enabled,
            "weight": self.weight,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "success_count": self.success_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "circuit_breaker_open": self.circuit_breaker_open,
            "is_available": self.is_available(),
        }
