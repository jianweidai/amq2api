"""
认证模块
负责 Token 刷新和管理（支持多账号）
支持 AWS OIDC 设备授权流程（Device Authorization Grant）
"""
import httpx
import logging
import uuid
import time
import asyncio
from typing import Dict, Any, Tuple, Optional
from account_manager import get_random_account, update_account_tokens, update_refresh_status

logger = logging.getLogger(__name__)

# ============== OIDC 设备授权常量 ==============
OIDC_BASE = "https://oidc.us-east-1.amazonaws.com"
REGISTER_URL = f"{OIDC_BASE}/client/register"
DEVICE_AUTH_URL = f"{OIDC_BASE}/device_authorization"
TOKEN_URL = f"{OIDC_BASE}/token"
START_URL = "https://view.awsapps.com/start"

# HTTP 请求头（模拟 AWS CLI）
USER_AGENT = "aws-sdk-rust/1.3.9 os/windows lang/rust/1.87.0"
X_AMZ_USER_AGENT = "aws-sdk-rust/1.3.9 ua/2.1 api/ssooidc/1.88.0 os/windows lang/rust/1.87.0 m/E app/AmazonQ-For-CLI"
AMZ_SDK_REQUEST = "attempt=1; max=3"


def _make_oidc_headers() -> Dict[str, str]:
    """构造 OIDC 请求头"""
    return {
        "content-type": "application/json",
        "user-agent": USER_AGENT,
        "x-amz-user-agent": X_AMZ_USER_AGENT,
        "amz-sdk-request": AMZ_SDK_REQUEST,
        "amz-sdk-invocation-id": str(uuid.uuid4()),
    }


async def register_oidc_client() -> Tuple[str, str]:
    """
    注册 OIDC 客户端，返回 (clientId, clientSecret)
    
    Returns:
        Tuple[str, str]: (clientId, clientSecret)
    
    Raises:
        httpx.HTTPError: HTTP 请求失败
    """
    payload = {
        "clientName": "Amazon Q Developer for command line",
        "clientType": "public",
        "scopes": [
            "codewhisperer:completions",
            "codewhisperer:analysis",
            "codewhisperer:conversations",
        ],
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            REGISTER_URL,
            json=payload,
            headers=_make_oidc_headers()
        )
        response.raise_for_status()
        data = response.json()
        logger.info("OIDC 客户端注册成功")
        return data["clientId"], data["clientSecret"]


async def start_device_authorization(client_id: str, client_secret: str) -> Dict[str, Any]:
    """
    启动设备授权流程
    
    Args:
        client_id: OIDC 客户端 ID
        client_secret: OIDC 客户端密钥
    
    Returns:
        Dict 包含:
        - deviceCode: 设备码（用于后续轮询）
        - interval: 轮询间隔（秒）
        - expiresIn: 过期时间（秒）
        - verificationUriComplete: 完整验证链接（用户需要访问）
        - userCode: 用户码（显示给用户）
    
    Raises:
        httpx.HTTPError: HTTP 请求失败
    """
    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "startUrl": START_URL,
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DEVICE_AUTH_URL,
            json=payload,
            headers=_make_oidc_headers()
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"设备授权已启动，用户码: {data.get('userCode')}")
        return data


