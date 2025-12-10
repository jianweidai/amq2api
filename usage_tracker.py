"""
Token 使用量追踪模块
记录和查询 API 请求的 token 消耗
"""
import sqlite3
import json
import uuid
import time
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 数据库配置（复用 account_manager 的配置）
MYSQL_HOST = os.getenv("MYSQL_HOST", "").strip()
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "amq2api").strip()

USE_MYSQL = bool(MYSQL_HOST and MYSQL_USER and MYSQL_DATABASE)

TABLE_PREFIX = "amq2api_" if USE_MYSQL else ""
USAGE_TABLE = f"{TABLE_PREFIX}usage"

# SQLite 数据库路径
if os.path.exists("/app/data"):
    SQLITE_DB_PATH = Path("/app/data/accounts.db")
else:
    SQLITE_DB_PATH = Path(__file__).parent / "accounts.db"


def _sqlite_conn() -> sqlite3.Connection:
    """创建 SQLite 数据库连接"""
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


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


def _ensure_usage_table():
    """初始化 usage 表"""
    if USE_MYSQL:
        conn = _mysql_get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS `{USAGE_TABLE}` (
                        id VARCHAR(36) PRIMARY KEY,
                        account_id VARCHAR(36),
                        model VARCHAR(64),
                        input_tokens INT DEFAULT 0,
                        output_tokens INT DEFAULT 0,
                        total_tokens INT DEFAULT 0,
                        channel VARCHAR(32) DEFAULT 'amazonq',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_created_at (created_at),
                        INDEX idx_account_id (account_id),
                        INDEX idx_model (model)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
            conn.commit()
        finally:
            conn.close()
    else:
        with _sqlite_conn() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {USAGE_TABLE} (
                    id TEXT PRIMARY KEY,
                    account_id TEXT,
                    model TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    channel TEXT DEFAULT 'amazonq',
                    created_at TEXT
                )
            """)
            # 创建索引
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_usage_created_at ON {USAGE_TABLE}(created_at)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_usage_account_id ON {USAGE_TABLE}(account_id)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_usage_model ON {USAGE_TABLE}(model)")
            conn.commit()


def record_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    account_id: Optional[str] = None,
    channel: str = "amazonq"
) -> str:
    """
    记录一次 API 请求的 token 使用量
    
    Args:
        model: 模型名称
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
        account_id: 账号 ID（可选）
        channel: 渠道 (amazonq/gemini)
    
    Returns:
        记录 ID
    """
    record_id = str(uuid.uuid4())
    total_tokens = input_tokens + output_tokens
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        if USE_MYSQL:
            conn = _mysql_get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"""
                        INSERT INTO `{USAGE_TABLE}` 
                        (id, account_id, model, input_tokens, output_tokens, total_tokens, channel, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (record_id, account_id, model, input_tokens, output_tokens, total_tokens, channel, now))
            finally:
                conn.close()
        else:
            with _sqlite_conn() as conn:
                conn.execute(f"""
                    INSERT INTO {USAGE_TABLE}
                    (id, account_id, model, input_tokens, output_tokens, total_tokens, channel, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (record_id, account_id, model, input_tokens, output_tokens, total_tokens, channel, now))
                conn.commit()
        
        logger.debug(f"记录 token 使用: model={model}, input={input_tokens}, output={output_tokens}")
    except Exception as e:
        logger.error(f"记录 token 使用失败: {e}")
    
    return record_id


def get_usage_summary(
    period: str = "day",
    account_id: Optional[str] = None,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取 token 使用量汇总
    
    Args:
        period: 统计周期 (hour/day/week/month/all)
        account_id: 按账号筛选（可选）
        model: 按模型筛选（可选）
    
    Returns:
        使用量汇总信息
    """
    # 计算时间范围
    now = datetime.now(timezone.utc)
    if period == "hour":
        start_time = now - timedelta(hours=1)
    elif period == "day":
        start_time = now - timedelta(days=1)
    elif period == "week":
        start_time = now - timedelta(weeks=1)
    elif period == "month":
        start_time = now - timedelta(days=30)
    else:  # all
        start_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
    
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建查询条件
    conditions = ["created_at >= ?"]
    params: List[Any] = [start_str]
    
    if account_id:
        conditions.append("account_id = ?")
        params.append(account_id)
    
    if model:
        conditions.append("model = ?")
        params.append(model)
    
    where_clause = " AND ".join(conditions)
    
    try:
        if USE_MYSQL:
            # MySQL 使用 %s 占位符
            where_clause_mysql = where_clause.replace("?", "%s")
            conn = _mysql_get_connection()
            try:
                with conn.cursor() as cursor:
                    # 总计
                    cursor.execute(f"""
                        SELECT 
                            COUNT(*) as request_count,
                            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                            COALESCE(SUM(total_tokens), 0) as total_tokens
                        FROM `{USAGE_TABLE}`
                        WHERE {where_clause_mysql}
                    """, params)
                    summary = cursor.fetchone()
                    
                    # 按模型分组
                    cursor.execute(f"""
                        SELECT 
                            model,
                            COUNT(*) as request_count,
                            COALESCE(SUM(input_tokens), 0) as input_tokens,
                            COALESCE(SUM(output_tokens), 0) as output_tokens,
                            COALESCE(SUM(total_tokens), 0) as total_tokens
                        FROM `{USAGE_TABLE}`
                        WHERE {where_clause_mysql}
                        GROUP BY model
                        ORDER BY total_tokens DESC
                    """, params)
                    by_model = cursor.fetchall()
                    
                    return {
                        "period": period,
                        "start_time": start_str,
                        "request_count": summary["request_count"],
                        "input_tokens": summary["total_input_tokens"],
                        "output_tokens": summary["total_output_tokens"],
                        "total_tokens": summary["total_tokens"],
                        "by_model": list(by_model)
                    }
            finally:
                conn.close()
        else:
            with _sqlite_conn() as conn:
                # 总计
                cursor = conn.execute(f"""
                    SELECT 
                        COUNT(*) as request_count,
                        COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                        COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens
                    FROM {USAGE_TABLE}
                    WHERE {where_clause}
                """, params)
                row = cursor.fetchone()
                summary = dict(row) if row else {}
                
                # 按模型分组
                cursor = conn.execute(f"""
                    SELECT 
                        model,
                        COUNT(*) as request_count,
                        COALESCE(SUM(input_tokens), 0) as input_tokens,
                        COALESCE(SUM(output_tokens), 0) as output_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens
                    FROM {USAGE_TABLE}
                    WHERE {where_clause}
                    GROUP BY model
                    ORDER BY total_tokens DESC
                """, params)
                by_model = [dict(r) for r in cursor.fetchall()]
                
                return {
                    "period": period,
                    "start_time": start_str,
                    "request_count": summary.get("request_count", 0),
                    "input_tokens": summary.get("total_input_tokens", 0),
                    "output_tokens": summary.get("total_output_tokens", 0),
                    "total_tokens": summary.get("total_tokens", 0),
                    "by_model": by_model
                }
    except Exception as e:
        logger.error(f"获取使用量汇总失败: {e}")
        return {
            "period": period,
            "start_time": start_str,
            "request_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "by_model": [],
            "error": str(e)
        }


def get_recent_usage(limit: int = 100) -> List[Dict[str, Any]]:
    """
    获取最近的使用记录
    
    Args:
        limit: 返回记录数量
    
    Returns:
        使用记录列表
    """
    try:
        if USE_MYSQL:
            conn = _mysql_get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT * FROM `{USAGE_TABLE}`
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (limit,))
                    return list(cursor.fetchall())
            finally:
                conn.close()
        else:
            with _sqlite_conn() as conn:
                cursor = conn.execute(f"""
                    SELECT * FROM {USAGE_TABLE}
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
                return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"获取最近使用记录失败: {e}")
        return []


# 初始化表
_ensure_usage_table()
