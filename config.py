"""
配置管理模块
负责读取和更新全局配置,支持多账号管理
"""
import os
import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from account_config import AccountConfig, LoadBalanceStrategy
from account_pool import AccountPool
from exceptions import InvalidAccountConfigError

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

# Token 缓存目录和文件路径
TOKEN_CACHE_DIR = Path.home() / ".amazonq_token_cache"
TOKEN_CACHE_FILE = Path.home() / ".amazonq_token_cache.json"  # 旧版单账号缓存文件(兼容)


@dataclass
class GlobalConfig:
    """全局配置类(仅包含非账号相关配置)"""
    # API Endpoints
    api_endpoint: str = "https://q.us-east-1.amazonaws.com/"
    token_endpoint: str = "https://oidc.us-east-1.amazonaws.com/token"

    # Gemini 配置
    gemini_enabled: bool = False
    gemini_client_id: Optional[str] = None
    gemini_client_secret: Optional[str] = None
    gemini_refresh_token: Optional[str] = None
    gemini_api_endpoint: str = "https://daily-cloudcode-pa.sandbox.googleapis.com"

    # 服务配置
    port: int = 8001

    # Token 统计配置
    zero_input_token_models: list = field(default_factory=lambda: ["haiku"])

    # 多账号配置
    multi_account_enabled: bool = False

    # 负载均衡配置
    load_balance_strategy: LoadBalanceStrategy = LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN

    # 熔断器配置
    circuit_breaker_enabled: bool = True
    circuit_breaker_error_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 300  # 秒

    # 健康检查配置
    health_check_interval: int = 300  # 秒


# 全局配置实例
_global_config: Optional[GlobalConfig] = None
_account_pool: Optional[AccountPool] = None
_config_lock = asyncio.Lock()


def get_account_cache_dir() -> Path:
    """获取账号缓存目录"""
    TOKEN_CACHE_DIR.mkdir(mode=0o700, exist_ok=True)
    return TOKEN_CACHE_DIR


def get_account_cache_file(account_id: str) -> Path:
    """获取账号缓存文件路径"""
    return get_account_cache_dir() / f"{account_id}.json"


def _load_account_cache(account_id: str) -> Optional[dict]:
    """
    从文件加载账号 token 缓存

    Args:
        account_id: 账号 ID

    Returns:
        Optional[dict]: 缓存数据,如果不存在或过期则返回 None
    """
    try:
        cache_file = get_account_cache_file(account_id)
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                cache = json.load(f)
                # 检查是否过期
                if 'expires_at' in cache:
                    expires_at = datetime.fromisoformat(cache['expires_at'])
                    if datetime.now() < expires_at:
                        logger.info(f"Loaded token cache for account '{account_id}', expires at {expires_at}")
                        return cache
    except Exception as e:
        logger.warning(f"Failed to load token cache for account '{account_id}': {e}")
    return None


def _save_account_cache(account_id: str, access_token: str, refresh_token: str, expires_at: datetime) -> None:
    """
    保存账号 token 到缓存文件

    Args:
        account_id: 账号 ID
        access_token: 访问令牌
        refresh_token: 刷新令牌
        expires_at: 过期时间
    """
    try:
        cache = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at.isoformat()
        }
        cache_file = get_account_cache_file(account_id)
        with open(cache_file, 'w') as f:
            json.dump(cache, f, indent=2)
        # 设置文件权限为仅当前用户可读写
        cache_file.chmod(0o600)
        logger.info(f"Saved token cache for account '{account_id}'")
    except Exception as e:
        logger.error(f"Failed to save token cache for account '{account_id}': {e}")


def _load_token_cache() -> Optional[dict]:
    """从旧版文件加载 token 缓存(兼容单账号模式)"""
    try:
        if TOKEN_CACHE_FILE.exists():
            with open(TOKEN_CACHE_FILE, 'r') as f:
                cache = json.load(f)
                # 检查是否过期
                if 'expires_at' in cache:
                    expires_at = datetime.fromisoformat(cache['expires_at'])
                    if datetime.now() < expires_at:
                        return cache
    except Exception as e:
        logger.warning(f"Failed to load legacy token cache: {e}")
    return None