async def poll_device_token(
    client_id: str,
    client_secret: str,
    device_code: str,
    interval: int,
    expires_in: int,
    max_timeout_sec: int = 300,
) -> Dict[str, Any]:
    """
    轮询 token 端点，直到用户完成授权或超时
    
    Args:
        client_id: OIDC 客户端 ID
        client_secret: OIDC 客户端密钥
        device_code: 设备码
        interval: 轮询间隔（秒）
        expires_in: 过期时间（秒）
        max_timeout_sec: 最大等待时间（秒），默认 5 分钟
    
    Returns:
        Dict 包含:
        - accessToken: 访问令牌
        - refreshToken: 刷新令牌（可选）
    
    Raises:
        TimeoutError: 超时未授权
        httpx.HTTPError: HTTP 错误
    """
    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "deviceCode": device_code,
        "grantType": "urn:ietf:params:oauth:grant-type:device_code",
    }

    deadline = min(time.time() + expires_in, time.time() + max_timeout_sec)
    poll_interval = max(1, int(interval or 1))

    async with httpx.AsyncClient(timeout=30.0) as client:
        while time.time() < deadline:
            response = await client.post(
                TOKEN_URL,
                json=payload,
                headers=_make_oidc_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("设备授权成功，已获取 token")
                return data
            
            if response.status_code == 400:
                err = response.json()
                if err.get("error") == "authorization_pending":
                    # 用户尚未完成授权，继续等待
                    await asyncio.sleep(poll_interval)
                    continue
                # 其他错误
                response.raise_for_status()
            
            response.raise_for_status()

    raise TimeoutError("设备授权超时，用户未在规定时间内完成授权")


class TokenRefreshError(Exception):
    """Token 刷新失败异常"""
    pass


class NoAccountAvailableError(Exception):
    """无可用账号异常"""
    pass


async def refresh_account_token(account: Dict[str, Any]) -> Dict[str, Any]:
    """
    刷新指定账号的 access_token

    Args:
        account: 账号信息字典

    Returns:
        Dict[str, Any]: 更新后的账号信息

    Raises:
        TokenRefreshError: 刷新失败时抛出异常
    """
    account_id = account["id"]

    if not account.get("clientId") or not account.get("clientSecret") or not account.get("refreshToken"):
        logger.error(f"账号 {account_id} 缺少必需的刷新凭证")
        update_refresh_status(account_id, "failed_missing_credentials")
        raise TokenRefreshError("账号缺少 clientId/clientSecret/refreshToken")

    try:
        logger.info(f"开始刷新账号 {account_id} 的 access_token")

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            payload = {
                "grantType": "refresh_token",
                "refreshToken": account["refreshToken"],
                "clientId": account["clientId"],
                "clientSecret": account["clientSecret"]
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "aws-sdk-rust/1.3.9 os/macos lang/rust/1.87.0",
                "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/ssooidc/1.88.0 os/macos lang/rust/1.87.0 m/E app/AmazonQ-For-CLI",
                "Amz-Sdk-Request": "attempt=1; max=3",
                "Amz-Sdk-Invocation-Id": str(uuid.uuid4()),
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br"
            }

            response = await http_client.post(
                "https://oidc.us-east-1.amazonaws.com/token",
                json=payload,
                headers=headers
            )

            response.raise_for_status()
            response_data = response.json()

            new_access_token = response_data.get("accessToken")
            new_refresh_token = response_data.get("refreshToken", account.get("refreshToken"))

            if not new_access_token:
                raise TokenRefreshError("响应中缺少 accessToken")

            # 更新数据库
            updated_account = update_account_tokens(
                account_id,
                new_access_token,
                new_refresh_token,
                "success"
            )

            logger.info(f"账号 {account_id} Token 刷新成功")
            return updated_account

    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        logger.error(f"账号 {account_id} Token 刷新失败 - HTTP 错误: {e.response.status_code} - {error_text}")

        # 检测账号是否被封（invalid_grant 错误）
        if e.response.status_code == 400 and "invalid_grant" in error_text:
            logger.error(f"账号 {account_id} 已被封禁（invalid_grant），自动禁用")
            from datetime import datetime
            suspend_info = {
                "suspended": True,
                "suspended_at": datetime.now().isoformat(),
                "suspend_reason": "INVALID_GRANT",
                "error_detail": error_text
            }
            # 获取当前账号信息
            from account_manager import get_account
            account_data = get_account(account_id)
            if account_data:
                current_other = account_data.get('other') or {}
                current_other.update(suspend_info)
                from account_manager import update_account
                update_account(account_id, enabled=False, other=current_other)
            update_refresh_status(account_id, "failed_invalid_grant")
            raise TokenRefreshError(f"账号已被封禁: {error_text}") from e

        update_refresh_status(account_id, f"failed_{e.response.status_code}")
        raise TokenRefreshError(f"HTTP 错误: {e.response.status_code}") from e
    except httpx.RequestError as e:
        logger.error(f"账号 {account_id} Token 刷新失败 - 网络错误: {str(e)}")
        update_refresh_status(account_id, "failed_network")
        raise TokenRefreshError(f"网络错误: {str(e)}") from e
    except Exception as e:
        logger.error(f"账号 {account_id} Token 刷新失败 - 未知错误: {str(e)}")
        update_refresh_status(account_id, "failed_unknown")
        raise TokenRefreshError(f"未知错误: {str(e)}") from e


async def get_account_with_token() -> Tuple[Optional[Dict[str, Any]], str]:
    """
    获取一个随机账号及其有效的 access_token
    如果数据库中没有账号，回退到使用 .env 配置（向后兼容）
    支持账号被封禁时自动切换到其他可用账号

    Returns:
        Tuple[Optional[Dict[str, Any]], str]: (账号信息或None, access_token)

    Raises:
        NoAccountAvailableError: 无可用账号且 .env 配置不完整
        TokenRefreshError: Token 刷新失败
    """
    # 最多尝试 3 次切换账号
    max_retries = 3
    tried_account_ids = set()

    for attempt in range(max_retries):
        account = get_random_account(account_type="amazonq")

        # 如果数据库中有账号，使用多账号模式
        if account:
            account_id = account.get("id")

            # 避免重复尝试同一个账号
            if account_id in tried_account_ids:
                logger.warning(f"账号 {account_id} 已尝试过，跳过")
                continue

            tried_account_ids.add(account_id)

            try:
                access_token = account.get("accessToken")
                token_expired = False

                # 检查 JWT token 是否过期
                if access_token:
                    try:
                        import base64
                        import json
                        from datetime import datetime

                        parts = access_token.split('.')
                        if len(parts) == 3:
                            payload = base64.urlsafe_b64decode(parts[1] + '==')
                            token_data = json.loads(payload)
                            exp = token_data.get('exp')
                            if exp:
                                exp_time = datetime.fromtimestamp(exp)
                                if datetime.now() >= exp_time:
                                    token_expired = True
                                    logger.info(f"账号 {account['id']} 的 accessToken 已过期")
                    except Exception as e:
                        logger.warning(f"解析 JWT token 失败: {e}")

                # 如果没有 access_token 或 token 已过期，尝试刷新
                if not access_token or token_expired:
                    logger.info(f"账号 {account['id']} 需要刷新 token")
                    account = await refresh_account_token(account)
                    access_token = account.get("accessToken")

                    if not access_token:
                        raise TokenRefreshError("刷新后仍无法获取 accessToken")

                return account, access_token

            except TokenRefreshError as e:
                error_msg = str(e)
                # 如果是账号被封禁错误，尝试切换到下一个账号
                if "账号已被封禁" in error_msg or "invalid_grant" in error_msg.lower():
                    logger.warning(f"账号 {account_id} 被封禁，尝试切换到其他账号 (尝试 {attempt + 1}/{max_retries})")
                    max_retries = 999999
                    continue
                else:
                    # 其他类型的刷新错误，直接抛出
                    raise
        else:
            # 没有可用的多账号，跳出循环进入单账号模式
            break

    # 如果所有账号都被封禁或没有账号，检查是否还有可用账号
    account = get_random_account()
    if account:
        # 还有账号但都尝试过了
        raise NoAccountAvailableError("所有可用账号都已被封禁或刷新失败")

    # 回退到单账号模式（使用 .env 配置）
    logger.info("数据库中没有账号，回退到单账号模式（使用 .env 配置）")
    from config import read_global_config

    try:
        config = await read_global_config()

        # 检查 token 是否过期
        if config.is_token_expired():
            logger.info("Token 已过期，开始刷新")
            await refresh_legacy_token()
            config = await read_global_config()

        if not config.access_token:
            raise NoAccountAvailableError("没有可用账号且 .env 配置不完整")

        return None, config.access_token
    except Exception as e:
        logger.error(f"单账号模式失败: {e}")
        raise NoAccountAvailableError("没有可用账号且 .env 配置不完整") from e


async def refresh_legacy_token() -> bool:
    """
    刷新单账号模式的 token（向后兼容）

    Returns:
        bool: 刷新成功返回 True
    """
    from config import read_global_config, update_global_config

    config = await read_global_config()

    try:
        logger.info("开始刷新单账号模式的 access_token")

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            payload = {
                "grantType": "refresh_token",
                "refreshToken": config.refresh_token,
                "clientId": config.client_id,
                "clientSecret": config.client_secret
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "aws-sdk-rust/1.3.9 os/macos lang/rust/1.87.0",
                "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/ssooidc/1.88.0 os/macos lang/rust/1.87.0 m/E app/AmazonQ-For-CLI",
                "Amz-Sdk-Request": "attempt=1; max=3",
                "Amz-Sdk-Invocation-Id": str(uuid.uuid4()),
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br"
            }

            response = await http_client.post(
                config.token_endpoint,
                json=payload,
                headers=headers
            )

            response.raise_for_status()
            response_data = response.json()

            new_access_token = response_data.get("accessToken")
            new_refresh_token = response_data.get("refreshToken")
            expires_in = response_data.get("expiresIn")

            if not new_access_token:
                raise TokenRefreshError("响应中缺少 accessToken")

            await update_global_config(
                access_token=new_access_token,
                refresh_token=new_refresh_token if new_refresh_token else None,
                expires_in=int(expires_in) if expires_in else 3600
            )

            logger.info("单账号模式 Token 刷新成功")
            return True

    except httpx.HTTPStatusError as e:
        logger.error(f"单账号模式 Token 刷新失败 - HTTP 错误: {e.response.status_code}")
        raise TokenRefreshError(f"HTTP 错误: {e.response.status_code}") from e
    except Exception as e:
        logger.error(f"单账号模式 Token 刷新失败: {str(e)}")
        raise TokenRefreshError(f"刷新失败: {str(e)}") from e


async def get_auth_headers_for_account(account: Dict[str, Any]) -> Dict[str, str]:
    """
    为指定账号获取认证头

    Args:
        account: 账号信息字典

    Returns:
        Dict[str, str]: 认证头

    Raises:
        TokenRefreshError: Token 刷新失败时抛出异常
    """
    access_token = account.get("accessToken")
    token_expired = False

    # 检查 JWT token 是否过期
    if access_token:
        try:
            import base64
            import json
            from datetime import datetime

            parts = access_token.split('.')
            if len(parts) == 3:
                payload = base64.urlsafe_b64decode(parts[1] + '==')
                token_data = json.loads(payload)
                exp = token_data.get('exp')
                if exp:
                    exp_time = datetime.fromtimestamp(exp)
                    if datetime.now() >= exp_time:
                        token_expired = True
                        logger.info(f"账号 {account['id']} 的 accessToken 已过期")
        except Exception as e:
            logger.warning(f"解析 JWT token 失败: {e}")

    # 如果没有 access_token 或 token 已过期，尝试刷新
    if not access_token or token_expired:
        logger.info(f"账号 {account['id']} 需要刷新 token")
        account = await refresh_account_token(account)
        access_token = account.get("accessToken")

        if not access_token:
            raise TokenRefreshError("刷新后仍无法获取 accessToken")

    return {
        "Authorization": f"Bearer {access_token}"
    }


async def get_auth_headers_with_retry() -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    """
    获取认证头，支持 401/403 重试机制
    支持多账号模式和单账号模式（向后兼容）

    Returns:
        Tuple[Optional[Dict[str, Any]], Dict[str, str]]: (账号信息或None, 认证头)
    """
    account, access_token = await get_account_with_token()

    return account, {
        "Authorization": f"Bearer {access_token}"
    }