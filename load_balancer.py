"""
负载均衡器

实现多种负载均衡策略用于账号选择
"""

import random
from typing import List, Optional
from account_config import AccountConfig, LoadBalanceStrategy
from exceptions import NoAvailableAccountError


class LoadBalancer:
    """负载均衡器"""

    def __init__(self, strategy: LoadBalanceStrategy = LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN):
        """
        初始化负载均衡器

        Args:
            strategy: 负载均衡策略
        """
        self.strategy = strategy
        self.current_index = 0  # 用于轮询

    def select_account(self, accounts: List[AccountConfig]) -> AccountConfig:
        """
        根据策略选择账号

        Args:
            accounts: 可用账号列表

        Returns:
            AccountConfig: 选中的账号

        Raises:
            NoAvailableAccountError: 无可用账号时抛出
        """
        # 过滤出可用账号
        available_accounts = [acc for acc in accounts if acc.is_available()]

        if not available_accounts:
            raise NoAvailableAccountError("All accounts are unavailable")

        # 根据策略选择
        if self.strategy == LoadBalanceStrategy.ROUND_ROBIN:
            return self._select_round_robin(available_accounts)
        elif self.strategy == LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN:
            return self._select_weighted_round_robin(available_accounts)
        elif self.strategy == LoadBalanceStrategy.LEAST_USED:
            return self._select_least_used(available_accounts)
        elif self.strategy == LoadBalanceStrategy.RANDOM:
            return self._select_random(available_accounts)
        else:
            # 默认使用加权轮询
            return self._select_weighted_round_robin(available_accounts)

    def _select_round_robin(self, accounts: List[AccountConfig]) -> AccountConfig:
        """
        简单轮询选择

        Args:
            accounts: 可用账号列表

        Returns:
            AccountConfig: 选中的账号
        """
        account = accounts[self.current_index % len(accounts)]
        self.current_index += 1
        return account

    def _select_weighted_round_robin(self, accounts: List[AccountConfig]) -> AccountConfig:
        """
        加权轮询选择

        根据账号权重(weight)进行随机选择,权重越高被选中概率越大

        Args:
            accounts: 可用账号列表

        Returns:
            AccountConfig: 选中的账号
        """
        # 提取权重
        weights = [acc.weight for acc in accounts]
        total_weight = sum(weights)

        if total_weight == 0:
            # 所有权重都是 0,使用简单轮询
            return self._select_round_robin(accounts)

        # 使用 random.choices 进行加权随机选择
        selected = random.choices(accounts, weights=weights, k=1)[0]
        return selected

    def _select_least_used(self, accounts: List[AccountConfig]) -> AccountConfig:
        """
        选择使用最少的账号

        基于 request_count 选择请求数最少的账号

        Args:
            accounts: 可用账号列表

        Returns:
            AccountConfig: 选中的账号
        """
        return min(accounts, key=lambda acc: acc.request_count)

    def _select_random(self, accounts: List[AccountConfig]) -> AccountConfig:
        """
        随机选择账号

        Args:
            accounts: 可用账号列表

        Returns:
            AccountConfig: 选中的账号
        """
        return random.choice(accounts)

    def set_strategy(self, strategy: LoadBalanceStrategy):
        """
        设置负载均衡策略

        Args:
            strategy: 新的负载均衡策略
        """
        self.strategy = strategy
