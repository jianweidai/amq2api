"""
账号管理模块
负责多账号的数据库操作和管理
支持 SQLite（默认）和 MySQL（可选）
"""
import sqlite3
import json
import uuid
import time
import random
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ============== 账号冷却机制 ==============
# 存储账号冷却结束时间 {account_id: cooldown_end_timestamp}
_account_cooldowns: Dict[str, float] = {}
# 默认冷却时间（秒）
DEFAULT_COOLDOWN_SECONDS = 300  # 5 分钟


def set_account_cooldown(account_id: str, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS) -> None:
    """设置账号冷却时间
    
    Args:
        account_id: 账号 ID
        cooldown_seconds: 冷却时间（秒），默认 5 分钟
    """
    cooldown_end = time.time() + cooldown_seconds
    _account_cooldowns[account_id] = cooldown_end
    logger.info(f"账号 {account_id} 进入冷却期 {cooldown_seconds} 秒，将在 {datetime.fromtimestamp(cooldown_end).strftime('%H:%M:%S')} 后恢复")


def is_account_in_cooldown(account_id: str) -> bool:
    """检查账号是否在冷却中
    
    Args:
        account_id: 账号 ID
    
    Returns:
        True 如果账号在冷却中，False 如果可用
    """
    if account_id not in _account_cooldowns:
        return False
    
    cooldown_end = _account_cooldowns[account_id]
    if time.time() >= cooldown_end:
        # 冷却已结束，清除记录
        del _account_cooldowns[account_id]
        logger.info(f"账号 {account_id} 冷却期已结束，恢复可用")
        return False
    
    return True


def get_account_cooldown_remaining(account_id: str) -> int:
    """获取账号剩余冷却时间（秒）
    
    Args:
        account_id: 账号 ID
    
    Returns:
        剩余冷却时间（秒），如果不在冷却中返回 0
    """
    if account_id not in _account_cooldowns:
        return 0
    
    remaining = _account_cooldowns[account_id] - time.time()
    return max(0, int(remaining))


def clear_account_cooldown(account_id: str) -> None:
    """清除账号冷却状态
    
    Args:
        account_id: 账号 ID
    """
    if account_id in _account_cooldowns:
        del _account_cooldowns[account_id]
        logger.info(f"账号 {account_id} 冷却状态已清除")

# ============== 数据库配置 ==============

# MySQL 配置（从环境变量读取）
MYSQL_HOST = os.getenv("MYSQL_HOST", "").strip()
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "amq2api").strip()

# 判断是否使用 MySQL
USE_MYSQL = bool(MYSQL_HOST and MYSQL_USER and MYSQL_DATABASE)

# 表名前缀（MySQL 使用，SQLite 保持原样以兼容现有数据）
TABLE_PREFIX = "amq2api_"
ACCOUNTS_TABLE = f"{TABLE_PREFIX}accounts" if USE_MYSQL else "accounts"

# SQLite 数据库路径
if os.path.exists("/app/data"):
    SQLITE_DB_PATH = Path("/app/data/accounts.db")
else:
    SQLITE_DB_PATH = Path(__file__).parent.parent / "data" / "accounts.db"

# MySQL 连接池
_mysql_pool = None


def _get_db_type() -> str:
    """获取当前使用的数据库类型"""
    return "mysql" if USE_MYSQL else "sqlite"


# ============== SQLite 实现 ==============