def _save_token_cache(access_token: str, refresh_token: str, expires_at: datetime) -> None:
    """保存 token 到旧版文件(兼容单账号模式)"""
    try:
        cache = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at.isoformat()
        }
        with open(TOKEN_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
        # 设置文件权限为仅当前用户可读写
        TOKEN_CACHE_FILE.chmod(0o600)
        logger.info("Saved legacy token cache")
    except Exception as e:
        logger.error(f"Failed to save legacy token cache: {e}")


def _load_accounts_from_env() -> list[AccountConfig]:
    """
    从环境变量加载多账号配置

    环境变量格式:
        AMAZONQ_ACCOUNT_COUNT=3
        AMAZONQ_ACCOUNT_1_ID=primary
        AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=xxx
        AMAZONQ_ACCOUNT_1_CLIENT_ID=xxx
        AMAZONQ_ACCOUNT_1_CLIENT_SECRET=xxx
        AMAZONQ_ACCOUNT_1_PROFILE_ARN=  # 可选
        AMAZONQ_ACCOUNT_1_WEIGHT=10
        AMAZONQ_ACCOUNT_1_ENABLED=true

    Returns:
        list[AccountConfig]: 账号配置列表

    Raises:
        InvalidAccountConfigError: 配置无效时抛出
    """
    accounts = []
    account_count = int(os.getenv("AMAZONQ_ACCOUNT_COUNT", "0"))

    if account_count == 0:
        # 尝试从单账号配置加载(向后兼容)
        refresh_token = os.getenv("AMAZONQ_REFRESH_TOKEN", "")
        client_id = os.getenv("AMAZONQ_CLIENT_ID", "")
        client_secret = os.getenv("AMAZONQ_CLIENT_SECRET", "")

        if not refresh_token or not client_id or not client_secret:
            raise InvalidAccountConfigError(
                "No accounts configured. Set AMAZONQ_ACCOUNT_COUNT or use legacy single account config."
            )

        # 单账号模式
        account = AccountConfig(
            id="default",
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            profile_arn=os.getenv("AMAZONQ_PROFILE_ARN") or None,
            weight=10,
            enabled=True,
        )

        # 尝试从旧版缓存加载
        cache = _load_token_cache()
        if cache:
            account.access_token = cache.get('access_token')
            account.refresh_token = cache.get('refresh_token', account.refresh_token)
            account.token_expires_at = datetime.fromisoformat(cache['expires_at'])

        accounts.append(account)
        logger.info("Loaded single account configuration (legacy mode)")
        return accounts

    # 多账号模式
    for i in range(1, account_count + 1):
        prefix = f"AMAZONQ_ACCOUNT_{i}_"

        account_id = os.getenv(f"{prefix}ID", f"account_{i}")
        refresh_token = os.getenv(f"{prefix}REFRESH_TOKEN", "")
        client_id = os.getenv(f"{prefix}CLIENT_ID", "")
        client_secret = os.getenv(f"{prefix}CLIENT_SECRET", "")
        profile_arn = os.getenv(f"{prefix}PROFILE_ARN") or None
        weight = int(os.getenv(f"{prefix}WEIGHT", "10"))
        enabled = os.getenv(f"{prefix}ENABLED", "true").lower() == "true"

        # 验证必需字段
        if not refresh_token:
            raise InvalidAccountConfigError(f"Account {i}: REFRESH_TOKEN is required")
        if not client_id:
            raise InvalidAccountConfigError(f"Account {i}: CLIENT_ID is required")
        if not client_secret:
            raise InvalidAccountConfigError(f"Account {i}: CLIENT_SECRET is required")

        account = AccountConfig(
            id=account_id,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            profile_arn=profile_arn,
            weight=weight,
            enabled=enabled,
        )

        # 尝试从缓存加载 token
        cache = _load_account_cache(account_id)
        if cache:
            account.access_token = cache.get('access_token')
            account.refresh_token = cache.get('refresh_token', account.refresh_token)
            account.token_expires_at = datetime.fromisoformat(cache['expires_at'])

        accounts.append(account)

    logger.info(f"Loaded {len(accounts)} accounts from environment variables")
    return accounts


async def load_account_pool() -> AccountPool:
    """
    加载账号池

    Returns:
        AccountPool: 账号池实例

    Raises:
        InvalidAccountConfigError: 配置无效时抛出
    """
    global _account_pool, _global_config

    async with _config_lock:
        if _account_pool is not None:
            return _account_pool

        # 直接使用全局配置(避免重入锁)
        if _global_config is None:
            raise RuntimeError("Global config must be initialized before loading account pool")

        config = _global_config

        # 创建账号池
        _account_pool = AccountPool(
            strategy=config.load_balance_strategy,
            circuit_breaker_enabled=config.circuit_breaker_enabled,
            circuit_breaker_error_threshold=config.circuit_breaker_error_threshold,
            circuit_breaker_recovery_timeout=config.circuit_breaker_recovery_timeout,
        )

        # 加载账号
        accounts = _load_accounts_from_env()
        for account in accounts:
            _account_pool.add_account(account)

        # 设置多账号模式标志
        config.multi_account_enabled = len(accounts) > 1

        logger.info(
            f"Account pool initialized with {len(accounts)} accounts, "
            f"multi_account_enabled={config.multi_account_enabled}"
        )

        return _account_pool


async def get_account_pool() -> AccountPool:
    """
    获取账号池实例

    Returns:
        AccountPool: 账号池实例

    Raises:
        RuntimeError: 账号池未初始化时抛出
    """
    if _account_pool is None:
        return await load_account_pool()
    return _account_pool


async def read_global_config() -> GlobalConfig:
    """
    读取全局配置(异步安全)
    如果配置未初始化,则从环境变量加载

    Returns:
        GlobalConfig: 全局配置实例
    """
    global _global_config

    async with _config_lock:
        if _global_config is None:
            # 从环境变量初始化配置
            zero_token_models = os.getenv("ZERO_INPUT_TOKEN_MODELS", "haiku")

            # 负载均衡策略
            lb_strategy_str = os.getenv("LOAD_BALANCE_STRATEGY", "weighted_round_robin")
            try:
                lb_strategy = LoadBalanceStrategy(lb_strategy_str)
            except ValueError:
                logger.warning(f"Invalid load balance strategy '{lb_strategy_str}', using default")
                lb_strategy = LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN

            _global_config = GlobalConfig(
                api_endpoint=os.getenv("AMAZONQ_API_ENDPOINT", "https://q.us-east-1.amazonaws.com/"),
                token_endpoint=os.getenv("AMAZONQ_TOKEN_ENDPOINT", "https://oidc.us-east-1.amazonaws.com/token"),
                gemini_enabled=os.getenv("GEMINI_ENABLED", "true").lower() == "true",
                gemini_client_id=os.getenv("GEMINI_CLIENT_ID") or None,
                gemini_client_secret=os.getenv("GEMINI_CLIENT_SECRET") or None,
                gemini_refresh_token=os.getenv("GEMINI_REFRESH_TOKEN") or None,
                gemini_api_endpoint=os.getenv("GEMINI_API_ENDPOINT", "https://daily-cloudcode-pa.sandbox.googleapis.com"),
                port=int(os.getenv("PORT", "8080")),
                zero_input_token_models=[m.strip() for m in zero_token_models.split(",")],
                load_balance_strategy=lb_strategy,
                circuit_breaker_enabled=os.getenv("CIRCUIT_BREAKER_ENABLED", "true").lower() == "true",
                circuit_breaker_error_threshold=int(os.getenv("CIRCUIT_BREAKER_ERROR_THRESHOLD", "5")),
                circuit_breaker_recovery_timeout=int(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "300")),
                health_check_interval=int(os.getenv("HEALTH_CHECK_INTERVAL", "300")),
            )

            logger.info(
                f"Global config initialized: port={_global_config.port}, "
                f"strategy={_global_config.load_balance_strategy.value}"
            )

        return _global_config


