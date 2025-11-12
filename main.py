"""
主服务模块
FastAPI 服务器,提供 Claude API 兼容的接口,支持多账号负载均衡
"""
import logging
import httpx
import asyncio
import time
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

from config import read_global_config, get_config_sync, load_account_pool, get_account_pool, save_all_account_caches
from auth import get_auth_headers
from models import ClaudeRequest
from converter import convert_claude_to_codewhisperer_request, codewhisperer_request_to_dict
from stream_handler_new import handle_amazonq_stream
from message_processor import process_claude_history_for_amazonq, log_history_summary
from account_config import AccountConfig
from exceptions import NoAvailableAccountError, TokenRefreshError
import metrics

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 健康检查任务
_health_check_task: Optional[asyncio.Task] = None


async def health_check_loop():
    """后台健康检查任务"""
    config = await read_global_config()
    interval = config.health_check_interval

    while True:
        try:
            await asyncio.sleep(interval)
            pool = await get_account_pool()

            logger.info("Running health check...")
            for account in pool.get_all_accounts():
                # 更新指标
                metrics.set_account_availability(account.id, account.is_available())
                metrics.update_account_stats(
                    account.id,
                    account.request_count,
                    account.error_count,
                    account.success_count
                )

            logger.info(f"Health check completed. Available accounts: {len(pool.get_available_accounts())}/{len(pool.get_all_accounts())}")

        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _health_check_task

    # 启动时初始化配置
    logger.info("Initializing configuration...")
    try:
        await read_global_config()
        logger.info("Configuration initialized successfully")
    except Exception as e:
        logger.error(f"Configuration initialization failed: {e}")
        raise

    # 初始化账号池
    logger.info("Initializing account pool...")
    try:
        pool = await load_account_pool()
        logger.info(f"Account pool initialized with {len(pool.get_all_accounts())} accounts")

        # 初始化所有账号的指标
        for account in pool.get_all_accounts():
            metrics.set_account_availability(account.id, account.is_available())

    except Exception as e:
        logger.error(f"Account pool initialization failed: {e}")
        raise

    # 启动健康检查任务
    logger.info("Starting health check task...")
    _health_check_task = asyncio.create_task(health_check_loop())

    yield

    # 关闭时清理资源
    logger.info("Shutting down service...")

    # 取消健康检查任务
    if _health_check_task:
        _health_check_task.cancel()
        try:
            await _health_check_task
        except asyncio.CancelledError:
            pass

    # 保存所有账号的 Token 缓存
    try:
        await save_all_account_caches()
        logger.info("All account token caches saved")
    except Exception as e:
        logger.error(f"Failed to save account caches: {e}")