def _sqlite_ensure_db():
    """初始化 SQLite 数据库表结构"""
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                label TEXT,
                clientId TEXT,
                clientSecret TEXT,
                refreshToken TEXT,
                accessToken TEXT,
                other TEXT,
                last_refresh_time TEXT,
                last_refresh_status TEXT,
                created_at TEXT,
                updated_at TEXT,
                enabled INTEGER DEFAULT 1,
                type TEXT DEFAULT 'amazonq',
                rate_limit_per_hour INTEGER DEFAULT 20
            )
            """
        )

        # 迁移：为已存在的表添加新字段
        cursor = conn.execute("PRAGMA table_info(accounts)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'type' not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN type TEXT DEFAULT 'amazonq'")
        if 'weight' not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN weight INTEGER DEFAULT 50")
        if 'rate_limit_per_hour' not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN rate_limit_per_hour INTEGER DEFAULT 20")

        # 创建调用记录表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                model TEXT,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
            """
        )

        # 创建索引以加速查询
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_call_logs_account_timestamp
            ON call_logs(account_id, timestamp)
            """
        )

        conn.commit()


def _sqlite_conn() -> sqlite3.Connection:
    """创建 SQLite 数据库连接"""
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ============== MySQL 实现 ==============

def _mysql_get_connection():
    """获取 MySQL 连接"""
    import pymysql
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )


def _mysql_ensure_db():
    """初始化 MySQL 数据库表结构"""
    import pymysql
    
    # 先连接不指定数据库，创建数据库
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        charset='utf8mb4'
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
    finally:
        conn.close()
    
    # 连接到指定数据库，创建表
    conn = _mysql_get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{ACCOUNTS_TABLE}` (
                    id VARCHAR(36) PRIMARY KEY,
                    label VARCHAR(255),
                    clientId VARCHAR(255),
                    clientSecret TEXT,
                    refreshToken TEXT,
                    accessToken TEXT,
                    other LONGTEXT,
                    last_refresh_time VARCHAR(32),
                    last_refresh_status VARCHAR(32),
                    created_at VARCHAR(32),
                    updated_at VARCHAR(32),
                    enabled TINYINT DEFAULT 1,
                    type VARCHAR(32) DEFAULT 'amazonq',
                    weight INT DEFAULT 50,
                    rate_limit_per_hour INT DEFAULT 20
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            # 迁移：为已存在的表添加字段
            cursor.execute(f"SHOW COLUMNS FROM `{ACCOUNTS_TABLE}` LIKE 'weight'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE `{ACCOUNTS_TABLE}` ADD COLUMN weight INT DEFAULT 50")
            cursor.execute(f"SHOW COLUMNS FROM `{ACCOUNTS_TABLE}` LIKE 'rate_limit_per_hour'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE `{ACCOUNTS_TABLE}` ADD COLUMN rate_limit_per_hour INT DEFAULT 20")
            
            # 创建调用记录表
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{TABLE_PREFIX}call_logs` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id VARCHAR(36) NOT NULL,
                    timestamp VARCHAR(32) NOT NULL,
                    model VARCHAR(255),
                    INDEX idx_account_timestamp (account_id, timestamp),
                    FOREIGN KEY (account_id) REFERENCES `{ACCOUNTS_TABLE}`(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()
    finally:
        conn.close()


# ============== 通用函数 ==============

def _row_to_dict(r) -> Dict[str, Any]:
    """将数据库行转换为字典"""
    if isinstance(r, sqlite3.Row):
        d = dict(r)
    else:
        # MySQL DictCursor 已经是字典
        d = dict(r) if r else {}
    
    if d.get("other"):
        try:
            d["other"] = json.loads(d["other"])
        except Exception:
            pass
    if "enabled" in d and d["enabled"] is not None:
        d["enabled"] = bool(int(d["enabled"]))
    return d


def _ensure_db():
    """初始化数据库"""
    if USE_MYSQL:
        logger.info("=" * 50)
        logger.info("数据库配置: MySQL")
        logger.info(f"  主机: {MYSQL_HOST}:{MYSQL_PORT}")
        logger.info(f"  数据库: {MYSQL_DATABASE}")
        logger.info(f"  用户: {MYSQL_USER}")
        logger.info(f"  表名: {ACCOUNTS_TABLE}")
        logger.info("=" * 50)
        _mysql_ensure_db()
        logger.info("MySQL 数据库初始化完成")
    else:
        logger.info("=" * 50)
        logger.info("数据库配置: SQLite")
        logger.info(f"  路径: {SQLITE_DB_PATH}")
        logger.info(f"  表名: {ACCOUNTS_TABLE}")
        logger.info("=" * 50)
        _sqlite_ensure_db()
        logger.info("SQLite 数据库初始化完成")


# ============== 账号管理 API ==============

def list_enabled_accounts(account_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取所有启用的账号"""
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                if account_type:
                    cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` WHERE enabled=1 AND type=%s ORDER BY created_at DESC", (account_type,))
                else:
                    cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` WHERE enabled=1 ORDER BY created_at DESC")
                rows = cursor.fetchall()
                return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            if account_type:
                rows = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} WHERE enabled=1 AND type=? ORDER BY created_at DESC", (account_type,)).fetchall()
            else:
                rows = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} WHERE enabled=1 ORDER BY created_at DESC").fetchall()
            return [_row_to_dict(r) for r in rows]


