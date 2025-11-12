"""
自定义异常类

定义多账号管理中使用的专用异常
"""


class MultiAccountException(Exception):
    """多账号相关异常的基类"""
    pass


class NoAvailableAccountError(MultiAccountException):
    """无可用账号异常"""
    def __init__(self, message: str = "No available accounts"):
        self.message = message
        super().__init__(self.message)


class AccountDisabledError(MultiAccountException):
    """账号已禁用异常"""
    def __init__(self, account_id: str, message: str = None):
        self.account_id = account_id
        self.message = message or f"Account '{account_id}' is disabled"
        super().__init__(self.message)


class TokenRefreshError(MultiAccountException):
    """Token 刷新失败异常"""
    def __init__(self, account_id: str, reason: str = None):
        self.account_id = account_id
        self.reason = reason
        self.message = f"Failed to refresh token for account '{account_id}'"
        if reason:
            self.message += f": {reason}"
        super().__init__(self.message)


class CircuitBreakerOpenError(MultiAccountException):
    """熔断器打开异常"""
    def __init__(self, account_id: str, open_until: str = None):
        self.account_id = account_id
        self.open_until = open_until
        self.message = f"Circuit breaker open for account '{account_id}'"
        if open_until:
            self.message += f" until {open_until}"
        super().__init__(self.message)


class AccountNotFoundError(MultiAccountException):
    """账号未找到异常"""
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.message = f"Account '{account_id}' not found"
        super().__init__(self.message)


class InvalidAccountConfigError(MultiAccountException):
    """无效的账号配置异常"""
    def __init__(self, message: str):
        self.message = f"Invalid account configuration: {message}"
        super().__init__(self.message)
