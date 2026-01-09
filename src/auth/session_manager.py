"""
会话管理模块
负责管理员会话的创建、验证和管理
支持 SQLite（默认）和 MySQL（可选）
"""
import sqlite3
import secrets
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone, timedelta

from src.auth.account_manager import (
    USE_MYSQL,
    SQLITE_DB_PATH,
    TABLE_PREFIX,
    _mysql_get_connection,
    _sqlite_conn,
)

logger = logging.getLogger(__name__)

# 表名
ADMIN_SESSIONS_TABLE = f"{TABLE_PREFIX}admin_sessions" if USE_MYSQL else "admin_sessions"
ADMIN_USERS_TABLE = f"{TABLE_PREFIX}admin_users" if USE_MYSQL else "admin_users"

# 会话配置
SESSION_TOKEN_BYTES = 32  # 256 bits of entropy
SESSION_EXPIRY_HOURS = 24  # 24 小时过期


@dataclass
class Session:
    """会话数据类"""
    token: str
    admin_id: str
    user_agent: str
    created_at: str
    expires_at: str
    last_activity: str


def ensure_session_table() -> None:
    """初始化 admin_sessions 表结构"""
    if USE_MYSQL:
        _mysql_ensure_session_table()
    else:
        _sqlite_ensure_session_table()
    logger.info(f"会话表 {ADMIN_SESSIONS_TABLE} 初始化完成")


def _sqlite_ensure_session_table() -> None:
    """初始化 SQLite admin_sessions 表"""
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {ADMIN_SESSIONS_TABLE} (
                token TEXT PRIMARY KEY,
                admin_id TEXT NOT NULL,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                FOREIGN KEY (admin_id) REFERENCES {ADMIN_USERS_TABLE}(id) ON DELETE CASCADE
            )
            """
        )
        # 创建索引以加速过期会话清理
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
            ON {ADMIN_SESSIONS_TABLE}(expires_at)
            """
        )
        conn.commit()