def list_all_accounts() -> List[Dict[str, Any]]:
    """获取所有账号"""
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` ORDER BY created_at DESC")
                rows = cursor.fetchall()
                return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            rows = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} ORDER BY created_at DESC").fetchall()
            return [_row_to_dict(r) for r in rows]


def get_account(account_id: str) -> Optional[Dict[str, Any]]:
    """根据ID获取账号"""
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` WHERE id=%s", (account_id,))
                row = cursor.fetchone()
                return _row_to_dict(row) if row else None
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            row = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} WHERE id=?", (account_id,)).fetchone()
            return _row_to_dict(row) if row else None


def _weighted_random_choice(accounts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """根据权重随机选择账号（权重越大，被选中概率越高）
    
    权重直接作为选择概率的比例。
    例如：权重30的账号和权重70的账号，被选中概率分别是30%和70%
    
    Args:
        accounts: 账号列表
    
    Returns:
        随机选中的账号
    """
    if not accounts:
        return None
    
    if len(accounts) == 1:
        return accounts[0]
    
    # 直接使用权重作为选择概率（权重越大，被选中概率越高）
    weights = []
    for acc in accounts:
        weight = acc.get('weight', 50) or 50  # 默认权重 50
        weights.append(max(1, weight))  # 确保权重至少为 1
    
    # 使用 random.choices 进行加权随机选择
    selected = random.choices(accounts, weights=weights, k=1)
    return selected[0] if selected else None


def get_random_account(account_type: Optional[str] = None, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """随机选择一个启用的账号（支持权重，权重越大被选中概率越高）

    Args:
        account_type: 账号类型 ('amazonq' 或 'gemini')
        model: 请求的模型名称（用于 Gemini 账号配额检查）

    Returns:
        符合条件的随机账号，如果没有可用账号则返回 None
    """
    accounts = list_enabled_accounts(account_type)
    if not accounts:
        return None

    # 过滤掉冷却中和限流的账号
    available_accounts = []
    for acc in accounts:
        acc_id = acc.get('id')
        # 检查冷却
        if is_account_in_cooldown(acc_id):
            logger.debug(f"账号 {acc.get('label')} (ID: {acc_id[:8]}...) 在冷却中，跳过")
            continue
        # 检查限流
        if not check_rate_limit(acc_id):
            logger.debug(f"账号 {acc.get('label')} (ID: {acc_id[:8]}...) 已达到限流，跳过")
            continue
        available_accounts.append(acc)
    
    if not available_accounts:
        logger.warning(f"所有 {account_type or '全部'} 类型的账号都在冷却中或已限流")
        return None

    # 如果是 Gemini 账号且指定了模型，需要检查配额
    if account_type == "gemini" and model:
        filtered_accounts = []
        for account in available_accounts:
            if is_model_available_for_account(account, model):
                filtered_accounts.append(account)
        available_accounts = filtered_accounts

        if not available_accounts:
            logger.warning(f"没有可用的 Gemini 账号支持模型 {model}")
            return None

    return _weighted_random_choice(available_accounts)


def get_random_channel_by_model(model: str) -> Optional[str]:
    """根据模型智能选择渠道（按账号权重加权，权重越大被选中概率越高）

    直接从所有可用账号中按权重选择一个账号，然后返回该账号的渠道类型。
    例如：权重70的账号和权重30的账号，被选中概率分别是70%和30%。

    Args:
        model: 请求的模型名称

    Returns:
        渠道名称 ('amazonq', 'gemini', 或 'custom_api')，如果没有可用账号则返回 None
    """
    # Gemini 独占模型
    gemini_only_models = [
        'claude-sonnet-4-5-thinking',
        'claude-opus-4-5-thinking',
    ]

    # 如果是 Gemini 独占模型
    if model.startswith('gemini') or model in gemini_only_models:
        gemini_accounts = list_enabled_accounts(account_type='gemini')
        gemini_accounts = [acc for acc in gemini_accounts if not is_account_in_cooldown(acc.get('id'))]
        if gemini_accounts:
            return 'gemini'
        return None

    # Amazon Q 独占模型
    amazonq_only_models = [
        'claude-sonnet-4',
        'claude-haiku-4.5'
    ]

    # 如果是 Amazon Q 独占模型
    if model in amazonq_only_models:
        amazonq_accounts = list_enabled_accounts(account_type='amazonq')
        amazonq_accounts = [acc for acc in amazonq_accounts if not is_account_in_cooldown(acc.get('id'))]
        if amazonq_accounts:
            return 'amazonq'
        return None

    # 对于其他模型，从所有账号中按权重选择
    all_accounts = []
    
    amazonq_accounts = list_enabled_accounts(account_type='amazonq')
    gemini_accounts = list_enabled_accounts(account_type='gemini')
    custom_api_accounts = list_enabled_accounts(account_type='custom_api')
    
    # 过滤冷却中的账号并合并
    for acc in amazonq_accounts:
        if not is_account_in_cooldown(acc.get('id')):
            all_accounts.append(acc)
    for acc in gemini_accounts:
        if not is_account_in_cooldown(acc.get('id')):
            all_accounts.append(acc)
    for acc in custom_api_accounts:
        if not is_account_in_cooldown(acc.get('id')):
            all_accounts.append(acc)

    if not all_accounts:
        return None

    # 直接按权重选择账号（权重越小，被选中概率越大）
    selected_account = _weighted_random_choice(all_accounts)
    
    if selected_account:
        return selected_account.get('type', 'amazonq')
    
    return None


def create_account(
    label: Optional[str],
    client_id: str,
    client_secret: str,
    refresh_token: Optional[str] = None,
    access_token: Optional[str] = None,
    other: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
    account_type: str = "amazonq",
    weight: int = 50,
    rate_limit_per_hour: int = 20
) -> Dict[str, Any]:
    """创建新账号"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    acc_id = str(uuid.uuid4())
    other_str = json.dumps(other, ensure_ascii=False) if other else None

    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO `{ACCOUNTS_TABLE}` (id, label, clientId, clientSecret, refreshToken, accessToken, other, last_refresh_time, last_refresh_status, created_at, updated_at, enabled, type, weight, rate_limit_per_hour)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (acc_id, label, client_id, client_secret, refresh_token, access_token, other_str, None, "never", now, now, 1 if enabled else 0, account_type, weight, rate_limit_per_hour)
                )
                cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` WHERE id=%s", (acc_id,))
                row = cursor.fetchone()
                return _row_to_dict(row)
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                f"""
                INSERT INTO {ACCOUNTS_TABLE} (id, label, clientId, clientSecret, refreshToken, accessToken, other, last_refresh_time, last_refresh_status, created_at, updated_at, enabled, type, weight, rate_limit_per_hour)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (acc_id, label, client_id, client_secret, refresh_token, access_token, other_str, None, "never", now, now, 1 if enabled else 0, account_type, weight, rate_limit_per_hour)
            )
            conn.commit()
            row = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} WHERE id=?", (acc_id,)).fetchone()
            return _row_to_dict(row)