async def save_account_token(
    account_id: str,
    access_token: str,
    refresh_token: str,
    expires_at: datetime
) -> None:
    """
    保存账号 Token 到缓存

    Args:
        account_id: 账号 ID
        access_token: 访问令牌
        refresh_token: 刷新令牌
        expires_at: 过期时间
    """
    # 保存到多账号缓存
    _save_account_cache(account_id, access_token, refresh_token, expires_at)

    # 如果是单账号模式,也保存到旧版缓存(兼容)
    config = await read_global_config()
    if not config.multi_account_enabled and account_id == "default":
        _save_token_cache(access_token, refresh_token, expires_at)


async def save_all_account_caches() -> None:
    """保存所有账号的 Token 缓存"""
    pool = await get_account_pool()
    for account in pool.get_all_accounts():
        if account.access_token and account.token_expires_at:
            await save_account_token(
                account.id,
                account.access_token,
                account.refresh_token,
                account.token_expires_at
            )
    logger.info("Saved all account token caches")


def get_config_sync() -> GlobalConfig:
    """
    同步获取配置(仅用于非异步上下文)
    注意: 如果配置未初始化,会抛出异常

    Returns:
        GlobalConfig: 全局配置实例

    Raises:
        RuntimeError: 配置未初始化时抛出
    """
    if _global_config is None:
        raise RuntimeError("Configuration not initialized. Call read_global_config() first.")
    return _global_config
