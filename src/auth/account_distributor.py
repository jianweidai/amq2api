# -*- coding: utf-8 -*-

"""
账号分配器 (Account Distributor)

实现基于成功率、冷却时间和负载均衡的账号智能分配算法。
用于在多账号环境中选择最佳账号处理当前请求。
"""

import random
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
from threading import Lock
from dataclasses import dataclass, field

from src.auth.account_manager import (
    list_enabled_accounts, get_account, is_account_in_cooldown
)

logger = logging.getLogger(__name__)


@dataclass
class AccountUsageRecord:
    """账号使用记录"""
    account_id: str
    success_count: int = 0
    fail_count: int = 0
    last_used: float = 0.0  # 时间戳（毫秒）
    recent_usage_count: int = 0  # 短期使用次数


class NoAccountAvailableError(Exception):
    """没有可用账号"""
    pass


class AccountDistributor:
    """
    智能账号分配器
    
    实现：
    1. 成功率评分（权重 40%）：保证可靠性
    2. 冷却时间评分（权重 30%）：最近使用的得低分，实现轮换
    3. 负载均衡评分（权重 30%）：短期内使用次数少的优先
    """
    
    # 单例实例
    _instance: Optional['AccountDistributor'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._lock = Lock()
        
        # 账号使用记录: {account_id: AccountUsageRecord}
        self._usage_records: Dict[str, AccountUsageRecord] = {}
        
        # 最小成功率阈值
        self.min_success_rate = 0.5
        
        # 短期使用计数重置时间（秒）
        self.recent_usage_window = 60
        self._last_reset = time.time()
        
        self._initialized = True
        logger.info("AccountDistributor 初始化完成")
    
    def _reset_recent_usage_if_needed(self):
        """每分钟重置一次短期使用计数"""
        now = time.time()
        if now - self._last_reset > self.recent_usage_window:
            for record in self._usage_records.values():
                record.recent_usage_count = 0
            self._last_reset = now
    
    def _get_or_create_record(self, account_id: str) -> AccountUsageRecord:
        """获取或创建使用记录"""
        if account_id not in self._usage_records:
            self._usage_records[account_id] = AccountUsageRecord(account_id=account_id)
        return self._usage_records[account_id]
    
    def calculate_score(self, account: Dict[str, Any]) -> float:
        """
        计算账号评分 (0-100)
        
        评分基于：
        - 成功率 (权重 40%)：保证可靠性
        - 冷却时间 (权重 30%)：最近使用的得低分，实现轮换
        - 负载均衡 (权重 30%)：短期内使用次数少的优先
        """
        now = time.time() * 1000  # 毫秒
        self._reset_recent_usage_if_needed()
        
        account_id = account.get('id')
        record = self._get_or_create_record(account_id)
        
        # 1. 成功率分 (权重 40%)
        total = record.success_count + record.fail_count
        if total == 0:
            success_rate = 1.0  # 新账号给予高分
        else:
            success_rate = record.success_count / total
        
        # 如果成功率低于阈值，大幅降分
        if success_rate < self.min_success_rate and total > 10:
            base_score = success_rate * 20  # 严重惩罚
        else:
            base_score = success_rate * 40
        
        # 2. 冷却时间分 (权重 30%)：最近使用的得低分，长时间未使用的得高分
        if record.last_used > 0:
            seconds_since_use = (now - record.last_used) / 1000
        else:
            seconds_since_use = 3600  # 从未使用，视为 1 小时前
        
        # 30 秒内使用过的得低分，超过 5 分钟的得满分
        if seconds_since_use < 30:
            cooldown_score = 5  # 刚用过，低分
        elif seconds_since_use < 60:
            cooldown_score = 15
        elif seconds_since_use < 300:
            cooldown_score = 25
        else:
            cooldown_score = 30  # 满分
        
        # 3. 短期负载均衡分 (权重 30%)：最近 1 分钟内使用次数少的优先
        recent_count = record.recent_usage_count
        # 每次使用扣 10 分，最多扣到 0
        balance_score = max(0, 30 - recent_count * 10)
        
        total_score = base_score + cooldown_score + balance_score
        
        # 考虑账号权重（如果有设置）
        account_weight = account.get('weight', 50) / 50.0  # 归一化到 1.0
        total_score *= account_weight
        
        logger.debug(
            f"账号 {account_id[:8]}... 评分: 总分={total_score:.1f} "
            f"(成功率={base_score:.1f}, 冷却={cooldown_score:.1f}, 均衡={balance_score:.1f}, 权重={account_weight:.2f})"
        )
        
        return total_score
    
    def _weighted_random_choice(self, accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        基于评分的加权随机选择
        
        评分高的账号有更高的概率被选中，但不是绝对的。
        这样可以在保证高质量账号优先的同时，实现负载均衡。
        """
        if len(accounts) == 1:
            return accounts[0]
        
        # 计算每个账号的评分
        scores = [(acc, self.calculate_score(acc)) for acc in accounts]
        
        # 确保所有分数为正（加一个小常数避免 0 权重）
        min_score = min(s for _, s in scores)
        if min_score <= 0:
            scores = [(acc, s - min_score + 1) for acc, s in scores]
        
        # 加权随机选择
        total_weight = sum(s for _, s in scores)
        r = random.uniform(0, total_weight)
        
        cumulative = 0
        for account, score in scores:
            cumulative += score
            if r <= cumulative:
                return account
        
        # 兜底返回最后一个
        return scores[-1][0]
    
    def get_best_account(
        self, 
        account_type: str = "amazonq",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取最佳账号
        
        Args:
            account_type: 账号类型 (amazonq, gemini, custom_api)
            model: 模型名称（用于过滤支持该模型的账号）
        
        Returns:
            选中的账号
        
        Raises:
            NoAccountAvailableError: 无可用账号
        """
        with self._lock:
            # 获取所有启用的账号
            all_accounts = list_enabled_accounts(account_type=account_type)
            
            if not all_accounts:
                raise NoAccountAvailableError(f"没有可用的 {account_type} 账号")
            
            # 过滤掉冷却中的账号
            available_accounts = [
                acc for acc in all_accounts
                if not is_account_in_cooldown(acc.get('id'))
            ]
            
            if not available_accounts:
                # 如果所有账号都在冷却中，使用所有账号（等待时间最短的会优先）
                logger.warning(f"所有 {account_type} 账号都在冷却中，使用所有可用账号进行分配")
                available_accounts = all_accounts
            
            # 过滤掉低成功率的账号（给新账号机会）
            good_accounts = []
            for acc in available_accounts:
                record = self._get_or_create_record(acc.get('id'))
                total = record.success_count + record.fail_count
                if total < 10 or (record.success_count / total) >= self.min_success_rate:
                    good_accounts.append(acc)
            
            if not good_accounts:
                # 如果没有好的账号，使用所有可用的
                good_accounts = available_accounts
            
            # 使用加权随机选择
            selected = self._weighted_random_choice(good_accounts)
            
            # 更新使用记录
            record = self._get_or_create_record(selected.get('id'))
            record.last_used = time.time() * 1000
            record.recent_usage_count += 1
            
            logger.info(
                f"Account分配: 从 {len(good_accounts)} 个可用 {account_type} 账号中选择了 "
                f"{selected.get('id')[:8]}... (label: {selected.get('label', 'N/A')})"
            )
            
            return selected
    
    def record_usage(self, account_id: str, success: bool):
        """
        记录账号使用结果
        
        Args:
            account_id: 账号 ID
            success: 是否成功
        """
        with self._lock:
            record = self._get_or_create_record(account_id)
            if success:
                record.success_count += 1
            else:
                record.fail_count += 1
            
            logger.debug(
                f"记录账号 {account_id[:8]}... 使用结果: {'成功' if success else '失败'} "
                f"(成功率: {record.success_count}/{record.success_count + record.fail_count})"
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            self._reset_recent_usage_if_needed()
            
            stats = {
                "total_records": len(self._usage_records),
                "min_success_rate": self.min_success_rate,
                "recent_usage_window": self.recent_usage_window,
                "accounts": {}
            }
            
            for account_id, record in self._usage_records.items():
                total = record.success_count + record.fail_count
                stats["accounts"][account_id[:8]] = {
                    "success_count": record.success_count,
                    "fail_count": record.fail_count,
                    "success_rate": record.success_count / total if total > 0 else 1.0,
                    "recent_usage": record.recent_usage_count
                }
            
            return stats


# 全局分配器实例
_account_distributor: Optional[AccountDistributor] = None


def get_account_distributor() -> AccountDistributor:
    """获取全局 Account Distributor 实例"""
    global _account_distributor
    if _account_distributor is None:
        _account_distributor = AccountDistributor()
    return _account_distributor