def update_account(
    account_id: str,
    label: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    refresh_token: Optional[str] = None,
    access_token: Optional[str] = None,
    other: Optional[Dict[str, Any]] = None,
    enabled: Optional[bool] = None,
    weight: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """更新账号信息"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    fields = []
    values: List[Any] = []

    if label is not None:
        fields.append("label")
        values.append(label)
    if client_id is not None:
        fields.append("clientId")
        values.append(client_id)
    if client_secret is not None:
        fields.append("clientSecret")
        values.append(client_secret)
    if refresh_token is not None:
        fields.append("refreshToken")
        values.append(refresh_token)
    if access_token is not None:
        fields.append("accessToken")
        values.append(access_token)
    if other is not None:
        fields.append("other")
        values.append(json.dumps(other, ensure_ascii=False))
    if enabled is not None:
        fields.append("enabled")
        values.append(1 if enabled else 0)
    if weight is not None:
        fields.append("weight")
        values.append(weight)

    if not fields:
        return get_account(account_id)

    fields.append("updated_at")
    values.append(now)
    values.append(account_id)

    if USE_MYSQL:
        set_clause = ", ".join([f"{f}=%s" for f in fields])
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"UPDATE `{ACCOUNTS_TABLE}` SET {set_clause} WHERE id=%s", values)
                if cursor.rowcount == 0:
                    return None
                cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` WHERE id=%s", (account_id,))
                row = cursor.fetchone()
                return _row_to_dict(row) if row else None
        finally:
            conn.close()
    else:
        set_clause = ", ".join([f"{f}=?" for f in fields])
        with _sqlite_conn() as conn:
            cur = conn.execute(f"UPDATE {ACCOUNTS_TABLE} SET {set_clause} WHERE id=?", values)
            conn.commit()
            if cur.rowcount == 0:
                return None
            row = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} WHERE id=?", (account_id,)).fetchone()
            return _row_to_dict(row) if row else None


def update_account_tokens(
    account_id: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    status: str = "success"
) -> Optional[Dict[str, Any]]:
    """更新账号的 token 信息"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                if refresh_token:
                    cursor.execute(
                        f"""
                        UPDATE `{ACCOUNTS_TABLE}`
                        SET accessToken=%s, refreshToken=%s, last_refresh_time=%s, last_refresh_status=%s, updated_at=%s
                        WHERE id=%s
                        """,
                        (access_token, refresh_token, now, status, now, account_id)
                    )
                else:
                    cursor.execute(
                        f"""
                        UPDATE `{ACCOUNTS_TABLE}`
                        SET accessToken=%s, last_refresh_time=%s, last_refresh_status=%s, updated_at=%s
                        WHERE id=%s
                        """,
                        (access_token, now, status, now, account_id)
                    )
                cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` WHERE id=%s", (account_id,))
                row = cursor.fetchone()
                return _row_to_dict(row) if row else None
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            if refresh_token:
                conn.execute(
                    f"""
                    UPDATE {ACCOUNTS_TABLE}
                    SET accessToken=?, refreshToken=?, last_refresh_time=?, last_refresh_status=?, updated_at=?
                    WHERE id=?
                    """,
                    (access_token, refresh_token, now, status, now, account_id)
                )
            else:
                conn.execute(
                    f"""
                    UPDATE {ACCOUNTS_TABLE}
                    SET accessToken=?, last_refresh_time=?, last_refresh_status=?, updated_at=?
                    WHERE id=?
                    """,
                    (access_token, now, status, now, account_id)
                )
            conn.commit()
            row = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} WHERE id=?", (account_id,)).fetchone()
            return _row_to_dict(row) if row else None


def update_refresh_status(account_id: str, status: str) -> None:
    """更新账号的刷新状态"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE `{ACCOUNTS_TABLE}` SET last_refresh_time=%s, last_refresh_status=%s, updated_at=%s WHERE id=%s",
                    (now, status, now, account_id)
                )
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                f"UPDATE {ACCOUNTS_TABLE} SET last_refresh_time=?, last_refresh_status=?, updated_at=? WHERE id=?",
                (now, status, now, account_id)
            )
            conn.commit()


def delete_account(account_id: str) -> bool:
    """删除账号"""
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{ACCOUNTS_TABLE}` WHERE id=%s", (account_id,))
                return cursor.rowcount > 0
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            cur = conn.execute(f"DELETE FROM {ACCOUNTS_TABLE} WHERE id=?", (account_id,))
            conn.commit()
            return cur.rowcount > 0


# ============== 配额管理 ==============

def is_model_available_for_account(account: Dict[str, Any], model: str) -> bool:
    """检查账号的指定模型是否有配额可用

    Args:
        account: 账号信息
        model: 模型名称

    Returns:
        True 如果模型可用，False 如果配额已用完或需要等待重置
    """
    other = account.get("other", {})
    if isinstance(other, str):
        try:
            other = json.loads(other)
        except json.JSONDecodeError:
            return True

    if not other:
        other = {}
    credits_info = other.get("creditsInfo", {})
    models = credits_info.get("models", {})

    if model not in models:
        return True

    model_info = models[model]
    remaining_fraction = model_info.get("remainingFraction", 1.0)
    reset_time_str = model_info.get("resetTime")

    if remaining_fraction > 0:
        return True

    if reset_time_str:
        try:
            reset_time = datetime.fromisoformat(reset_time_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)

            if now >= reset_time:
                account_id = account.get('id')
                if account_id and restore_model_quota_if_needed(account_id, model):
                    logger.info(f"模型 {model} 配额已自动恢复，账号 {account_id} 可用")
                    return True
        except Exception as e:
            logger.error(f"解析重置时间失败: {e}")

    logger.debug(f"模型 {model} 配额不足，账号 {account.get('id')} 不可用")
    return False


def restore_model_quota_if_needed(account_id: str, model: str) -> bool:
    """检查并恢复模型配额（如果已到重置时间）

    Args:
        account_id: 账号 ID
        model: 模型名称

    Returns:
        True 如果配额已恢复，False 如果仍需等待
    """
    account = get_account(account_id)
    if not account:
        logger.error(f"账号 {account_id} 不存在")
        return False

    other = account.get("other", {})
    if isinstance(other, str):
        try:
            other = json.loads(other)
        except json.JSONDecodeError:
            return False

    credits_info = other.get("creditsInfo", {})
    models = credits_info.get("models", {})

    if model not in models:
        return True

    model_info = models[model]
    remaining_fraction = model_info.get("remainingFraction", 1.0)
    reset_time_str = model_info.get("resetTime")

    if remaining_fraction > 0:
        return True

    if reset_time_str:
        try:
            reset_time = datetime.fromisoformat(reset_time_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)

            if now >= reset_time:
                model_info["remainingFraction"] = 1.0
                model_info["remainingPercent"] = 100
                update_account(account_id, other=other)
                logger.info(f"已自动恢复账号 {account_id} 的模型 {model} 配额")
                return True
        except Exception as e:
            logger.error(f"恢复配额时出错: {e}")

    return False


def mark_model_exhausted(account_id: str, model: str, reset_time: str) -> None:
    """标记账号的某个模型配额已用完

    Args:
        account_id: 账号 ID
        model: 模型名称
        reset_time: 配额重置时间 (ISO 8601 格式)
    """
    account = get_account(account_id)
    if not account:
        logger.error(f"账号 {account_id} 不存在")
        return

    other = account.get("other", {})
    if isinstance(other, str):
        try:
            other = json.loads(other)
        except json.JSONDecodeError:
            other = {}

    if "creditsInfo" not in other:
        other["creditsInfo"] = {"models": {}, "summary": {"totalModels": 0, "averageRemaining": 0}}

    credits_info = other["creditsInfo"]
    if "models" not in credits_info:
        credits_info["models"] = {}

    if model not in credits_info["models"]:
        credits_info["models"][model] = {}

    credits_info["models"][model]["remainingFraction"] = 0
    credits_info["models"][model]["remainingPercent"] = 0
    credits_info["models"][model]["resetTime"] = reset_time

    update_account(account_id, other=other)
    logger.info(f"已标记账号 {account_id} 的模型 {model} 配额用完，重置时间: {reset_time}")


# ============== 限流和统计功能 ==============

def record_api_call(account_id: str, model: Optional[str] = None) -> None:
    """记录账号的 API 调用

    Args:
        account_id: 账号 ID
        model: 使用的模型名称
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO `{TABLE_PREFIX}call_logs` (account_id, timestamp, model) VALUES (%s, %s, %s)",
                    (account_id, now, model)
                )
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                "INSERT INTO call_logs (account_id, timestamp, model) VALUES (?, ?, ?)",
                (account_id, now, model)
            )
            conn.commit()


def check_rate_limit(account_id: str) -> bool:
    """检查账号是否超过速率限制（滑动窗口）

    Args:
        account_id: 账号 ID

    Returns:
        True 如果未超过限制，False 如果已超过限制
    """
    account = get_account(account_id)
    if not account:
        return False

    rate_limit = account.get("rate_limit_per_hour", 20)

    # 计算一小时前的时间戳
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    one_hour_ago_str = one_hour_ago.strftime("%Y-%m-%dT%H:%M:%S")

    # 查询过去一小时内的调用次数
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) as count FROM `{TABLE_PREFIX}call_logs` WHERE account_id=%s AND timestamp >= %s",
                    (account_id, one_hour_ago_str)
                )
                result = cursor.fetchone()
                call_count = result['count'] if result else 0
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM call_logs WHERE account_id=? AND timestamp >= ?",
                (account_id, one_hour_ago_str)
            ).fetchone()
            call_count = result[0] if result else 0

    return call_count < rate_limit


def get_account_call_stats(account_id: str) -> Dict[str, Any]:
    """获取账号的调用统计信息

    Args:
        account_id: 账号 ID

    Returns:
        包含统计信息的字典
    """
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    one_hour_ago_str = one_hour_ago.strftime("%Y-%m-%dT%H:%M:%S")
    
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    one_day_ago_str = one_day_ago.strftime("%Y-%m-%dT%H:%M:%S")

    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                # 过去一小时
                cursor.execute(
                    f"SELECT COUNT(*) as count FROM `{TABLE_PREFIX}call_logs` WHERE account_id=%s AND timestamp >= %s",
                    (account_id, one_hour_ago_str)
                )
                result = cursor.fetchone()
                calls_last_hour = result['count'] if result else 0
                
                # 过去24小时
                cursor.execute(
                    f"SELECT COUNT(*) as count FROM `{TABLE_PREFIX}call_logs` WHERE account_id=%s AND timestamp >= %s",
                    (account_id, one_day_ago_str)
                )
                result = cursor.fetchone()
                calls_last_day = result['count'] if result else 0
                
                # 总调用次数
                cursor.execute(
                    f"SELECT COUNT(*) as count FROM `{TABLE_PREFIX}call_logs` WHERE account_id=%s",
                    (account_id,)
                )
                result = cursor.fetchone()
                total_calls = result['count'] if result else 0
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            # 过去一小时
            result = conn.execute(
                "SELECT COUNT(*) FROM call_logs WHERE account_id=? AND timestamp >= ?",
                (account_id, one_hour_ago_str)
            ).fetchone()
            calls_last_hour = result[0] if result else 0
            
            # 过去24小时
            result = conn.execute(
                "SELECT COUNT(*) FROM call_logs WHERE account_id=? AND timestamp >= ?",
                (account_id, one_day_ago_str)
            ).fetchone()
            calls_last_day = result[0] if result else 0
            
            # 总调用次数
            result = conn.execute(
                "SELECT COUNT(*) FROM call_logs WHERE account_id=?",
                (account_id,)
            ).fetchone()
            total_calls = result[0] if result else 0

    account = get_account(account_id)
    rate_limit = account.get("rate_limit_per_hour", 20) if account else 20

    return {
        "account_id": account_id,
        "calls_last_hour": calls_last_hour,
        "calls_last_day": calls_last_day,
        "total_calls": total_calls,
        "rate_limit_per_hour": rate_limit,
        "remaining_quota": max(0, rate_limit - calls_last_hour)
    }


def update_account_rate_limit(account_id: str, rate_limit_per_hour: int) -> Optional[Dict[str, Any]]:
    """更新账号的速率限制

    Args:
        account_id: 账号 ID
        rate_limit_per_hour: 每小时调用限制

    Returns:
        更新后的账号信息
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE `{ACCOUNTS_TABLE}` SET rate_limit_per_hour=%s, updated_at=%s WHERE id=%s",
                    (rate_limit_per_hour, now, account_id)
                )
                if cursor.rowcount == 0:
                    return None
                cursor.execute(f"SELECT * FROM `{ACCOUNTS_TABLE}` WHERE id=%s", (account_id,))
                row = cursor.fetchone()
                return _row_to_dict(row) if row else None
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            cur = conn.execute(
                f"UPDATE {ACCOUNTS_TABLE} SET rate_limit_per_hour=?, updated_at=? WHERE id=?",
                (rate_limit_per_hour, now, account_id)
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
            row = conn.execute(f"SELECT * FROM {ACCOUNTS_TABLE} WHERE id=?", (account_id,)).fetchone()
            return _row_to_dict(row) if row else None


# 初始化数据库
_ensure_db()
