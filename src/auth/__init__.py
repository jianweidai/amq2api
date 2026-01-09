"""
认证模块
包含 Amazon Q 认证、账号管理、Token 调度和登录速率限制
"""

from src.auth.auth import (
    get_auth_headers_with_retry,
    get_auth_headers_for_account,
    refresh_account_token,
    refresh_legacy_token,
    NoAccountAvailableError,
    TokenRefreshError,
)

from src.auth.account_manager import (
    list_enabled_accounts,
    list_all_accounts,
    get_account,
    create_account,
    update_account,
    delete_account,
    get_random_account,
    get_random_channel_by_model,
    set_account_cooldown,
)

from src.auth.token_scheduler import scheduled_token_refresh

from src.auth.rate_limiter import (
    check_rate_limit as check_login_rate_limit,
    record_login_attempt,
    is_account_locked,
    clear_login_attempts,
    get_failed_attempts_count,
)

__all__ = [
    # auth
    "get_auth_headers_with_retry",
    "get_auth_headers_for_account",
    "refresh_account_token",
    "refresh_legacy_token",
    "NoAccountAvailableError",
    "TokenRefreshError",
    # account_manager
    "list_enabled_accounts",
    "list_all_accounts",
    "get_account",
    "create_account",
    "update_account",
    "delete_account",
    "get_random_account",
    "get_random_channel_by_model",
    "set_account_cooldown",
    # token_scheduler
    "scheduled_token_refresh",
    # rate_limiter (for admin login)
    "check_login_rate_limit",
    "record_login_attempt",
    "is_account_locked",
    "clear_login_attempts",
    "get_failed_attempts_count",
]
