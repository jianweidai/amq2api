"""
Admin Manager 模块测试
验证管理员账号的创建、验证和管理功能
"""
import pytest
from src.auth.admin_manager import (
    ensure_admin_table,
    admin_exists,
    get_admin_user,
    get_admin_user_by_username,
    create_admin_user,
    verify_admin_password,
    delete_admin_user,
    AdminUser,
    BCRYPT_COST_FACTOR,
)


@pytest.fixture(autouse=True)
def cleanup_admin():
    """每个测试前后清理管理员账号"""
    delete_admin_user()
    yield
    delete_admin_user()


class TestAdminManagerBasic:
    """Admin Manager 基础功能测试"""

    def test_bcrypt_cost_factor_at_least_12(self):
        """验证 bcrypt 成本因子至少为 12"""
        assert BCRYPT_COST_FACTOR >= 12

    def test_ensure_admin_table(self):
        """验证表初始化不会报错"""
        ensure_admin_table()

    def test_admin_exists_returns_false_when_no_admin(self):
        """验证没有管理员时 admin_exists 返回 False"""
        assert admin_exists() is False

    def test_get_admin_user_returns_none_when_no_admin(self):
        """验证没有管理员时 get_admin_user 返回 None"""
        assert get_admin_user() is None

    def test_create_admin_user_success(self):
        """验证创建管理员账号成功"""
        admin = create_admin_user("testadmin", "testpassword123")
        
        assert admin is not None
        assert isinstance(admin, AdminUser)
        assert admin.username == "testadmin"
        assert admin.password_hash.startswith("$2")  # bcrypt format
        assert admin.id is not None
        assert admin.created_at is not None
        assert admin.updated_at is not None

    def test_create_admin_user_bcrypt_cost_factor(self):
        """验证密码哈希使用正确的 bcrypt 成本因子"""
        admin = create_admin_user("testadmin", "testpassword123")
        
        # bcrypt hash format: $2b$12$...
        parts = admin.password_hash.split("$")
        cost = int(parts[2])
        assert cost >= 12, f"Cost factor should be >= 12, got {cost}"

    def test_admin_exists_returns_true_after_creation(self):
        """验证创建管理员后 admin_exists 返回 True"""
        create_admin_user("testadmin", "testpassword123")
        assert admin_exists() is True

    def test_get_admin_user_returns_admin_after_creation(self):
        """验证创建管理员后 get_admin_user 返回管理员"""
        create_admin_user("testadmin", "testpassword123")
        
        admin = get_admin_user()
        assert admin is not None
        assert admin.username == "testadmin"

    def test_get_admin_user_by_username(self):
        """验证根据用户名获取管理员"""
        create_admin_user("testadmin", "testpassword123")
        
        admin = get_admin_user_by_username("testadmin")
        assert admin is not None
        assert admin.username == "testadmin"
        
        # 不存在的用户名
        assert get_admin_user_by_username("nonexistent") is None


class TestAdminPasswordVerification:
    """密码验证测试"""

    def test_verify_correct_password(self):
        """验证正确密码返回 True"""
        create_admin_user("testadmin", "testpassword123")
        assert verify_admin_password("testadmin", "testpassword123") is True

    def test_verify_wrong_password(self):
        """验证错误密码返回 False"""
        create_admin_user("testadmin", "testpassword123")
        assert verify_admin_password("testadmin", "wrongpassword") is False

    def test_verify_wrong_username(self):
        """验证错误用户名返回 False"""
        create_admin_user("testadmin", "testpassword123")
        assert verify_admin_password("wronguser", "testpassword123") is False

    def test_verify_nonexistent_user(self):
        """验证不存在的用户返回 False"""
        assert verify_admin_password("nonexistent", "anypassword") is False


class TestAdminAccountConstraints:
    """管理员账号约束测试"""

    def test_only_one_admin_allowed(self):
        """验证系统只允许一个管理员账号"""
        create_admin_user("firstadmin", "password123")
        
        with pytest.raises(ValueError, match="管理员账号已存在"):
            create_admin_user("secondadmin", "password456")

    def test_username_length_validation_too_short(self):
        """验证用户名长度验证 - 太短"""
        with pytest.raises(ValueError, match="用户名必须为 3-50 个字符"):
            create_admin_user("ab", "password123")

    def test_username_length_validation_too_long(self):
        """验证用户名长度验证 - 太长"""
        with pytest.raises(ValueError, match="用户名必须为 3-50 个字符"):
            create_admin_user("a" * 51, "password123")

    def test_password_length_validation(self):
        """验证密码长度验证"""
        with pytest.raises(ValueError, match="密码必须至少 8 个字符"):
            create_admin_user("testadmin", "short")

    def test_empty_username_rejected(self):
        """验证空用户名被拒绝"""
        with pytest.raises(ValueError):
            create_admin_user("", "password123")

    def test_empty_password_rejected(self):
        """验证空密码被拒绝"""
        with pytest.raises(ValueError):
            create_admin_user("testadmin", "")


class TestAdminDeletion:
    """管理员删除测试"""

    def test_delete_admin_user(self):
        """验证删除管理员账号"""
        create_admin_user("testadmin", "testpassword123")
        assert admin_exists() is True
        
        result = delete_admin_user()
        assert result is True
        assert admin_exists() is False

    def test_delete_nonexistent_admin(self):
        """验证删除不存在的管理员返回 False"""
        result = delete_admin_user()
        assert result is False
