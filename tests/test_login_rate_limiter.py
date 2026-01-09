"""
测试管理员登录速率限制模块
"""
import pytest
from src.auth.rate_limiter import (
    check_rate_limit,
    record_login_attempt,
    is_account_locked,
    clear_login_attempts,
    get_failed_attempts_count,
    RATE_LIMIT_MAX_ATTEMPTS,
    LOCKOUT_THRESHOLD,
)


@pytest.fixture(autouse=True)
def cleanup():
    """每个测试前后清理状态"""
    clear_login_attempts()
    yield
    clear_login_attempts()


class TestCheckRateLimit:
    """测试速率限制检查"""
    
    def test_initial_state_allows_request(self):
        """初始状态应该允许请求"""
        allowed, msg = check_rate_limit("192.168.1.100")
        assert allowed is True
        assert msg is None
    
    def test_allows_requests_under_limit(self):
        """未达到限制时应该允许请求"""
        test_ip = "192.168.1.101"
        for i in range(RATE_LIMIT_MAX_ATTEMPTS - 1):
            record_login_attempt(test_ip, success=False)
        
        allowed, msg = check_rate_limit(test_ip)
        assert allowed is True
        assert msg is None
    
    def test_blocks_requests_at_limit(self):
        """达到限制时应该阻止请求"""
        test_ip = "192.168.1.102"
        for i in range(RATE_LIMIT_MAX_ATTEMPTS):
            record_login_attempt(test_ip, success=False)
        
        allowed, msg = check_rate_limit(test_ip)
        assert allowed is False
        assert msg is not None
        assert "请求过于频繁" in msg


class TestRecordLoginAttempt:
    """测试登录尝试记录"""
    
    def test_successful_login_clears_failed_count(self):
        """成功登录应该清除失败计数"""
        test_ip = "192.168.1.103"
        for i in range(3):
            record_login_attempt(test_ip, success=False)
        
        assert get_failed_attempts_count(test_ip) == 3
        
        record_login_attempt(test_ip, success=True)
        assert get_failed_attempts_count(test_ip) == 0
    
    def test_failed_login_increments_count(self):
        """失败登录应该增加失败计数"""
        test_ip = "192.168.1.104"
        
        record_login_attempt(test_ip, success=False)
        assert get_failed_attempts_count(test_ip) == 1
        
        record_login_attempt(test_ip, success=False)
        assert get_failed_attempts_count(test_ip) == 2


class TestAccountLockout:
    """测试账号锁定"""
    
    def test_not_locked_initially(self):
        """初始状态不应该锁定"""
        locked, remaining = is_account_locked("192.168.1.105")
        assert locked is False
        assert remaining is None
    
    def test_locks_after_threshold_failures(self):
        """达到阈值后应该锁定"""
        test_ip = "192.168.1.106"
        for i in range(LOCKOUT_THRESHOLD):
            record_login_attempt(test_ip, success=False)
        
        locked, remaining = is_account_locked(test_ip)
        assert locked is True
        assert remaining is not None
        assert remaining > 0
    
    def test_successful_login_clears_lockout(self):
        """成功登录应该清除锁定状态"""
        test_ip = "192.168.1.107"
        for i in range(LOCKOUT_THRESHOLD):
            record_login_attempt(test_ip, success=False)
        
        locked, _ = is_account_locked(test_ip)
        assert locked is True
        
        # 模拟成功登录（实际场景中锁定期间不会成功，这里测试清除逻辑）
        record_login_attempt(test_ip, success=True)
        
        locked, remaining = is_account_locked(test_ip)
        assert locked is False
        assert remaining is None


class TestClearLoginAttempts:
    """测试清除登录尝试"""
    
    def test_clear_specific_ip(self):
        """清除特定 IP 的记录"""
        ip1 = "192.168.1.108"
        ip2 = "192.168.1.109"
        
        record_login_attempt(ip1, success=False)
        record_login_attempt(ip2, success=False)
        
        clear_login_attempts(ip1)
        
        assert get_failed_attempts_count(ip1) == 0
        assert get_failed_attempts_count(ip2) == 1
    
    def test_clear_all(self):
        """清除所有记录"""
        ip1 = "192.168.1.110"
        ip2 = "192.168.1.111"
        
        record_login_attempt(ip1, success=False)
        record_login_attempt(ip2, success=False)
        
        clear_login_attempts()
        
        assert get_failed_attempts_count(ip1) == 0
        assert get_failed_attempts_count(ip2) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
