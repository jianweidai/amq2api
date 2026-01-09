"""
Session Manager 模块测试
验证会话管理功能的正确性
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.auth.session_manager import (
    Session,
    create_session,
    validate_session,
    invalidate_session,
    cleanup_expired_sessions,
    delete_all_sessions,
    get_session,
    get_active_session_count,
    invalidate_all_sessions,
    SESSION_TOKEN_BYTES,
)
from src.auth.admin_manager import (
    create_admin_user,
    delete_admin_user,
)


@pytest.fixture(autouse=True)
def cleanup():
    """每个测试前后清理数据"""
    delete_all_sessions()
    delete_admin_user()
    yield
    delete_all_sessions()
    delete_admin_user()


@pytest.fixture
def admin_user():
    """创建测试用管理员账号"""
    return create_admin_user("testadmin", "testpassword123")


class TestSessionCreation:
    """会话创建测试"""
    
    def test_create_session_returns_token(self, admin_user):
        """测试创建会话返回令牌"""
        token = create_session(admin_user.id, "Mozilla/5.0 Test")
        assert token is not None
        assert isinstance(token, str)
    
    def test_create_session_token_length(self, admin_user):
        """测试会话令牌长度（64 字符 = 256 bits）"""
        token = create_session(admin_user.id, "Mozilla/5.0 Test")
        # 32 bytes * 2 (hex encoding) = 64 characters
        assert len(token) == SESSION_TOKEN_BYTES * 2
    
    def test_create_session_stores_in_database(self, admin_user):
        """测试会话存储到数据库"""
        token = create_session(admin_user.id, "Mozilla/5.0 Test")
        session = get_session(token)
        
        assert session is not None
        assert session.token == token
        assert session.admin_id == admin_user.id
        assert session.user_agent == "Mozilla/5.0 Test"
    
    def test_create_multiple_sessions(self, admin_user):
        """测试创建多个会话"""
        token1 = create_session(admin_user.id, "UA1")
        token2 = create_session(admin_user.id, "UA2")
        
        assert token1 != token2
        assert get_session(token1) is not None
        assert get_session(token2) is not None


class TestSessionValidation:
    """会话验证测试"""
    
    def test_validate_valid_session(self, admin_user):
        """测试验证有效会话"""
        token = create_session(admin_user.id, "Mozilla/5.0 Test")
        session = validate_session(token, "Mozilla/5.0 Test")
        
        assert session is not None
        assert session.admin_id == admin_user.id
    
    def test_validate_invalid_token(self, admin_user):
        """测试验证无效令牌"""
        session = validate_session("invalid_token_12345", "Mozilla/5.0 Test")
        assert session is None
    
    def test_validate_wrong_user_agent(self, admin_user):
        """测试 User-Agent 不匹配时验证失败"""
        token = create_session(admin_user.id, "Mozilla/5.0 Test")
        session = validate_session(token, "Different User Agent")
        
        assert session is None
    
    def test_validate_empty_user_agent_stored(self, admin_user):
        """测试存储空 User-Agent 时允许任何 UA"""
        token = create_session(admin_user.id, "")
        session = validate_session(token, "Any User Agent")
        
        # 空 user_agent 存储时，验证应该通过
        assert session is not None


class TestSessionInvalidation:
    """会话失效测试"""
    
    def test_invalidate_existing_session(self, admin_user):
        """测试使现有会话失效"""
        token = create_session(admin_user.id, "Mozilla/5.0 Test")
        
        result = invalidate_session(token)
        assert result is True
        
        # 验证会话已删除
        session = get_session(token)
        assert session is None
    
    def test_invalidate_nonexistent_session(self):
        """测试使不存在的会话失效"""
        result = invalidate_session("nonexistent_token")
        assert result is False
    
    def test_invalidate_all_sessions_for_admin(self, admin_user):
        """测试使管理员的所有会话失效"""
        token1 = create_session(admin_user.id, "UA1")
        token2 = create_session(admin_user.id, "UA2")
        token3 = create_session(admin_user.id, "UA3")
        
        deleted = invalidate_all_sessions(admin_user.id)
        assert deleted == 3
        
        # 验证所有会话已删除
        assert get_session(token1) is None
        assert get_session(token2) is None
        assert get_session(token3) is None


class TestSessionCleanup:
    """会话清理测试"""
    
    def test_cleanup_expired_sessions(self, admin_user):
        """测试清理过期会话"""
        # 创建一个会话
        token = create_session(admin_user.id, "Mozilla/5.0 Test")
        
        # 手动将会话设置为过期（通过直接修改数据库）
        from src.auth.account_manager import _sqlite_conn, USE_MYSQL
        from src.auth.session_manager import ADMIN_SESSIONS_TABLE
        
        past_time = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        if not USE_MYSQL:
            with _sqlite_conn() as conn:
                conn.execute(
                    f"UPDATE {ADMIN_SESSIONS_TABLE} SET expires_at=? WHERE token=?",
                    (past_time, token)
                )
                conn.commit()
        
        # 清理过期会话
        deleted = cleanup_expired_sessions()
        
        if not USE_MYSQL:
            assert deleted >= 1
            assert get_session(token) is None


class TestActiveSessionCount:
    """活跃会话计数测试"""
    
    def test_get_active_session_count(self, admin_user):
        """测试获取活跃会话数量"""
        # 初始应该是 0
        count = get_active_session_count(admin_user.id)
        assert count == 0
        
        # 创建会话后应该是 1
        create_session(admin_user.id, "UA1")
        count = get_active_session_count(admin_user.id)
        assert count == 1
        
        # 再创建一个应该是 2
        create_session(admin_user.id, "UA2")
        count = get_active_session_count(admin_user.id)
        assert count == 2


class TestSessionDataClass:
    """Session 数据类测试"""
    
    def test_session_dataclass_fields(self):
        """测试 Session 数据类字段"""
        session = Session(
            token="test_token",
            admin_id="test_admin_id",
            user_agent="Mozilla/5.0",
            created_at="2024-01-01T00:00:00Z",
            expires_at="2024-01-02T00:00:00Z",
            last_activity="2024-01-01T12:00:00Z"
        )
        
        assert session.token == "test_token"
        assert session.admin_id == "test_admin_id"
        assert session.user_agent == "Mozilla/5.0"
        assert session.created_at == "2024-01-01T00:00:00Z"
        assert session.expires_at == "2024-01-02T00:00:00Z"
        assert session.last_activity == "2024-01-01T12:00:00Z"
