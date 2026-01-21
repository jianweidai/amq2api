"""
测试账号统计功能
验证账号调用次数和 token 用量统计
"""
import pytest
from datetime import datetime, timezone, timedelta
from src.auth.account_manager import (
    create_account,
    delete_account,
    record_api_call,
    get_account_call_stats,
    _ensure_db
)
from src.processing.usage_tracker import record_usage, get_usage_summary


@pytest.fixture
def test_account():
    """创建测试账号"""
    _ensure_db()
    account = create_account(
        label="测试账号",
        client_id="test_client_id",
        client_secret="test_client_secret",
        refresh_token="test_refresh_token",
        enabled=True,
        account_type="amazonq"
    )
    yield account
    # 清理
    delete_account(account['id'])


def test_record_api_call(test_account):
    """测试记录 API 调用"""
    account_id = test_account['id']
    
    # 记录几次调用
    for i in range(5):
        record_api_call(account_id, model="claude-sonnet-4")
    
    # 获取统计
    stats = get_account_call_stats(account_id)
    
    assert stats['account_id'] == account_id
    assert stats['calls_last_hour'] == 5
    assert stats['calls_last_day'] == 5
    assert stats['total_calls'] == 5


def test_record_token_usage(test_account):
    """测试记录 token 使用量"""
    account_id = test_account['id']
    
    # 记录几次 token 使用
    record_usage(
        model="claude-sonnet-4",
        input_tokens=100,
        output_tokens=50,
        account_id=account_id,
        channel="amazonq"
    )
    
    record_usage(
        model="claude-sonnet-4",
        input_tokens=200,
        output_tokens=100,
        account_id=account_id,
        channel="amazonq"
    )
    
    # 获取今日统计
    day_usage = get_usage_summary(period="day", account_id=account_id)
    
    assert day_usage['request_count'] == 2
    assert day_usage['input_tokens'] == 300
    assert day_usage['output_tokens'] == 150
    assert day_usage['total_tokens'] == 450


def test_token_usage_with_cache(test_account):
    """测试带缓存的 token 使用量记录"""
    account_id = test_account['id']
    
    # 记录带缓存的 token 使用
    record_usage(
        model="claude-sonnet-4",
        input_tokens=100,
        output_tokens=50,
        account_id=account_id,
        channel="amazonq",
        cache_creation_input_tokens=50,
        cache_read_input_tokens=30
    )
    
    # 获取统计
    day_usage = get_usage_summary(period="day", account_id=account_id)
    
    assert day_usage['cache_creation_input_tokens'] == 50
    assert day_usage['cache_read_input_tokens'] == 30


def test_multiple_accounts_stats():
    """测试多账号统计隔离"""
    _ensure_db()
    
    # 创建两个测试账号
    account1 = create_account(
        label="账号1",
        client_id="client1",
        client_secret="secret1",
        refresh_token="token1",
        enabled=True
    )
    
    account2 = create_account(
        label="账号2",
        client_id="client2",
        client_secret="secret2",
        refresh_token="token2",
        enabled=True
    )
    
    try:
        # 为账号1记录调用
        for i in range(3):
            record_api_call(account1['id'], model="claude-sonnet-4")
        
        record_usage(
            model="claude-sonnet-4",
            input_tokens=100,
            output_tokens=50,
            account_id=account1['id']
        )
        
        # 为账号2记录调用
        for i in range(5):
            record_api_call(account2['id'], model="claude-sonnet-4")
        
        record_usage(
            model="claude-sonnet-4",
            input_tokens=200,
            output_tokens=100,
            account_id=account2['id']
        )
        
        # 验证统计隔离
        stats1 = get_account_call_stats(account1['id'])
        stats2 = get_account_call_stats(account2['id'])
        
        assert stats1['total_calls'] == 3
        assert stats2['total_calls'] == 5
        
        usage1 = get_usage_summary(period="day", account_id=account1['id'])
        usage2 = get_usage_summary(period="day", account_id=account2['id'])
        
        assert usage1['total_tokens'] == 150
        assert usage2['total_tokens'] == 300
        
    finally:
        # 清理
        delete_account(account1['id'])
        delete_account(account2['id'])


def test_period_filtering(test_account):
    """测试不同时间周期的统计"""
    account_id = test_account['id']
    
    # 记录一些使用
    for i in range(3):
        record_usage(
            model="claude-sonnet-4",
            input_tokens=100,
            output_tokens=50,
            account_id=account_id
        )
    
    # 测试不同周期
    hour_usage = get_usage_summary(period="hour", account_id=account_id)
    day_usage = get_usage_summary(period="day", account_id=account_id)
    month_usage = get_usage_summary(period="month", account_id=account_id)
    
    # 所有周期应该都能看到这些记录（因为刚记录的）
    assert hour_usage['request_count'] == 3
    assert day_usage['request_count'] == 3
    assert month_usage['request_count'] == 3
    
    assert hour_usage['total_tokens'] == 450
    assert day_usage['total_tokens'] == 450
    assert month_usage['total_tokens'] == 450


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