def _mysql_ensure_session_table() -> None:
    """初始化 MySQL admin_sessions 表"""
    conn = _mysql_get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{ADMIN_SESSIONS_TABLE}` (
                    token VARCHAR(64) PRIMARY KEY,
                    admin_id VARCHAR(36) NOT NULL,
                    user_agent TEXT,
                    created_at VARCHAR(32) NOT NULL,
                    expires_at VARCHAR(32) NOT NULL,
                    last_activity VARCHAR(32) NOT NULL,
                    INDEX idx_expires_at (expires_at),
                    FOREIGN KEY (admin_id) REFERENCES `{ADMIN_USERS_TABLE}`(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()
    finally:
        conn.close()


def _generate_secure_token() -> str:
    """生成加密安全的会话令牌
    
    使用 secrets 模块生成 256 bits (32 bytes) 的随机令牌，
    转换为十六进制字符串（64 字符）。
    
    Returns:
        64 字符的十六进制令牌字符串
    """
    return secrets.token_hex(SESSION_TOKEN_BYTES)


def create_session(admin_id: str, user_agent: str) -> str:
    """创建新会话
    
    生成加密安全的会话令牌，并存储到数据库。
    
    Args:
        admin_id: 管理员用户 ID
        user_agent: 客户端 User-Agent 字符串
    
    Returns:
        会话令牌字符串
    """
    token = _generate_secure_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=SESSION_EXPIRY_HOURS)
    
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at_str = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO `{ADMIN_SESSIONS_TABLE}` 
                    (token, admin_id, user_agent, created_at, expires_at, last_activity)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (token, admin_id, user_agent, now_str, expires_at_str, now_str)
                )
            conn.commit()
            logger.info(f"会话创建成功，管理员 ID: {admin_id}")
            return token
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                f"""
                INSERT INTO {ADMIN_SESSIONS_TABLE} 
                (token, admin_id, user_agent, created_at, expires_at, last_activity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, admin_id, user_agent, now_str, expires_at_str, now_str)
            )
            conn.commit()
            logger.info(f"会话创建成功，管理员 ID: {admin_id}")
            return token


def _row_to_session(row) -> Optional[Session]:
    """将数据库行转换为 Session 对象"""
    if not row:
        return None
    
    if isinstance(row, sqlite3.Row):
        return Session(
            token=row['token'],
            admin_id=row['admin_id'],
            user_agent=row['user_agent'] or '',
            created_at=row['created_at'],
            expires_at=row['expires_at'],
            last_activity=row['last_activity']
        )
    else:
        # MySQL DictCursor
        return Session(
            token=row['token'],
            admin_id=row['admin_id'],
            user_agent=row['user_agent'] or '',
            created_at=row['created_at'],
            expires_at=row['expires_at'],
            last_activity=row['last_activity']
        )


def get_session(token: str) -> Optional[Session]:
    """根据令牌获取会话
    
    Args:
        token: 会话令牌
    
    Returns:
        Session 对象，如果不存在则返回 None
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM `{ADMIN_SESSIONS_TABLE}` WHERE token=%s",
                    (token,)
                )
                row = cursor.fetchone()
                return _row_to_session(row)
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {ADMIN_SESSIONS_TABLE} WHERE token=?",
                (token,)
            ).fetchone()
            return _row_to_session(row)


def _update_last_activity(token: str) -> None:
    """更新会话的最后活动时间
    
    Args:
        token: 会话令牌
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE `{ADMIN_SESSIONS_TABLE}` SET last_activity=%s WHERE token=%s",
                    (now_str, token)
                )
            conn.commit()
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                f"UPDATE {ADMIN_SESSIONS_TABLE} SET last_activity=? WHERE token=?",
                (now_str, token)
            )
            conn.commit()


def validate_session(token: str, user_agent: str) -> Optional[Session]:
    """验证会话有效性
    
    检查会话是否存在、是否过期、以及 user-agent 是否匹配。
    如果会话有效，更新最后活动时间。
    
    Args:
        token: 会话令牌
        user_agent: 客户端 User-Agent 字符串
    
    Returns:
        有效的 Session 对象，如果无效则返回 None
    """
    session = get_session(token)
    
    if not session:
        logger.debug(f"会话验证失败：令牌不存在")
        return None
    
    # 检查是否过期
    try:
        expires_at = datetime.fromisoformat(session.expires_at.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        
        if now >= expires_at:
            logger.debug(f"会话验证失败：会话已过期")
            # 自动清理过期会话
            invalidate_session(token)
            return None
    except Exception as e:
        logger.error(f"解析会话过期时间失败: {e}")
        return None
    
    # 检查 user-agent 是否匹配（防止会话劫持）
    if session.user_agent and session.user_agent != user_agent:
        logger.warning(f"会话验证失败：User-Agent 不匹配")
        return None
    
    # 更新最后活动时间
    _update_last_activity(token)
    
    logger.debug(f"会话验证成功，管理员 ID: {session.admin_id}")
    return session


def invalidate_session(token: str) -> bool:
    """使会话失效（登出）
    
    Args:
        token: 会话令牌
    
    Returns:
        True 如果成功删除会话，False 如果会话不存在
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM `{ADMIN_SESSIONS_TABLE}` WHERE token=%s",
                    (token,)
                )
                deleted = cursor.rowcount > 0
            conn.commit()
            if deleted:
                logger.info(f"会话已失效")
            return deleted
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            cursor = conn.execute(
                f"DELETE FROM {ADMIN_SESSIONS_TABLE} WHERE token=?",
                (token,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"会话已失效")
            return deleted


def invalidate_all_sessions(admin_id: str) -> int:
    """使指定管理员的所有会话失效
    
    Args:
        admin_id: 管理员用户 ID
    
    Returns:
        删除的会话数量
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM `{ADMIN_SESSIONS_TABLE}` WHERE admin_id=%s",
                    (admin_id,)
                )
                deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"已删除管理员 {admin_id} 的 {deleted} 个会话")
            return deleted
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            cursor = conn.execute(
                f"DELETE FROM {ADMIN_SESSIONS_TABLE} WHERE admin_id=?",
                (admin_id,)
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"已删除管理员 {admin_id} 的 {deleted} 个会话")
            return deleted


def cleanup_expired_sessions() -> int:
    """清理所有过期会话
    
    删除所有 expires_at 早于当前时间的会话。
    
    Returns:
        删除的会话数量
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM `{ADMIN_SESSIONS_TABLE}` WHERE expires_at < %s",
                    (now_str,)
                )
                deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"已清理 {deleted} 个过期会话")
            return deleted
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            cursor = conn.execute(
                f"DELETE FROM {ADMIN_SESSIONS_TABLE} WHERE expires_at < ?",
                (now_str,)
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"已清理 {deleted} 个过期会话")
            return deleted


def get_active_session_count(admin_id: str) -> int:
    """获取管理员的活跃会话数量
    
    Args:
        admin_id: 管理员用户 ID
    
    Returns:
        活跃会话数量
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) as count FROM `{ADMIN_SESSIONS_TABLE}` WHERE admin_id=%s AND expires_at > %s",
                    (admin_id, now_str)
                )
                result = cursor.fetchone()
                return result['count'] if result else 0
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            result = conn.execute(
                f"SELECT COUNT(*) FROM {ADMIN_SESSIONS_TABLE} WHERE admin_id=? AND expires_at > ?",
                (admin_id, now_str)
            ).fetchone()
            return result[0] if result else 0


def delete_all_sessions() -> int:
    """删除所有会话（仅用于测试）
    
    Returns:
        删除的会话数量
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{ADMIN_SESSIONS_TABLE}`")
                deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"已删除所有 {deleted} 个会话")
            return deleted
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            cursor = conn.execute(f"DELETE FROM {ADMIN_SESSIONS_TABLE}")
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"已删除所有 {deleted} 个会话")
            return deleted


# 初始化会话表
ensure_session_table()
