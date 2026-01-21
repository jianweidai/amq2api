"""
测试账号统计 API 端点
验证 /v2/accounts/{account_id}/stats 接口返回正确的数据
"""
import pytest
import os
from fastapi.testclient import TestClient
from src.main import app
from src.auth.account_manager import (
    create_account,
    delete_account,
    record_api_call,
    _ensure_db
)
from src.processing.usage_tracker import record_usage


@pytest.fixture
def client():
    """创建测试客户端（禁用认证）"""
    # 临时清除 API_KEY 环境变量以禁用认证
    original_api_key = os.environ.get('API_KEY')
    if 'API_KEY' in os.environ:
        del os.environ['API_KEY']
    
    client = TestClient(app)
    
    yield client
    
    # 恢复原始环境变量
    if original_api_key:
        os.environ['API_KEY'] = original_api_key


@pytest.fixture
def admin_client():
    """创建带管理员认证的测试客户端"""
    from src.auth.admin_manager import create_admin_user, admin_exists
    from src.auth.session_manager import create_session
    
    # 如果管理员不存在，创建一个
    if not admin_exists():
        create_admin_user("test_admin", "test_password_123")
    
    # 创建会话（使用固定的 user-agent）
    user_agent = "test-client"
    session_token = create_session("test_admin", user_agent)
    
    client = TestClient(app)
    # 设置请求头，包括 User-Agent
    client.headers.update({
        "X-Session-Token": session_token,
        "User-Agent": user_agent
    })
    
    return client


@pytest.fixture
def test_account():
    """创建测试账号"""
    _ensure_db()
    account = create_account(
        label="API测试账号",
        client_id="test_client_id",
        client_secret="test_client_secret",
        refresh_token="test_refresh_token",
        enabled=True,
        account_type="amazonq"
    )
    
    # 记录一些调用和 token 使用
    for i in range(3):
        record_api_call(account['id'], model="claude-sonnet-4")
    
    record_usage(
        model="claude-sonnet-4",
        input_tokens=100,
        output_tokens=50,
        account_id=account['id'],
        channel="amazonq"
    )
    
    record_usage(
        model="claude-sonnet-4",
        input_tokens=200,
        output_tokens=100,
        account_id=account['id'],
        channel="amazonq",
        cache_creation_input_tokens=50,
        cache_read_input_tokens=30
    )
    
    yield account
    # 清理
    delete_account(account['id'])


def test_get_account_stats_api(admin_client, test_account):
    """测试获取账号统计 API"""
    account_id = test_account['id']
    
    # 调用 API
    response = admin_client.get(f"/v2/accounts/{account_id}/stats")
    
    # 验证响应
    assert response.status_code == 200
    
    data = response.json()
    
    # 验证基本统计字段
    assert 'account_id' in data
    assert data['account_id'] == account_id
    assert 'calls_last_hour' in data
    assert 'calls_last_day' in data
    assert 'total_calls' in data
    
    # 验证调用次数
    assert data['total_calls'] == 3
    
    # 验证 token 使用量字段
    assert 'token_usage' in data
    assert 'today' in data['token_usage']
    assert 'this_month' in data['token_usage']
    
    # 验证今日 token 使用量
    today = data['token_usage']['today']
    assert today['request_count'] == 2
    assert today['input_tokens'] == 300
    assert today['output_tokens'] == 150
    assert today['total_tokens'] == 450
    assert today['cache_creation_input_tokens'] == 50
    assert today['cache_read_input_tokens'] == 30
    assert 'total_cost' in today
    assert 'currency' in today
    assert today['currency'] == 'USD'
    
    # 验证本月 token 使用量（应该和今日相同，因为刚创建）
    this_month = data['token_usage']['this_month']
    assert this_month['request_count'] == 2
    assert this_month['total_tokens'] == 450
    assert 'total_cost' in this_month
    assert 'currency' in this_month


def test_get_account_stats_not_found(admin_client):
    """测试获取不存在账号的统计"""
    response = admin_client.get("/v2/accounts/nonexistent-id/stats")
    assert response.status_code == 404


def test_stats_response_structure(admin_client, test_account):
    """测试统计响应的完整结构"""
    account_id = test_account['id']
    response = admin_client.get(f"/v2/accounts/{account_id}/stats")
    
    assert response.status_code == 200
    data = response.json()
    
    # 验证所有必需字段
    required_fields = [
        'account_id',
        'calls_last_hour',
        'calls_last_day',
        'total_calls',
        'rate_limit_per_hour',
        'remaining_quota',
        'cooldown_remaining_seconds',
        'is_in_cooldown',
        'token_usage'
    ]
    
    for field in required_fields:
        assert field in data, f"缺少字段: {field}"
    
    # 验证 token_usage 结构
    token_usage = data['token_usage']
    for period in ['today', 'this_month']:
        assert period in token_usage
        period_data = token_usage[period]
        
        required_token_fields = [
            'request_count',
            'input_tokens',
            'output_tokens',
            'total_tokens',
            'cache_creation_input_tokens',
            'cache_read_input_tokens',
            'total_cost',
            'currency'
        ]
        
        for field in required_token_fields:
            assert field in period_data, f"缺少 token 字段: {period}.{field}"
            if field == 'currency':
                assert isinstance(period_data[field], str), f"字段类型错误: {period}.{field}"
            else:
                assert isinstance(period_data[field], (int, float)), f"字段类型错误: {period}.{field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
