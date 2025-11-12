"""
Prometheus 监控指标模块

定义和管理多账号系统的监控指标
"""

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from typing import Optional

# 请求计数器(按账号和状态)
request_counter = Counter(
    'amazonq_requests_total',
    'Total number of requests per account',
    ['account_id', 'status']
)

# 错误计数器(按账号和错误类型)
error_counter = Counter(
    'amazonq_errors_total',
    'Total number of errors per account',
    ['account_id', 'error_type']
)

# 账号可用性(0=不可用, 1=可用)
account_availability = Gauge(
    'amazonq_account_available',
    'Account availability status (0=unavailable, 1=available)',
    ['account_id']
)

# 响应时间直方图(按账号)
response_time_histogram = Histogram(
    'amazonq_response_seconds',
    'Response time in seconds per account',
    ['account_id'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, float('inf'))
)

# Token 刷新计数器(按账号)
token_refresh_counter = Counter(
    'amazonq_token_refresh_total',
    'Total number of token refreshes per account',
    ['account_id', 'status']
)

# 当前活跃请求数(按账号)
active_requests_gauge = Gauge(
    'amazonq_active_requests',
    'Current number of active requests per account',
    ['account_id']
)

# 熔断器打开次数(按账号)
circuit_breaker_counter = Counter(
    'amazonq_circuit_breaker_opened_total',
    'Total number of times circuit breaker was opened per account',
    ['account_id']
)

# 账号请求计数
account_request_count = Gauge(
    'amazonq_account_request_count',
    'Total request count per account',
    ['account_id']
)

# 账号错误计数
account_error_count = Gauge(
    'amazonq_account_error_count',
    'Total error count per account',
    ['account_id']
)

# 账号成功计数
account_success_count = Gauge(
    'amazonq_account_success_count',
    'Total success count per account',
    ['account_id']
)


def record_request(account_id: str, status: str = "success"):
    """
    记录请求

    Args:
        account_id: 账号 ID
        status: 请求状态(success, error, timeout 等)
    """
    request_counter.labels(account_id=account_id, status=status).inc()


def record_error(account_id: str, error_type: str = "unknown"):
    """
    记录错误

    Args:
        account_id: 账号 ID
        error_type: 错误类型(token_refresh, network, http_error 等)
    """
    error_counter.labels(account_id=account_id, error_type=error_type).inc()


def set_account_availability(account_id: str, available: bool):
    """
    设置账号可用性

    Args:
        account_id: 账号 ID
        available: 是否可用
    """
    account_availability.labels(account_id=account_id).set(1 if available else 0)


def record_response_time(account_id: str, duration: float):
    """
    记录响应时间

    Args:
        account_id: 账号 ID
        duration: 响应时间(秒)
    """
    response_time_histogram.labels(account_id=account_id).observe(duration)


def record_token_refresh(account_id: str, status: str = "success"):
    """
    记录 Token 刷新

    Args:
        account_id: 账号 ID
        status: 刷新状态(success, error)
    """
    token_refresh_counter.labels(account_id=account_id, status=status).inc()


def inc_active_requests(account_id: str):
    """
    增加活跃请求数

    Args:
        account_id: 账号 ID
    """
    active_requests_gauge.labels(account_id=account_id).inc()


def dec_active_requests(account_id: str):
    """
    减少活跃请求数

    Args:
        account_id: 账号 ID
    """
    active_requests_gauge.labels(account_id=account_id).dec()


def record_circuit_breaker_opened(account_id: str):
    """
    记录熔断器打开

    Args:
        account_id: 账号 ID
    """
    circuit_breaker_counter.labels(account_id=account_id).inc()


def update_account_stats(account_id: str, request_count: int, error_count: int, success_count: int):
    """
    更新账号统计信息

    Args:
        account_id: 账号 ID
        request_count: 请求总数
        error_count: 错误总数
        success_count: 成功总数
    """
    account_request_count.labels(account_id=account_id).set(request_count)
    account_error_count.labels(account_id=account_id).set(error_count)
    account_success_count.labels(account_id=account_id).set(success_count)


def get_metrics() -> bytes:
    """
    获取 Prometheus 格式的指标数据

    Returns:
        bytes: Prometheus 格式的指标数据
    """
    return generate_latest()


def get_content_type() -> str:
    """
    获取 Prometheus 指标的 Content-Type

    Returns:
        str: Content-Type
    """
    return CONTENT_TYPE_LATEST
