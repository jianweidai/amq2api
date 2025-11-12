"""
认证模块
负责 Token 刷新和管理,支持多账号
"""
import httpx
import logging
from typing import Dict
from datetime import datetime, timedelta
from account_config import AccountConfig
from config import save_account_token, read_global_config
from exceptions import TokenRefreshError

logger = logging.getLogger(__name__)


async def refresh_token(account: AccountConfig) -> bool:
    """
    刷新指定账号的 access_token

    Args:
        account: 账号配置对象

    Returns:
        bool: 刷新成功返回 True,失败返回 False

    Raises:
        TokenRefreshError: 刷新失败时抛出异常
    """
    try:
        logger.info(f"Refreshing access_token for account '{account.id}'")

        # 获取全局配置(token_endpoint)
        config = await read_global_config()

        # 构建并发送请求
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            payload = {
                "grantType": "refresh_token",
                "refreshToken": account.refresh_token,
                "clientId": account.client_id,
                "clientSecret": account.client_secret
            }

            # 构建 AWS SDK 风格的请求头
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "aws-sdk-rust/1.3.9 os/macos lang/rust/1.87.0",
                "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/ssooidc/1.88.0 os/macos lang/rust/1.87.0 m/E app/AmazonQ-For-CLI",
                "Amz-Sdk-Request": "attempt=1; max=3",
                "Amz-Sdk-Invocation-Id": "362523fb-ad17-428a-b3be-5a812faf0448",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br"
            }

            response = await http_client.post(
                config.token_endpoint,
                json=payload,
                headers=headers
            )

            # 检查 HTTP 错误
            response.raise_for_status()

            # 解析响应并更新账号配置
            response_data = response.json()

            # 提取 token 信息(使用驼峰命名)
            new_access_token = response_data.get("accessToken")
            new_refresh_token = response_data.get("refreshToken")
            expires_in = response_data.get("expiresIn")

            if not new_access_token:
                raise TokenRefreshError(account.id, "Response missing accessToken")

            # 更新账号对象
            account.access_token = new_access_token
            if new_refresh_token:
                account.refresh_token = new_refresh_token
            expires_in_seconds = int(expires_in) if expires_in else 3600  # 默认 1 小时
            account.token_expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)

            # 保存到缓存
            await save_account_token(
                account.id,
                account.access_token,
                account.refresh_token,
                account.token_expires_at
            )

            logger.info(
                f"Token refreshed successfully for account '{account.id}', "
                f"expires at {account.token_expires_at.isoformat()}"
            )
            return True

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
        logger.error(f"Token refresh failed for account '{account.id}' - {error_msg}")
        raise TokenRefreshError(account.id, error_msg) from e
    except httpx.RequestError as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"Token refresh failed for account '{account.id}' - {error_msg}")
        raise TokenRefreshError(account.id, error_msg) from e
    except Exception as e:
        error_msg = f"Unknown error: {str(e)}"
        logger.error(f"Token refresh failed for account '{account.id}' - {error_msg}")
        raise TokenRefreshError(account.id, error_msg) from e


def is_token_expired(account: AccountConfig) -> bool:
    """
    检查账号的 access_token 是否过期

    Args:
        account: 账号配置对象

    Returns:
        bool: 过期或不存在返回 True,否则返回 False
    """
    if not account.access_token or not account.token_expires_at:
        return True
    # 提前 5 分钟刷新
    return datetime.now() >= (account.token_expires_at - timedelta(minutes=5))


async def ensure_valid_token(account: AccountConfig) -> str:
    """
    确保指定账号有有效的 access_token
    如果 token 过期或不存在,则自动刷新

    Args:
        account: 账号配置对象

    Returns:
        str: 有效的 access_token

    Raises:
        TokenRefreshError: 无法获取有效 token 时抛出异常
    """
    # 检查 token 是否过期
    if is_token_expired(account):
        logger.debug(f"Token expired or missing for account '{account.id}', refreshing")
        await refresh_token(account)

    if not account.access_token:
        raise TokenRefreshError(account.id, "Unable to get valid access_token")

    return account.access_token


async def get_auth_headers(account: AccountConfig) -> Dict[str, str]:
    """
    获取指定账号的认证请求头

    Args:
        account: 账号配置对象

    Returns:
        Dict[str, str]: 包含 Authorization 的请求头
    """
    access_token = await ensure_valid_token(account)
    return {
        "Authorization": f"Bearer {access_token}"
    }
