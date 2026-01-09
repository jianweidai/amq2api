"""
测试限流和统计功能
"""
import pytest
from src.auth.account_manager import (
    record_api_call,
    check_rate_limit,
    get_account_call_stats,
    update_account_rate_limit,
    create_account,
    delete_account
)
import time


def test_record_and_check_rate_limit():
    """测试记录调用和检查限流"""
    # 创建测试账号
    account = create_account(
        label="Test Rate Limit Account",
        client_id="test_client_id",
        client_secret="test_client_secret",
        refresh_token="test_refresh_token",
        account_type="amazonq",
        weight=50
    )
    account_id = account['id']
    
    try:
        # 设置限流为 5 次/小时
        update_account_rate_limit(account_id, 5)
        
        # 记录 3 次调用
        for i in range(3):
            record_api_call(account_id, "claude-sonnet-4.5")
        
        # 应该还没有达到限流
        assert check_rate_limit(account_id) == True
        
        # 获取统计信息
        stats = get_account_call_stats(account_id)
        assert stats['calls_last_hour'] == 3
        assert stats['rate_limit_per_hour'] == 5
        assert stats['remaining_quota'] == 2
        
        # 再记录 3 次调用（总共 6 次）
        for i in range(3):
            record_api_call(account_id, "claude-sonnet-4.5")
        
        # 应该已经达到限流
        assert check_rate_limit(account_id) == False
        
        # 获取统计信息
        stats = get_account_call_stats(account_id)
        assert stats['calls_last_hour'] == 6
        assert stats['remaining_quota'] == 0
        
    finally:
        # 清理测试账号
        delete_account(account_id)


def test_account_call_stats():
    """测试账号调用统计"""
    # 创建测试账号
    account = create_account(
        label="Test Stats Account",
        client_id="test_client_id",
        client_secret="test_client_secret",
        refresh_token="test_refresh_token",
        account_type="gemini",
        weight=70
    )
    account_id = account['id']
    
    try:
        # 记录一些调用
        for i in range(5):
            record_api_call(account_id, "gemini-2.5-flash")
        
        # 获取统计信息
        stats = get_account_call_stats(account_id)
        
        assert stats['account_id'] == account_id
        assert stats['calls_last_hour'] == 5
        assert stats['calls_last_day'] == 5
        assert stats['total_calls'] == 5
        assert stats['rate_limit_per_hour'] == 20  # 默认值
        assert stats['remaining_quota'] == 15
        
    finally:
        # 清理测试账号
        delete_account(account_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
