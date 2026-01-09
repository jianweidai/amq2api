"""
测试管理后台安全性
验证会话认证是否正常工作
"""
import pytest
import os
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建测试客户端"""
    # 临时设置环境变量
    os.environ["AMAZONQ_REFRESH_TOKEN"] = "test_token"
    os.environ["AMAZONQ_CLIENT_ID"] = "test_client_id"
    os.environ["AMAZONQ_CLIENT_SECRET"] = "test_client_secret"
    
    # 确保没有 ADMIN_KEY
    if "ADMIN_KEY" in os.environ:
        del os.environ["ADMIN_KEY"]
    
    from src.main import app
    return TestClient(app)


def test_admin_page_without_admin_key_env(client):
    """测试：未登录时，应该拒绝访问管理页面"""
    response = client.get("/admin")
    # 可能返回 401（需要登录）或 403（无管理员账号）
    assert response.status_code in [401, 403]


def test_admin_page_without_header(client):
    """测试：未提供会话令牌时，应该拒绝访问"""
    response = client.get("/admin")
    assert response.status_code in [401, 403]


def test_admin_page_with_wrong_key(client):
    """测试：提供无效的会话令牌时，应该拒绝访问"""
    response = client.get(
        "/admin",
        headers={"X-Session-Token": "invalid_token"}
    )
    assert response.status_code == 401
    assert "会话已过期或无效" in response.json()["detail"]


def test_admin_page_with_correct_key(client):
    """测试：提供有效的会话令牌时，应该允许访问"""
    # 首先创建管理员账号
    from src.auth.admin_manager import create_admin_user, delete_admin_user, get_admin_user
    from src.auth.session_manager import create_session
    
    # 清理可能存在的管理员
    delete_admin_user()
    
    # 创建管理员
    admin = create_admin_user("testadmin", "testpassword123")
    
    # 创建会话
    token = create_session(admin.id, "test-user-agent")
    
    # 使用会话令牌访问
    response = client.get(
        "/admin",
        headers={"X-Session-Token": token, "User-Agent": "test-user-agent"}
    )
    assert response.status_code == 200
    
    # 清理
    delete_admin_user()


def test_accounts_api_without_admin_key_env(client):
    """测试：未登录时，API 应该拒绝访问"""
    response = client.get("/v2/accounts")
    # 可能返回 401（需要登录）或 403（无管理员账号）
    assert response.status_code in [401, 403]


def test_accounts_api_without_header(client):
    """测试：未提供会话令牌时，API 应该拒绝访问"""
    response = client.get("/v2/accounts")
    assert response.status_code in [401, 403]


def test_accounts_api_with_wrong_key(client):
    """测试：提供无效的会话令牌时，API 应该拒绝访问"""
    response = client.get(
        "/v2/accounts",
        headers={"X-Session-Token": "invalid_token"}
    )
    assert response.status_code == 401


def test_accounts_api_with_correct_key(client):
    """测试：提供有效的会话令牌时，API 应该允许访问"""
    from src.auth.admin_manager import create_admin_user, delete_admin_user, get_admin_user
    from src.auth.session_manager import create_session
    
    # 清理可能存在的管理员
    delete_admin_user()
    
    # 创建管理员
    admin = create_admin_user("testadmin", "testpassword123")
    
    # 创建会话
    token = create_session(admin.id, "test-user-agent")
    
    # 使用会话令牌访问
    response = client.get(
        "/v2/accounts",
        headers={"X-Session-Token": token, "User-Agent": "test-user-agent"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    
    # 清理
    delete_admin_user()


def test_create_account_without_key(client):
    """测试：创建账号时未提供会话令牌，应该拒绝"""
    response = client.post(
        "/v2/accounts",
        json={
            "label": "Test Account",
            "clientId": "test_id",
            "clientSecret": "test_secret",
            "type": "amazonq"
        }
    )
    # 可能返回 401（需要登录）或 403（无管理员账号）
    assert response.status_code in [401, 403]


def test_create_account_with_correct_key(client):
    """测试：创建账号时提供有效会话令牌，应该成功"""
    from src.auth.admin_manager import create_admin_user, delete_admin_user, get_admin_user
    from src.auth.session_manager import create_session
    from src.auth.account_manager import delete_account
    
    # 清理可能存在的管理员
    delete_admin_user()
    
    # 创建管理员
    admin = create_admin_user("testadmin", "testpassword123")
    
    # 创建会话
    token = create_session(admin.id, "test-user-agent")
    
    # 使用会话令牌创建账号
    response = client.post(
        "/v2/accounts",
        json={
            "label": "Test Account",
            "clientId": "test_id",
            "clientSecret": "test_secret",
            "refreshToken": "test_refresh",
            "type": "amazonq"
        },
        headers={"X-Session-Token": token, "User-Agent": "test-user-agent"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Test Account"
    assert data["clientId"] == "test_id"
    
    # 清理创建的测试账号
    if "id" in data:
        delete_account(data["id"])
    
    # 清理管理员
    delete_admin_user()


def test_url_parameter_not_supported(client):
    """测试：URL 参数不支持认证"""
    response = client.get("/admin?key=some_key")
    # 应该返回 401 或 403，因为没有在 Header 中提供会话令牌
    assert response.status_code in [401, 403]


def test_all_admin_endpoints_require_key(client):
    """测试：所有管理端点都需要会话令牌"""
    from src.auth.admin_manager import create_admin_user, delete_admin_user, get_admin_user
    from src.auth.session_manager import create_session
    
    # 清理可能存在的管理员
    delete_admin_user()
    
    # 创建管理员
    admin = create_admin_user("testadmin", "testpassword123")
    
    # 创建会话
    token = create_session(admin.id, "test-user-agent")
    
    endpoints = [
        ("GET", "/v2/accounts"),
        ("POST", "/v2/accounts/refresh-all"),
    ]
    
    for method, endpoint in endpoints:
        # 不提供会话令牌
        if method == "GET":
            response = client.get(endpoint)
        else:
            response = client.post(endpoint)
        
        assert response.status_code in [401, 403], f"{method} {endpoint} 应该返回 401 或 403"
        
        # 提供正确会话令牌
        headers = {"X-Session-Token": token, "User-Agent": "test-user-agent"}
        if method == "GET":
            response = client.get(endpoint, headers=headers)
        else:
            response = client.post(endpoint, headers=headers)
        
        # 应该不是 401 或 403（可能是 200 或其他错误）
        assert response.status_code not in [401, 403], f"{method} {endpoint} 不应该返回 401 或 403"
    
    # 清理
    delete_admin_user()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
