"""
账号池管理器

管理多个 Amazon Q 账号,提供负载均衡、故障转移和熔断功能
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from account_config import AccountConfig, LoadBalanceStrategy
from load_balancer import LoadBalancer
from exceptions import (
    NoAvailableAccountError,
    AccountNotFoundError,
    CircuitBreakerOpenError,
    TokenRefreshError,
)

logger = logging.getLogger(__name__)


class AccountPool:
    """账号池管理器"""

    def __init__(
        self,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN,
        circuit_breaker_enabled: bool = True,
        circuit_breaker_error_threshold: int = 5,
        circuit_breaker_recovery_timeout: int = 300,
    ):
        """
        初始化账号池

        Args:
            strategy: 负载均衡策略
            circuit_breaker_enabled: 是否启用熔断器
            circuit_breaker_error_threshold: 熔断器错误阈值
            circuit_breaker_recovery_timeout: 熔断器恢复时间(秒)
        """
        self.accounts: Dict[str, AccountConfig] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
        self.load_balancer = LoadBalancer(strategy)

        # 熔断器配置
        self.circuit_breaker_enabled = circuit_breaker_enabled
        self.circuit_breaker_error_threshold = circuit_breaker_error_threshold
        self.circuit_breaker_recovery_timeout = circuit_breaker_recovery_timeout

        logger.info(
            f"AccountPool initialized with strategy={strategy.value}, "
            f"circuit_breaker_enabled={circuit_breaker_enabled}"
        )

    def add_account(self, account: AccountConfig):
        """
        添加账号到池

        Args:
            account: 账号配置对象
        """
        self.accounts[account.id] = account
        self.locks[account.id] = asyncio.Lock()
        logger.info(
            f"Added account '{account.id}' to pool "
            f"(enabled={account.enabled}, weight={account.weight})"
        )

    def remove_account(self, account_id: str):
        """
        从池中移除账号

        Args:
            account_id: 账号 ID

        Raises:
            AccountNotFoundError: 账号不存在时抛出
        """
        if account_id not in self.accounts:
            raise AccountNotFoundError(account_id)

        del self.accounts[account_id]
        del self.locks[account_id]
        logger.info(f"Removed account '{account_id}' from pool")

    def get_account(self, account_id: str) -> AccountConfig:
        """
        获取指定账号

        Args:
            account_id: 账号 ID

        Returns:
            AccountConfig: 账号配置对象

        Raises:
            AccountNotFoundError: 账号不存在时抛出
        """
        if account_id not in self.accounts:
            raise AccountNotFoundError(account_id)
        return self.accounts[account_id]

    async def select_account(self) -> AccountConfig:
        """
        根据负载均衡策略选择账号

        Returns:
            AccountConfig: 选中的账号

        Raises:
            NoAvailableAccountError: 无可用账号时抛出
        """
        accounts = list(self.accounts.values())
        if not accounts:
            raise NoAvailableAccountError("No accounts configured")

        account = self.load_balancer.select_account(accounts)
        logger.debug(f"Selected account '{account.id}' using strategy {self.load_balancer.strategy.value}")
        return account

    async def mark_success(self, account_id: str):
        """
        标记账号请求成功

        Args:
            account_id: 账号 ID
        """
        if account_id in self.accounts:
            account = self.accounts[account_id]
            account.mark_success()
            logger.debug(f"Account '{account_id}' marked as success (success={account.success_count})")

    async def mark_error(self, account_id: str, error: Optional[Exception] = None):
        """
        标记账号请求错误,并检查是否需要熔断

        Args:
            account_id: 账号 ID
            error: 错误对象(可选)
        """
        if account_id not in self.accounts:
            return

        account = self.accounts[account_id]
        account.mark_error()

        logger.warning(
            f"Account '{account_id}' marked as error "
            f"(error_count={account.error_count}, error={error})"
        )

        # 检查熔断条件
        if self.circuit_breaker_enabled:
            if account.error_count >= self.circuit_breaker_error_threshold:
                await self._open_circuit_breaker(account_id)

    async def _open_circuit_breaker(self, account_id: str):
        """
        打开熔断器

        Args:
            account_id: 账号 ID
        """
        if account_id not in self.accounts:
            return

        account = self.accounts[account_id]
        account.circuit_breaker_open = True
        account.circuit_breaker_open_until = datetime.now() + timedelta(
            seconds=self.circuit_breaker_recovery_timeout
        )

        logger.error(
            f"Circuit breaker opened for account '{account_id}' "
            f"(error_count={account.error_count}, "
            f"recovery_at={account.circuit_breaker_open_until.isoformat()})"
        )

    async def reset_circuit_breaker(self, account_id: str):
        """
        重置熔断器

        Args:
            account_id: 账号 ID

        Raises:
            AccountNotFoundError: 账号不存在时抛出
        """
        if account_id not in self.accounts:
            raise AccountNotFoundError(account_id)

        account = self.accounts[account_id]
        account.circuit_breaker_open = False
        account.circuit_breaker_open_until = None
        account.error_count = 0

        logger.info(f"Circuit breaker reset for account '{account_id}'")

    async def enable_account(self, account_id: str):
        """
        启用账号

        Args:
            account_id: 账号 ID

        Raises:
            AccountNotFoundError: 账号不存在时抛出
        """
        if account_id not in self.accounts:
            raise AccountNotFoundError(account_id)

        self.accounts[account_id].enabled = True
        logger.info(f"Account '{account_id}' enabled")

    async def disable_account(self, account_id: str):
        """
        禁用账号

        Args:
            account_id: 账号 ID

        Raises:
            AccountNotFoundError: 账号不存在时抛出
        """
        if account_id not in self.accounts:
            raise AccountNotFoundError(account_id)

        self.accounts[account_id].enabled = False
        logger.info(f"Account '{account_id}' disabled")

    def get_account_lock(self, account_id: str) -> asyncio.Lock:
        """
        获取账号的锁(用于 Token 刷新等操作)

        Args:
            account_id: 账号 ID

        Returns:
            asyncio.Lock: 账号锁

        Raises:
            AccountNotFoundError: 账号不存在时抛出
        """
        if account_id not in self.locks:
            raise AccountNotFoundError(account_id)
        return self.locks[account_id]

    def get_all_accounts(self) -> List[AccountConfig]:
        """
        获取所有账号

        Returns:
            List[AccountConfig]: 账号列表
        """
        return list(self.accounts.values())

    def get_available_accounts(self) -> List[AccountConfig]:
        """
        获取所有可用账号

        Returns:
            List[AccountConfig]: 可用账号列表
        """
        return [acc for acc in self.accounts.values() if acc.is_available()]

    def get_stats(self) -> dict:
        """
        获取账号池统计信息

        Returns:
            dict: 统计信息字典
        """
        total_accounts = len(self.accounts)
        available_accounts = len(self.get_available_accounts())
        total_requests = sum(acc.request_count for acc in self.accounts.values())
        total_errors = sum(acc.error_count for acc in self.accounts.values())
        total_successes = sum(acc.success_count for acc in self.accounts.values())

        return {
            "total_accounts": total_accounts,
            "available_accounts": available_accounts,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "total_successes": total_successes,
            "strategy": self.load_balancer.strategy.value,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "accounts": [acc.to_dict() for acc in self.accounts.values()],
        }
