"""
认证模块
包含 Amazon Q 认证、账号管理和 Token 调度
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
]