# 创建 FastAPI 应用
app = FastAPI(
    title="Amazon Q to Claude API Proxy",
    description="将 Claude API 请求转换为 Amazon Q/CodeWhisperer 请求的代理服务",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "Amazon Q to Claude API Proxy",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """健康检查端点"""
    try:
        pool = await get_account_pool()
        available_accounts = pool.get_available_accounts()

        return {
            "status": "healthy",
            "accounts": {
                "total": len(pool.get_all_accounts()),
                "available": len(available_accounts),
                "unavailable": len(pool.get_all_accounts()) - len(available_accounts)
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/accounts/stats")
async def get_accounts_stats():
    """获取所有账号统计信息"""
    try:
        pool = await get_account_pool()
        return pool.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/accounts/{account_id}")
async def get_account_detail(account_id: str):
    """获取单个账号详情"""
    try:
        pool = await get_account_pool()
        account = pool.get_account(account_id)
        return account.to_dict()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")


@app.post("/accounts/{account_id}/enable")
async def enable_account(account_id: str):
    """启用账号"""
    try:
        pool = await get_account_pool()
        await pool.enable_account(account_id)
        return {"status": "success", "message": f"Account '{account_id}' enabled"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/accounts/{account_id}/disable")
async def disable_account(account_id: str):
    """禁用账号"""
    try:
        pool = await get_account_pool()
        await pool.disable_account(account_id)
        return {"status": "success", "message": f"Account '{account_id}' disabled"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/accounts/{account_id}/reset")
async def reset_account_errors(account_id: str):
    """重置账号错误计数和熔断状态"""
    try:
        pool = await get_account_pool()
        await pool.reset_circuit_breaker(account_id)
        return {"status": "success", "message": f"Account '{account_id}' reset"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/metrics")
async def get_metrics():
    """获取 Prometheus 指标"""
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type()
    )


@app.post("/v1/messages")
async def create_message(request: Request):
    """
    Claude API 兼容的消息创建端点
    接收 Claude 格式的请求，转换为 CodeWhisperer 格式并返回流式响应
    """
    try:
        # 解析请求体
        request_data = await request.json()

        # 标准 Claude API 格式 - 转换为 conversationState
        logger.info(f"收到标准 Claude API 请求: {request_data.get('model', 'unknown')}")

        # 转换为 ClaudeRequest 对象
        claude_req = parse_claude_request(request_data)

        # 选择账号(带重试和故障转移) - 需要先选择账号才能获取 profile_arn
        account = None
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                pool = await get_account_pool()
                account = await pool.select_account()

                # 使用账号池的锁确保 Token 刷新的原子性
                lock = pool.get_account_lock(account.id)
                async with lock:
                    # 获取认证头(会自动刷新 Token 如果过期)
                    base_auth_headers = await get_auth_headers(account)

                logger.info(f"Selected account '{account.id}' for request (attempt {attempt + 1}/{max_retries})")

                # 增加请求计数
                account.request_count += 1
                account.last_used_at = asyncio.get_event_loop().time()

                # 记录指标
                metrics.inc_active_requests(account.id)

                break  # 成功选择账号,跳出循环

            except TokenRefreshError as e:
                last_error = e
                logger.error(f"Failed to refresh token for account '{e.account_id}' (attempt {attempt + 1}/{max_retries}): {e}")

                # 标记账号错误
                if account:
                    await pool.mark_error(account.id, e)
                    metrics.record_error(account.id, "token_refresh")

                if attempt < max_retries - 1:
                    continue
                else:
                    raise HTTPException(status_code=503, detail="No available accounts after retries")

            except NoAvailableAccountError as e:
                logger.error(f"No available accounts: {e}")
                raise HTTPException(status_code=503, detail=str(e))

            except Exception as e:
                logger.error(f"Unexpected error selecting account: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to select account")

        # 确保选择了账号
        if account is None:
            raise HTTPException(status_code=503, detail="No available accounts")

        # 使用选中账号的 profile_arn 转换请求
        codewhisperer_req = convert_claude_to_codewhisperer_request(
            claude_req,
            conversation_id=None,  # 自动生成
            profile_arn=account.profile_arn
        )

        # 转换为字典
        codewhisperer_dict = codewhisperer_request_to_dict(codewhisperer_req)
        model = claude_req.model

        # 处理历史记录：合并连续的 userInputMessage
        conversation_state = codewhisperer_dict.get("conversationState", {})
        history = conversation_state.get("history", [])

        if history:
            # 记录原始历史记录
            logger.info("=" * 80)
            logger.info("原始历史记录:")
            log_history_summary(history, prefix="[原始] ")

            # 合并连续的用户消息
            processed_history = process_claude_history_for_amazonq(history)

            # 记录处理后的历史记录
            logger.info("=" * 80)
            logger.info("处理后的历史记录:")
            log_history_summary(processed_history, prefix="[处理后] ")

            # 更新请求体
            conversation_state["history"] = processed_history
            codewhisperer_dict["conversationState"] = conversation_state

        # 处理 currentMessage 中的重复 toolResults（标准 Claude API 格式）
        conversation_state = codewhisperer_dict.get("conversationState", {})
        current_message = conversation_state.get("currentMessage", {})
        user_input_message = current_message.get("userInputMessage", {})
        user_input_message_context = user_input_message.get("userInputMessageContext", {})

        # 合并 currentMessage 中重复的 toolResults
        tool_results = user_input_message_context.get("toolResults", [])
        if tool_results:
            merged_tool_results = []
            seen_tool_use_ids = set()

            for result in tool_results:
                tool_use_id = result.get("toolUseId")
                if tool_use_id in seen_tool_use_ids:
                    # 找到已存在的条目，合并 content
                    for existing in merged_tool_results:
                        if existing.get("toolUseId") == tool_use_id:
                            existing["content"].extend(result.get("content", []))
                            logger.info(f"[CURRENT MESSAGE - CLAUDE API] 合并重复的 toolUseId {tool_use_id} 的 content")
                            break
                else:
                    # 新条目
                    seen_tool_use_ids.add(tool_use_id)
                    merged_tool_results.append(result)

            user_input_message_context["toolResults"] = merged_tool_results
            user_input_message["userInputMessageContext"] = user_input_message_context
            current_message["userInputMessage"] = user_input_message
            conversation_state["currentMessage"] = current_message
            codewhisperer_dict["conversationState"] = conversation_state

        final_request = codewhisperer_dict

        # 调试：打印请求体
        import json
        logger.info(f"转换后的请求体: {json.dumps(final_request, indent=2, ensure_ascii=False)}")

        # 账号已在前面选择(base_auth_headers 已设置)

        # 构建 Amazon Q 特定的请求头（完整版本）
        import uuid
        auth_headers = {
            **base_auth_headers,
            "Content-Type": "application/x-amz-json-1.0",
            "X-Amz-Target": "AmazonCodeWhispererStreamingService.GenerateAssistantResponse",
            "User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 md/appVersion-1.19.3 app/AmazonQ-For-CLI",
            "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 m/F app/AmazonQ-For-CLI",
            "X-Amzn-Codewhisperer-Optout": "true",
            "Amz-Sdk-Request": "attempt=1; max=3",
            "Amz-Sdk-Invocation-Id": str(uuid.uuid4()),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br"
        }

        # 发送请求到 Amazon Q
        logger.info("正在发送请求到 Amazon Q...")

        # API URL（根路径，不需要额外路径）
        config = await read_global_config()
        api_url = config.api_endpoint.rstrip('/')

        # 记录请求开始时间
        request_start_time = time.time()

        # 创建字节流响应
        async def byte_stream():
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    try:
                        async with client.stream(
                            "POST",
                            api_url,
                            json=final_request,
                            headers=auth_headers
                        ) as response:
                            # 检查响应状态
                            if response.status_code != 200:
                                error_text = await response.aread()

                                # 特殊处理 429 限流错误
                                if response.status_code == 429:
                                    logger.warning(f"Account '{account.id}' hit rate limit (429), triggering circuit breaker")
                                    # 429 触发熔断器,自动切换到其他账号
                                    await pool.mark_error(account.id, Exception("Rate limit exceeded"))
                                    metrics.record_error(account.id, "rate_limit")
                                    metrics.record_request(account.id, "error")

                                    raise HTTPException(
                                        status_code=503,
                                        detail=f"Rate limit exceeded for account '{account.id}', please retry"
                                    )

                                logger.error(f"Upstream API error: {response.status_code} {error_text}")

                                # 记录错误
                                await pool.mark_error(account.id)
                                metrics.record_error(account.id, "http_error")
                                metrics.record_request(account.id, "error")

                                raise HTTPException(
                                    status_code=response.status_code,
                                    detail=f"Upstream API error: {error_text.decode()}"
                                )

                            # 处理 Event Stream(字节流)
                            async for chunk in response.aiter_bytes():
                                if chunk:
                                    yield chunk

                            # 请求成功
                            request_duration = time.time() - request_start_time
                            await pool.mark_success(account.id)
                            metrics.record_request(account.id, "success")
                            metrics.record_response_time(account.id, request_duration)

                    except httpx.RequestError as e:
                        logger.error(f"Request error: {e}")

                        # 记录错误
                        await pool.mark_error(account.id)
                        metrics.record_error(account.id, "network_error")
                        metrics.record_request(account.id, "error")

                        raise HTTPException(status_code=502, detail=f"Upstream service error: {str(e)}")

            finally:
                # 减少活跃请求数
                metrics.dec_active_requests(account.id)

        # 返回流式响应
        async def claude_stream():
            async for event in handle_amazonq_stream(byte_stream(), model=model, request_data=request_data):
                yield event

        return StreamingResponse(
            claude_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理请求时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


def parse_claude_request(data: dict) -> ClaudeRequest:
    """
    解析 Claude API 请求数据

    Args:
        data: 请求数据字典

    Returns:
        ClaudeRequest: Claude 请求对象
    """
    from models import ClaudeMessage, ClaudeTool

    # 解析消息
    messages = []
    for msg in data.get("messages", []):
        messages.append(ClaudeMessage(
            role=msg["role"],
            content=msg["content"]
        ))

    # 解析工具
    tools = None
    if "tools" in data:
        tools = []
        for tool in data["tools"]:
            tools.append(ClaudeTool(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["input_schema"]
            ))

    return ClaudeRequest(
        model=data.get("model", "claude-sonnet-4.5"),
        messages=messages,
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature"),
        tools=tools,
        stream=data.get("stream", True),
        system=data.get("system")
    )


if __name__ == "__main__":
    import uvicorn

    # 读取配置
    try:
        import asyncio
        config = asyncio.run(read_global_config())
        port = config.port
    except Exception as e:
        logger.error(f"无法读取配置: {e}")
        port = 8080

    logger.info(f"正在启动服务，监听端口 {port}...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
