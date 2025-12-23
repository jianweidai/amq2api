"""
流式响应工具模块
提供流验证和错误处理功能
"""
import json
import logging
from typing import AsyncIterator, Tuple, Optional, Any, Callable, Awaitable
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class StreamValidationResult:
    """流验证结果"""
    success: bool
    status_code: int
    error_message: Optional[str] = None
    stream_generator: Optional[Callable[[], AsyncIterator[bytes]]] = None
    # 保存需要在生成器中使用的资源引用
    client: Optional[httpx.AsyncClient] = None
    response: Optional[httpx.Response] = None


def format_sse_error_event(error_type: str, message: str, status_code: int = 500) -> str:
    """
    格式化 SSE 错误事件（Claude API 格式）

    Args:
        error_type: 错误类型 (api_error, upstream_error, auth_error, rate_limit_error 等)
        message: 错误消息
        status_code: HTTP 状态码

    Returns:
        SSE 格式的错误事件字符串
    """
    error_event = {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message
        }
    }
    return f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"


async def validate_upstream_stream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    json_body: Optional[dict] = None,
    timeout: float = 300.0
) -> StreamValidationResult:
    """
    验证上游流式响应

    在建立连接后立即检查 HTTP 状态码，如果状态码不是 200，
    则读取错误信息并返回失败结果，而不是返回 StreamingResponse。

    Args:
        client: httpx 客户端
        method: HTTP 方法
        url: 请求 URL
        headers: 请求头
        json_body: JSON 请求体
        timeout: 超时时间

    Returns:
        StreamValidationResult: 包含验证结果和流生成器
    """
    try:
        # 构建请求
        request = client.build_request(
            method,
            url,
            json=json_body,
            headers=headers,
            timeout=timeout
        )

        # 发送请求并获取响应（保持连接打开）
        response = await client.send(request, stream=True)

        # 立即检查状态码
        if response.status_code != 200:
            error_text = await response.aread()
            await response.aclose()
            error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)

            return StreamValidationResult(
                success=False,
                status_code=response.status_code,
                error_message=error_str,
                client=client,
                response=None
            )

        # 状态码正常，创建流生成器
        async def stream_with_cleanup() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                await response.aclose()

        return StreamValidationResult(
            success=True,
            status_code=200,
            stream_generator=stream_with_cleanup,
            client=client,
            response=response
        )

    except httpx.RequestError as e:
        logger.error(f"请求错误: {e}")
        return StreamValidationResult(
            success=False,
            status_code=502,
            error_message=f"上游服务错误: {str(e)}",
            client=client
        )


class ValidatedStreamContext:
    """
    验证流上下文管理器

    用于管理 httpx 客户端的生命周期，确保资源正确释放
    """

    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
        self.response: Optional[httpx.Response] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 注意：如果流正在使用，不要在这里关闭
        # 资源释放由 stream_with_cleanup 负责
        pass

    async def validate_and_stream(
        self,
        method: str,
        url: str,
        headers: dict,
        json_body: Optional[dict] = None
    ) -> StreamValidationResult:
        """
        验证并返回流
        """
        return await validate_upstream_stream(
            client=self.client,
            method=method,
            url=url,
            headers=headers,
            json_body=json_body,
            timeout=self.timeout
        )

    async def close(self):
        """手动关闭客户端"""
        if self.client:
            await self.client.aclose()
            self.client = None