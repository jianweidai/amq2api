"""
管理员账号管理模块
负责管理员账号的创建、验证和管理
支持 SQLite（默认）和 MySQL（可选）
"""
import sqlite3
import uuid
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone

import bcrypt

from src.auth.account_manager import (
    USE_MYSQL,
    SQLITE_DB_PATH,
    TABLE_PREFIX,
    _mysql_get_connection,
    _sqlite_conn,
)

logger = logging.getLogger(__name__)

# 表名
ADMIN_USERS_TABLE = f"{TABLE_PREFIX}admin_users" if USE_MYSQL else "admin_users"

# bcrypt 成本因子（至少 12）
BCRYPT_COST_FACTOR = 12


@dataclass
class AdminUser:
    """管理员用户数据类"""
    id: str
    username: str
    password_hash: str
    created_at: str
    updated_at: str


def ensure_admin_table() -> None:
    """初始化 admin_users 表结构"""
    if USE_MYSQL:
        _mysql_ensure_admin_table()
    else:
        _sqlite_ensure_admin_table()
    logger.info(f"管理员表 {ADMIN_USERS_TABLE} 初始化完成")


def _sqlite_ensure_admin_table() -> None:
    """初始化 SQLite admin_users 表"""
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _mysql_ensure_admin_table() -> None:
    """初始化 MySQL admin_users 表"""
    conn = _mysql_get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{ADMIN_USERS_TABLE}` (
                    id VARCHAR(36) PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at VARCHAR(32) NOT NULL,
                    updated_at VARCHAR(32) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()
    finally:
        conn.close()


def admin_exists() -> bool:
    """检查是否已存在管理员账号
    
    Returns:
        True 如果存在管理员账号，False 如果不存在
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) as count FROM `{ADMIN_USERS_TABLE}`")
                result = cursor.fetchone()
                return result['count'] > 0 if result else False
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            result = conn.execute(
                f"SELECT COUNT(*) FROM {ADMIN_USERS_TABLE}"
            ).fetchone()
            return result[0] > 0 if result else False


def get_admin_user() -> Optional[AdminUser]:
    """获取管理员账号（系统只允许一个）
    
    Returns:
        AdminUser 对象，如果不存在则返回 None
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{ADMIN_USERS_TABLE}` LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return AdminUser(
                        id=row['id'],
                        username=row['username'],
                        password_hash=row['password_hash'],
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    )
                return None
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {ADMIN_USERS_TABLE} LIMIT 1"
            ).fetchone()
            if row:
                return AdminUser(
                    id=row['id'],
                    username=row['username'],
                    password_hash=row['password_hash'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
            return None


def get_admin_user_by_username(username: str) -> Optional[AdminUser]:
    """根据用户名获取管理员账号
    
    Args:
        username: 用户名
    
    Returns:
        AdminUser 对象，如果不存在则返回 None
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM `{ADMIN_USERS_TABLE}` WHERE username=%s",
                    (username,)
                )
                row = cursor.fetchone()
                if row:
                    return AdminUser(
                        id=row['id'],
                        username=row['username'],
                        password_hash=row['password_hash'],
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    )
                return None
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {ADMIN_USERS_TABLE} WHERE username=?",
                (username,)
            ).fetchone()
            if row:
                return AdminUser(
                    id=row['id'],
                    username=row['username'],
                    password_hash=row['password_hash'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
            return None


def _hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码
    
    Args:
        password: 明文密码
    
    Returns:
        bcrypt 哈希值
    """
    salt = bcrypt.gensalt(rounds=BCRYPT_COST_FACTOR)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_admin_user(username: str, password: str) -> AdminUser:
    """创建管理员账号
    
    系统只允许一个管理员账号，如果已存在则抛出异常。
    
    Args:
        username: 用户名（3-50 字符）
        password: 密码（至少 8 字符）
    
    Returns:
        创建的 AdminUser 对象
    
    Raises:
        ValueError: 如果已存在管理员账号或输入无效
    """
    # 验证输入
    if not username or len(username) < 3 or len(username) > 50:
        raise ValueError("用户名必须为 3-50 个字符")
    
    if not password or len(password) < 8:
        raise ValueError("密码必须至少 8 个字符")
    
    # 检查是否已存在管理员
    if admin_exists():
        raise ValueError("管理员账号已存在")
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    admin_id = str(uuid.uuid4())
    password_hash = _hash_password(password)
    
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO `{ADMIN_USERS_TABLE}` 
                    (id, username, password_hash, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (admin_id, username, password_hash, now, now)
                )
            conn.commit()
            logger.info(f"管理员账号 '{username}' 创建成功")
            return AdminUser(
                id=admin_id,
                username=username,
                password_hash=password_hash,
                created_at=now,
                updated_at=now
            )
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                f"""
                INSERT INTO {ADMIN_USERS_TABLE} 
                (id, username, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (admin_id, username, password_hash, now, now)
            )
            conn.commit()
            logger.info(f"管理员账号 '{username}' 创建成功")
            return AdminUser(
                id=admin_id,
                username=username,
                password_hash=password_hash,
                created_at=now,
                updated_at=now
            )


def verify_admin_password(username: str, password: str) -> bool:
    """验证管理员密码
    
    Args:
        username: 用户名
        password: 明文密码
    
    Returns:
        True 如果密码正确，False 如果密码错误或用户不存在
    """
    admin = get_admin_user_by_username(username)
    if not admin:
        # 为了防止时序攻击，即使用户不存在也执行一次哈希比较
        bcrypt.checkpw(b"dummy_password", bcrypt.gensalt())
        return False
    
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            admin.password_hash.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"密码验证失败: {e}")
        return False


def delete_admin_user() -> bool:
    """删除管理员账号（仅用于测试）
    
    Returns:
        True 如果删除成功，False 如果不存在管理员
    """
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{ADMIN_USERS_TABLE}`")
                deleted = cursor.rowcount > 0
            conn.commit()
            if deleted:
                logger.info("管理员账号已删除")
            return deleted
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            cursor = conn.execute(f"DELETE FROM {ADMIN_USERS_TABLE}")
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info("管理员账号已删除")
            return deleted


# 初始化管理员表
ensure_admin_table()
