"""
主服务模块
FastAPI 服务器，提供 Claude API 兼容的接口
"""
import logging

# 配置日志（必须在其他模块导入之前）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import httpx
import time
import uuid
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

from src.config import read_global_config, get_config_sync
from src.auth.auth import get_auth_headers_with_retry, refresh_account_token, NoAccountAvailableError, TokenRefreshError
from src.auth.account_manager import (
    list_enabled_accounts, list_all_accounts, get_account,
    create_account, update_account, delete_account, get_random_account,
    get_random_channel_by_model, record_api_call, check_rate_limit,
    get_account_call_stats, update_account_rate_limit,
    is_account_in_cooldown
)
from src.auth.account_distributor import get_account_distributor, NoAccountAvailableError as DistributorNoAccountError
from src.models import ClaudeRequest
from src.amazonq.converter import convert_claude_to_codewhisperer_request, codewhisperer_request_to_dict
from src.amazonq.stream_handler import handle_amazonq_stream
from src.processing.message_processor import process_claude_history_for_amazonq, log_history_summary
from pydantic import BaseModel
from typing import Dict, Any, Optional
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Gemini 模块导入
from src.gemini.auth import GeminiTokenManager
from src.gemini.converter import convert_claude_to_gemini
from src.gemini.handler import handle_gemini_stream

# Custom API 模块导入
from src.custom_api.handler import handle_custom_api_request

# Cache Manager 导入
from src.processing.cache_manager import CacheManager, CacheResult

# Admin Login 模块导入
from src.auth.admin_manager import admin_exists, create_admin_user, verify_admin_password, get_admin_user
from src.auth.session_manager import create_session, validate_session, invalidate_session
from src.auth.rate_limiter import check_rate_limit as check_login_rate_limit, record_login_attempt, is_account_locked

# 全局 CacheManager 实例（在 lifespan 中初始化）
_cache_manager: CacheManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _cache_manager
    
    # 启动时初始化配置
    logger.info("正在初始化配置...")
    try:
        config = await read_global_config()
        logger.info("配置初始化成功")
        
        # 初始化 CacheManager（如果启用了缓存模拟）
        if config.enable_cache_simulation:
            _cache_manager = CacheManager(
                ttl_seconds=config.cache_ttl_seconds,
                max_entries=config.max_cache_entries
            )
            logger.info(f"Prompt Caching 模拟已启用 (TTL: {config.cache_ttl_seconds}s, Max Entries: {config.max_cache_entries})")
        else:
            logger.info("Prompt Caching 模拟已禁用")
    except Exception as e:
        logger.error(f"配置初始化失败: {e}")
        raise

    # 启动定时刷新任务
    refresh_task = None
    try:
        from src.auth.token_scheduler import scheduled_token_refresh
        import asyncio
        
        config = await read_global_config()
        if config.enable_auto_refresh:
            refresh_task = asyncio.create_task(scheduled_token_refresh())
            logger.info("Token 定时刷新后台任务已创建")
        else:
            logger.info("Token 定时刷新功能已禁用")
    except Exception as e:
        logger.error(f"启动定时刷新任务失败: {e}")

    yield

    # 关闭时清理资源
    logger.info("正在关闭服务...")
    
    # 取消定时刷新任务
    if refresh_task is not None:
        logger.info("正在停止定时刷新任务...")
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            logger.info("定时刷新任务已停止")



# 创建 FastAPI 应用
app = FastAPI(
    title="Amazon Q to Claude API Proxy",
    description="将 Claude API 请求转换为 Amazon Q/CodeWhisperer 请求的代理服务",
    version="1.0.0",
    lifespan=lifespan
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 管理员鉴权依赖
async def verify_admin_key(
    request: Request,
    x_session_token: Optional[str] = Header(None)
):
    """验证管理员认证
    
    使用 X-Session-Token 进行会话认证。
    """
    # 获取客户端信息
    user_agent = request.headers.get("user-agent", "")
    
    # 使用 X-Session-Token 认证
    if x_session_token:
        session = validate_session(x_session_token, user_agent)
        if session:
            return True
        # 会话无效
        raise HTTPException(
            status_code=401,
            detail="会话已过期或无效，请重新登录"
        )
    
    # 没有提供会话令牌
    # 检查是否存在管理员账号
    if admin_exists():
        logger.warning("⚠️  需要登录认证。请使用会话令牌访问管理功能。")
        raise HTTPException(
            status_code=401,
            detail="需要登录认证。请先登录获取会话令牌。"
        )
    else:
        logger.warning("⚠️  无管理员账号！请先创建管理员账号。")
        raise HTTPException(
            status_code=403,
            detail="管理功能已禁用：请先创建管理员账号。"
        )


# API Key 鉴权依赖
async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """验证 API Key（Anthropic API 格式）"""
    import os
    api_key = os.getenv("API_KEY")

    # 如果没有设置 API_KEY，则不需要验证
    if not api_key:
        return True

    # 如果设置了 API_KEY，则必须验证
    if not x_api_key or x_api_key != api_key:
        raise HTTPException(
            status_code=401,
            detail="未授权：需要有效的 API Key。请在请求头中添加 x-api-key"
        )
    return True


# Pydantic 模型
class AccountCreate(BaseModel):
    label: Optional[str] = None
    clientId: str
    clientSecret: str
    refreshToken: Optional[str] = None
    accessToken: Optional[str] = None
    other: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = True
    type: str = "amazonq"  # amazonq, gemini, 或 custom_api
    weight: Optional[int] = 50  # 权重，越大被选中概率越高（建议1-100）
    rate_limit_per_hour: Optional[int] = 20  # 每小时调用限制


class AccountUpdate(BaseModel):
    label: Optional[str] = None
    clientId: Optional[str] = None
    clientSecret: Optional[str] = None
    refreshToken: Optional[str] = None
    accessToken: Optional[str] = None
    other: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    weight: Optional[int] = None  # 权重，越大被选中概率越高（建议1-100）
    rate_limit_per_hour: Optional[int] = None  # 每小时调用限制


# ============== 管理员登录系统 Pydantic 模型 ==============

class AdminSetupRequest(BaseModel):
    """管理员账号设置请求"""
    username: str
    password: str
    confirmPassword: str


class AdminLoginRequest(BaseModel):
    """管理员登录请求"""
    username: str
    password: str


class AdminStatusResponse(BaseModel):
    """管理员系统状态响应"""
    needSetup: bool
    locked: bool = False
    lockRemaining: int = 0


class AdminLoginResponse(BaseModel):
    """管理员登录响应"""
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None


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
    """轻量级健康检查端点 - 仅检查服务状态和账号配置"""
    try:
        all_accounts = list_all_accounts()
        enabled_accounts = [acc for acc in all_accounts if acc.get('enabled')]

        if not enabled_accounts:
            return {
                "status": "unhealthy",
                "reason": "no_enabled_accounts",
                "enabled_accounts": 0,
                "total_accounts": len(all_accounts)
            }

        return {
            "status": "healthy",
            "enabled_accounts": len(enabled_accounts),
            "total_accounts": len(all_accounts)
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "reason": "system_error",
            "error": str(e)
        }


@app.post("/api/event_logging/batch")
async def event_logging_batch():
    """静默处理 Claude Code 的遥测请求"""
    return {"status": "ok"}


@app.post("/v1/messages")
async def create_message(request: Request, _: bool = Depends(verify_api_key)):
    """
    Claude API 兼容的消息创建端点（智能路由）
    根据模型和账号数量自动选择渠道（Amazon Q 或 Gemini）
    """
    try:
        # 解析请求体
        request_data = await request.json()
        model = request_data.get('model', 'claude-sonnet-4.5')

        # 智能路由：根据模型选择渠道
        specified_account_id = request.headers.get("X-Account-ID")
        test_mode = request.headers.get("X-Test-Mode") == "true"  # 测试模式标志

        if specified_account_id:
            # 指定了账号，检查账号类型并路由到对应渠道
            account = get_account(specified_account_id)
            if not account:
                raise HTTPException(status_code=404, detail=f"账号不存在: {specified_account_id}")
            # 测试模式下允许使用禁用的账号
            if not test_mode and not account.get('enabled'):
                raise HTTPException(status_code=403, detail=f"账号已禁用: {specified_account_id}")

            account_type = account.get('type', 'amazonq')
            if account_type == 'gemini':
                logger.info(f"指定账号为 Gemini 类型，转发到 Gemini 渠道")
                return await create_gemini_message(request)
            elif account_type == 'custom_api':
                logger.info(f"指定账号为 Custom API 类型，转发到 Custom API 渠道")
                return await create_custom_api_message(request)
        else:
            # 没有指定账号时，根据模型智能选择渠道
            channel = get_random_channel_by_model(model)

            if not channel:
                raise HTTPException(status_code=503, detail="没有可用的账号")

            logger.info(f"智能路由选择渠道: {channel}")

            # 如果选择了 Gemini 渠道，转发到 /v1/gemini/messages
            if channel == 'gemini':
                return await create_gemini_message(request)
            
            # 如果选择了 Custom API 渠道
            if channel == 'custom_api':
                return await create_custom_api_message(request)

        # 继续使用 Amazon Q 渠道的原有逻辑

        # 转换为 ClaudeRequest 对象
        claude_req = parse_claude_request(request_data)

        # 获取配置
        config = await read_global_config()

        # 转换为 CodeWhisperer 请求
        codewhisperer_req = convert_claude_to_codewhisperer_request(
            claude_req,
            conversation_id=None,  # KiroGate 风格：每个请求生成新的 conversationId，无需绑定
            profile_arn=config.profile_arn
        )

        # 转换为字典
        codewhisperer_dict = codewhisperer_request_to_dict(codewhisperer_req)
        model = claude_req.model

        # 处理历史记录：合并连续的 userInputMessage
        conversation_state = codewhisperer_dict.get("conversationState", {})
        history = conversation_state.get("history", [])

        if history:
            # 记录原始历史记录
            # logger.info("=" * 80)
            # logger.info("原始历史记录:")
            # log_history_summary(history, prefix="[原始] ")

            # 合并连续的用户消息
            processed_history = process_claude_history_for_amazonq(history)

            # 记录处理后的历史记录
            # logger.info("=" * 80)
            # logger.info("处理后的历史记录:")
            # log_history_summary(processed_history, prefix="[处理后] ")

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

        # 获取账号和认证头（KiroGate 风格：每个请求独立分配，无需会话绑定）
        # 检查是否指定了特定账号（用于测试）
        specified_account_id = request.headers.get("X-Account-ID")
        test_mode = request.headers.get("X-Test-Mode") == "true"  # 测试模式标志

        # 用于重试的变量
        account = None
        base_auth_headers = None

        try:
            if specified_account_id:
                # 使用指定的账号
                account = get_account(specified_account_id)
                if not account:
                    raise HTTPException(status_code=404, detail=f"账号不存在: {specified_account_id}")
                # 测试模式下允许使用禁用的账号
                if not test_mode and not account.get('enabled'):
                    raise HTTPException(status_code=403, detail=f"账号已禁用: {specified_account_id}")

                # 获取该账号的认证头
                from src.auth.auth import get_auth_headers_for_account
                base_auth_headers = await get_auth_headers_for_account(account)
                logger.info(f"使用指定账号 - 账号: {account.get('id')} (label: {account.get('label', 'N/A')})")
            else:
                # KiroGate 风格：使用智能账号分配器
                # 每个请求独立分配账号，基于成功率、冷却时间和负载均衡
                try:
                    distributor = get_account_distributor()
                    account = distributor.get_best_account(account_type="amazonq")
                    
                    from src.auth.auth import get_auth_headers_for_account
                    base_auth_headers = await get_auth_headers_for_account(account)
                    logger.info(f"智能分配账号 - 账号: {account.get('id')} (label: {account.get('label', 'N/A')})")
                except DistributorNoAccountError:
                    # 回退到旧的账号获取方式（兼容单账号模式）
                    account, base_auth_headers = await get_auth_headers_with_retry()
                    if account:
                        logger.info(f"使用多账号模式 - 账号: {account.get('id')} (label: {account.get('label', 'N/A')})")
                    else:
                        logger.info("使用单账号模式（.env 配置）")
        except NoAccountAvailableError as e:
            logger.error(f"无可用账号: {e}")
            raise HTTPException(status_code=503, detail="没有可用的账号，请在管理页面添加账号或配置 .env 文件")
        except TokenRefreshError as e:
            logger.error(f"Token 刷新失败: {e}")
            raise HTTPException(status_code=502, detail="Token 刷新失败")

        # 应用模型映射（如果账号有配置）
        if account:
            from src.processing.model_mapper import apply_model_mapping
            original_model = model
            model = apply_model_mapping(account, model)
            if model != original_model:
                # 更新 claude_req 中的模型
                claude_req.model = model
                # 重新转换请求，保持相同的 conversationId
                existing_conversation_id = codewhisperer_req.conversationState.conversationId
                codewhisperer_req = convert_claude_to_codewhisperer_request(
                    claude_req,
                    conversation_id=existing_conversation_id,
                    profile_arn=config.profile_arn
                )
                codewhisperer_dict = codewhisperer_request_to_dict(codewhisperer_req)
                # 重新处理历史记录和 toolResults
                conversation_state = codewhisperer_dict.get("conversationState", {})
                history = conversation_state.get("history", [])
                if history:
                    processed_history = process_claude_history_for_amazonq(history)
                    conversation_state["history"] = processed_history
                    codewhisperer_dict["conversationState"] = conversation_state
                
                conversation_state = codewhisperer_dict.get("conversationState", {})
                current_message = conversation_state.get("currentMessage", {})
                user_input_message = current_message.get("userInputMessage", {})
                user_input_message_context = user_input_message.get("userInputMessageContext", {})
                tool_results = user_input_message_context.get("toolResults", [])
                if tool_results:
                    merged_tool_results = []
                    seen_tool_use_ids = set()
                    for result in tool_results:
                        tool_use_id = result.get("toolUseId")
                        if tool_use_id in seen_tool_use_ids:
                            for existing in merged_tool_results:
                                if existing.get("toolUseId") == tool_use_id:
                                    existing["content"].extend(result.get("content", []))
                                    break
                        else:
                            seen_tool_use_ids.add(tool_use_id)
                            merged_tool_results.append(result)
                    user_input_message_context["toolResults"] = merged_tool_results
                    user_input_message["userInputMessageContext"] = user_input_message_context
                    current_message["userInputMessage"] = user_input_message
                    conversation_state["currentMessage"] = current_message
                    codewhisperer_dict["conversationState"] = conversation_state
                
                final_request = codewhisperer_dict

        # 在发送请求前验证输入长度（仅对 Amazon Q，因为它的限制较严格）
        # 可以通过环境变量 AMAZONQ_MAX_INPUT_TOKENS 调整限制
        # 或设置 DISABLE_INPUT_VALIDATION=true 完全禁用验证
        import os
        if os.getenv("DISABLE_INPUT_VALIDATION", "").lower() != "true":
            from src.processing.input_validator import validate_input_length, count_images_in_request
            is_valid, error_message, estimated_tokens = validate_input_length(request_data)
            
            if not is_valid:
                image_count = count_images_in_request(request_data)
                logger.warning(f"输入验证失败: {error_message} (图片数量: {image_count})")
                # 注意：这只是警告，不阻止请求继续
                # 如果需要严格验证，取消下面的注释
                # raise HTTPException(
                #     status_code=400,
                #     detail={
                #         "type": "error",
                #         "error": {
                #             "type": "invalid_request_error",
                #             "message": error_message
                #         },
                #         "estimated_tokens": estimated_tokens,
                #         "image_count": image_count
                #     }
                # )

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
        # API URL
        api_url = "https://q.us-east-1.amazonaws.com/"

        # 创建字节流响应（支持 401/403 重试）
        # 创建字节流响应（支持 401/403 重试，以及 5xx 重试）
        async def byte_stream():
            max_retries = 3
            current_retry = 0
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                while True:
                    try:
                        # 更新尝试次数 header
                        if "Amz-Sdk-Request" in auth_headers:
                            auth_headers["Amz-Sdk-Request"] = f"attempt={current_retry+1}; max={max_retries+1}"

                        async with client.stream(
                            "POST",
                            api_url,
                            json=final_request,
                            headers=auth_headers
                        ) as response:
                            # 1. 检查响应状态 - 处理 401/403 (Token 过期/封禁)
                            if response.status_code in (401, 403):
                                logger.warning(f"收到 {response.status_code} 错误 (尝试 {current_retry+1})")
                                error_text = await response.aread()
                                error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                                
                                # 检测账号是否被封
                                if "TEMPORARILY_SUSPENDED" in error_str and account:
                                    logger.error(f"账号 {account['id']} 已被封禁，自动禁用")
                                    from datetime import datetime
                                    suspend_info = {
                                        "suspended": True,
                                        "suspended_at": datetime.now().isoformat(),
                                        "suspend_reason": "TEMPORARILY_SUSPENDED"
                                    }
                                    current_other = account.get('other') or {}
                                    current_other.update(suspend_info)
                                    update_account(account['id'], enabled=False, other=current_other)

                                    if not specified_account_id:
                                        raise TokenRefreshError(f"账号已被封禁: {error_str}")
                                    else:
                                        raise HTTPException(status_code=403, detail=f"账号已被封禁: {error_str}")

                                try:
                                    logger.info("尝试刷新 Token...")
                                    # 刷新 token（支持多账号和单账号模式）
                                    if account:
                                        # 多账号模式：刷新当前账号
                                        refreshed_account = await refresh_account_token(account)
                                        new_access_token = refreshed_account.get("accessToken")
                                    else:
                                        # 单账号模式：刷新 .env 配置的 token
                                        from src.auth.auth import refresh_legacy_token
                                        await refresh_legacy_token()
                                        from src.config import read_global_config
                                        config = await read_global_config()
                                        new_access_token = config.access_token

                                    if not new_access_token:
                                        raise HTTPException(status_code=502, detail="Token 刷新后仍无法获取 accessToken")

                                    # 更新认证头
                                    auth_headers["Authorization"] = f"Bearer {new_access_token}"
                                    logger.info("Token 刷新成功，准备重试请求")
                                    
                                    # 避免死循环，如果已经是重试过多次的 401，可能无法修复
                                    if current_retry >= max_retries:
                                         logger.warning("Token 刷新成功但重试次数已耗尽 (401Loop?)")
                                    
                                    # 重新开始循环，使用新 Token 发起请求
                                    # 注意：这里不增加 current_retry，给新 Token 一次公平的机会（除非你希望严格限制总次数）
                                    # 为了稳健性，稍微 sleep 一下？不需要。
                                    continue

                                except TokenRefreshError as e:
                                    logger.error(f"Token 刷新失败: {e}")
                                    raise HTTPException(status_code=502, detail=f"Token 刷新失败: {str(e)}")

                            # 2. 处理 5xx 错误 (服务端错误)
                            elif response.status_code >= 500:
                                error_text = await response.aread()
                                error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                                logger.warning(f"上游 API {response.status_code} 错误 (尝试 {current_retry+1}/{max_retries+1}): {error_str}")
                                
                                if current_retry < max_retries:
                                    current_retry += 1
                                    import asyncio
                                    import random
                                    # 指数退避 + 抖动
                                    sleep_time = 1.0 * (2 ** (current_retry - 1)) + random.uniform(0, 1)
                                    logger.info(f"等待 {sleep_time:.2f}s 后重试...")
                                    await asyncio.sleep(sleep_time)
                                    continue
                                else:
                                    logger.error("重试耗尽，抛出 502")
                                    raise HTTPException(
                                        status_code=502, 
                                        detail=f"上游 API 错误 (重试耗尽): {error_str}"
                                    )

                            # 3. 处理其他错误 (400, 429等)
                            elif response.status_code != 200:
                                error_text = await response.aread()
                                error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                                logger.error(f"上游 API 错误: {response.status_code} {error_str}")

                                # 检查配额用完
                                if "ServiceQuotaExceededException" in error_str and "MONTHLY_REQUEST_COUNT" in error_str:
                                    logger.error(f"账号 {account.get('id') if account else 'legacy'} 月度配额已用完")
                                    if account:
                                        from datetime import datetime
                                        quota_info = {
                                            "monthly_quota_exhausted": True,
                                            "exhausted_at": datetime.now().isoformat()
                                        }
                                        current_other = account.get('other') or {}
                                        if isinstance(current_other, str):
                                            import json
                                            try: current_other = json.loads(current_other)
                                            except: current_other = {}
                                        if not isinstance(current_other, dict): current_other = {}
                                        
                                        current_other.update(quota_info)
                                        update_account(account['id'], enabled=False, other=current_other)
                                        
                                        if account.get('id'):
                                            from src.auth.account_distributor import get_account_distributor
                                            get_account_distributor().record_usage(account['id'], success=False)
                                            
                                        raise HTTPException(status_code=429, detail="账号月度配额已用完，已自动禁用该账号。")
                                    else:
                                        raise HTTPException(status_code=429, detail="Amazon Q 月度配额已用完。")

                                # 处理 429 错误 (Rate Limit)
                                if response.status_code == 429:
                                    if account:
                                        from src.auth.account_manager import set_account_cooldown
                                        set_account_cooldown(account['id'], 300)
                                        logger.warning(f"账号 {account['id']} 触发速率限制，进入 5 分钟冷却期")
                                        from src.auth.account_distributor import get_account_distributor
                                        get_account_distributor().record_usage(account['id'], success=False)
                                        
                                    raise HTTPException(status_code=429, detail="请求过于频繁，账号已进入 5 分钟冷却期，请稍后重试")

                                raise HTTPException(
                                    status_code=response.status_code,
                                    detail=f"上游 API 错误: {error_str}"
                                )

                            # 4. 正常响应
                            async for chunk in response.aiter_bytes():
                                if chunk:
                                    yield chunk
                            return

                    except httpx.RequestError as e:
                        logger.error(f"网络请求错误: {e}")
                        if current_retry < max_retries:
                            current_retry += 1
                            logger.warning(f"网络错误，{1.0}s 后重试 (尝试 {current_retry}/{max_retries})")
                            import asyncio
                            await asyncio.sleep(1.0)
                            continue
                        raise HTTPException(status_code=502, detail=f"上游服务网络错误: {str(e)}")


        # 返回流式响应
        account_id_for_tracking = account.get('id') if account else None
        
        # 处理 Prompt Caching 模拟
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0
        
        if _cache_manager is not None:
            # 从请求中提取可缓存内容
            cacheable_content, token_count = _cache_manager.extract_cacheable_content(request_data)
            
            if cacheable_content and token_count > 0:
                # 计算缓存键并检查缓存
                cache_key = _cache_manager.calculate_cache_key(cacheable_content)
                cache_result = _cache_manager.check_cache(cache_key, token_count)
                
                cache_creation_input_tokens = cache_result.cache_creation_input_tokens
                cache_read_input_tokens = cache_result.cache_read_input_tokens
                
                if cache_result.is_hit:
                    logger.info(f"Prompt Cache 命中: {token_count} tokens (key: {cache_key[:16]}...)")
                else:
                    logger.info(f"Prompt Cache 未命中: {token_count} tokens (key: {cache_key[:16]}...)")
        
        async def claude_stream():
            async for event in handle_amazonq_stream(
                byte_stream(),
                model=model,
                request_data=request_data,
                account_id=account_id_for_tracking,
                channel="amazonq",
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens
            ):
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


@app.post("/v1/gemini/messages")
async def create_gemini_message(request: Request, _: bool = Depends(verify_api_key), retry_account: Optional[Dict[str, Any]] = None):
    """
    Gemini API 端点
    接收 Claude 格式的请求，转换为 Gemini 格式并返回流式响应
    
    Args:
        retry_account: 用于重试的账号（内部使用）
    """
    try:
        # 解析请求体
        request_data = await request.json()

        # 转换为 ClaudeRequest 对象
        claude_req = parse_claude_request(request_data)

        # 检查是否指定了特定账号（用于测试）
        specified_account_id = request.headers.get("X-Account-ID")
        test_mode = request.headers.get("X-Test-Mode") == "true"  # 测试模式标志
        session_bound = False  # 标记是否使用了会话绑定

        if retry_account:
            # 使用重试传入的账号
            account = retry_account
            logger.info(f"使用重试账号: {account['label']} (ID: {account['id']})")
        elif specified_account_id:
            # 使用指定的账号
            account = get_account(specified_account_id)
            if not account:
                raise HTTPException(status_code=404, detail=f"账号不存在: {specified_account_id}")
            # 测试模式下允许使用禁用的账号
            if not test_mode and not account.get('enabled'):
                raise HTTPException(status_code=403, detail=f"账号已禁用: {specified_account_id}")
            if account.get('type') != 'gemini':
                raise HTTPException(status_code=400, detail=f"账号类型不是 Gemini: {specified_account_id}")
            logger.info(f"使用指定 Gemini 账号: {account['label']} (ID: {account['id']})")
        else:
            # KiroGate 风格：使用智能账号分配器
            try:
                distributor = get_account_distributor()
                account = distributor.get_best_account(account_type="gemini", model=claude_req.model)
                logger.info(f"智能分配 Gemini 账号: {account.get('label', 'N/A')} (ID: {account['id']})")
            except DistributorNoAccountError:
                # 回退到随机选择
                account = get_random_account(account_type="gemini", model=claude_req.model)
                if not account:
                    raise HTTPException(status_code=503, detail=f"没有可用的 Gemini 账号支持模型 {claude_req.model}")
                logger.info(f"随机选择 Gemini 账号: {account.get('label', 'N/A')} (ID: {account['id']}) - 模型: {claude_req.model}")

        # 检查并使用数据库中的 access token
        other = account.get("other") or {}
        if isinstance(other, str):
            import json
            try:
                other = json.loads(other)
            except json.JSONDecodeError:
                other = {}

        access_token = account.get("accessToken")
        token_expires_at = None

        # 从 other 字段读取过期时间
        if access_token:
            if other.get("token_expires_at"):
                try:
                    from datetime import datetime, timedelta
                    token_expires_at = datetime.fromisoformat(other["token_expires_at"])
                    if datetime.now() >= token_expires_at - timedelta(minutes=5):
                        logger.info(f"Gemini access token 即将过期，需要刷新")
                        access_token = None
                        token_expires_at = None
                except Exception as e:
                    logger.warning(f"解析 Gemini token 过期时间失败: {e}")
                    access_token = None
                    token_expires_at = None
            else:
                # 如果有 access_token 但没有过期时间,清空 token 强制刷新一次
                logger.info(f"Gemini access token 缺少过期时间,强制刷新")
                access_token = None
                token_expires_at = None

        # 初始化 Token 管理器
        token_manager = GeminiTokenManager(
            client_id=account["clientId"],
            client_secret=account["clientSecret"],
            refresh_token=account["refreshToken"],
            api_endpoint=other.get("api_endpoint", "https://daily-cloudcode-pa.sandbox.googleapis.com"),
            access_token=access_token,
            token_expires_at=token_expires_at
        )

        # 确保 token 有效（如果需要会自动刷新）
        await token_manager.get_access_token()

        # 获取项目 ID
        project_id = other.get("project") or await token_manager.get_project_id()

        # 如果 token 被刷新，更新数据库
        if token_manager.access_token != access_token:
            from src.auth.account_manager import update_account_tokens
            # 更新 other 字段，保存过期时间
            other["token_expires_at"] = token_manager.token_expires_at.isoformat() if token_manager.token_expires_at else None
            update_account(account["id"], access_token=token_manager.access_token, other=other)
            logger.info(f"Gemini access token 已更新到数据库")

        # 应用模型映射（如果账号有配置）
        from src.processing.model_mapper import apply_model_mapping
        original_model = claude_req.model
        mapped_model = apply_model_mapping(account, original_model)
        if mapped_model != original_model:
            claude_req.model = mapped_model


        # 转换为 Gemini 请求
        gemini_request = convert_claude_to_gemini(
            claude_req,
            project=project_id
        )

        # 获取认证头
        auth_headers = await token_manager.get_auth_headers()

        # 构建完整的请求头
        headers = {
            **auth_headers,
            "Content-Type": "application/json",
            "User-Agent": "antigravity/1.11.3 darwin/arm64",
            "Accept-Encoding": "gzip"
        }

        # API URL
        api_url = f"{other.get('api_endpoint', 'https://daily-cloudcode-pa.sandbox.googleapis.com')}/v1internal:streamGenerateContent?alt=sse"

        async def gemini_byte_stream():
            async with httpx.AsyncClient(timeout=300.0) as client:
                try:
                    logger.info(f"[HTTP] 开始请求 Gemini API: {api_url}")
                    async with client.stream(
                        "POST",
                        api_url,
                        json=gemini_request,
                        headers=headers
                    ) as response:
                        logger.info(f"[HTTP] 收到响应: status_code={response.status_code}")
                        logger.info(f"[HTTP] 响应头: {dict(response.headers)}")

                        # 检测 Gemini API 空响应问题
                        content_length = response.headers.get('content-length', '')
                        if content_length == '0':
                            logger.error("[HTTP] Gemini API 返回空响应 (content-length: 0)")
                            # 返回标准的 Claude API SSE 流，但内容为空
                            import json
                            events = [
                                'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_empty","type":"message","role":"assistant","content":[],"model":"' + claude_req.model + '","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":0,"output_tokens":0}}}\n\n',
                                'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
                                'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
                                'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":0}}\n\n',
                                'event: message_stop\ndata: {"type":"message_stop"}\n\n'
                            ]
                            for event in events:
                                yield event.encode('utf-8')
                            return

                        if response.status_code != 200:
                            error_text = await response.aread()
                            error_str = error_text.decode() if isinstance(error_text, bytes) else str(error_text)
                            logger.error(f"Gemini API 错误: {response.status_code} {error_str}")

                            # 处理 429 Resource Exhausted 错误
                            if response.status_code == 429:
                                try:
                                    from src.auth.account_manager import mark_model_exhausted, update_account, set_account_cooldown
                                    from src.gemini.converter import map_claude_model_to_gemini

                                    # 获取 Gemini 模型名称
                                    gemini_model = map_claude_model_to_gemini(claude_req.model)
                                    logger.info(f"收到 429 错误，正在调用 fetchAvailableModels 获取账号 {account['id']} 的最新配额信息...")

                                    # 调用 fetchAvailableModels 获取最新配额信息
                                    models_data = await token_manager.fetch_available_models(project_id)

                                    # 从 models_data 中提取该模型的配额信息
                                    reset_time = None
                                    remaining_fraction = 0
                                    models = models_data.get("models", {})
                                    if gemini_model in models:
                                        quota_info = models[gemini_model].get("quotaInfo", {})
                                        reset_time = quota_info.get("resetTime")
                                        remaining_fraction = quota_info.get("remainingFraction", 0)

                                    # 如果没有找到 resetTime，使用默认值（1小时后）
                                    if not reset_time:
                                        from datetime import datetime, timedelta, timezone
                                        reset_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
                                        logger.warning(f"未找到模型 {gemini_model} 的 resetTime，使用默认值: {reset_time}")

                                    # 更新账号的 creditsInfo
                                    credits_info = extract_credits_from_models_data(models_data)
                                    other = account.get("other") or {}
                                    if isinstance(other, str):
                                        import json
                                        try:
                                            other = json.loads(other)
                                        except json.JSONDecodeError:
                                            other = {}

                                    other["creditsInfo"] = credits_info
                                    update_account(account['id'], other=other)
                                    logger.info(f"已更新账号 {account['id']} 的配额信息")

                                    # 判断是速率限制还是配额用完
                                    if remaining_fraction > 0.03:
                                        # 配额充足，是速率限制（RPM/TPM），设置 5 分钟冷却
                                        set_account_cooldown(account['id'], 300)  # 5 分钟冷却
                                        logger.warning(f"账号 {account['id']} 触发速率限制（RPM/TPM），进入 5 分钟冷却期，剩余配额: {remaining_fraction:.2%}")
                                        
                                        # 抛出特殊异常，让外层处理重试
                                        raise HTTPException(
                                            status_code=429,
                                            detail=f"RATE_LIMIT_RETRY_AVAILABLE:速率限制：账号已进入 5 分钟冷却期（剩余配额: {remaining_fraction:.2%}）"
                                        )
                                    else:
                                        # 配额不足，真的用完了
                                        mark_model_exhausted(account['id'], gemini_model, reset_time)
                                        logger.warning(f"账号 {account['id']} 的模型 {gemini_model} 配额已用完（剩余: {remaining_fraction:.2%}），重置时间: {reset_time}")
                                        
                                        # 抛出特殊异常，让外层处理重试
                                        raise HTTPException(
                                            status_code=429,
                                            detail=f"QUOTA_EXHAUSTED_RETRY_AVAILABLE:配额已用完，重置时间: {reset_time}"
                                        )

                                except HTTPException:
                                    raise
                                except Exception as e:
                                    logger.error(f"处理 429 错误时出错: {e}", exc_info=True)

                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"Gemini API 错误: {error_str}"
                            )

                        # 返回字节流
                        logger.info("[HTTP] 开始迭代字节流")
                        chunk_count = 0
                        total_bytes = 0
                        async for chunk in response.aiter_bytes():
                            chunk_count += 1
                            if chunk:
                                total_bytes += len(chunk)
                                logger.info(f"[HTTP] Chunk {chunk_count}: {len(chunk)} 字节")
                                yield chunk
                            else:
                                logger.debug(f"[HTTP] Chunk {chunk_count}: 空 chunk")
                        logger.info(f"[HTTP] 字节流结束: 共 {chunk_count} 个 chunk, 总计 {total_bytes} 字节")

                except httpx.RequestError as e:
                    logger.error(f"请求错误: {e}")
                    raise HTTPException(status_code=502, detail=f"上游服务错误: {str(e)}")

        # 返回流式响应
        gemini_account_id = account.get('id') if account else None
        
        # 处理 Prompt Caching 模拟
        gemini_cache_creation_input_tokens = 0
        gemini_cache_read_input_tokens = 0
        
        if _cache_manager is not None:
            # 从请求中提取可缓存内容
            cacheable_content, token_count = _cache_manager.extract_cacheable_content(request_data)
            
            if cacheable_content and token_count > 0:
                # 计算缓存键并检查缓存
                cache_key = _cache_manager.calculate_cache_key(cacheable_content)
                cache_result = _cache_manager.check_cache(cache_key, token_count)
                
                gemini_cache_creation_input_tokens = cache_result.cache_creation_input_tokens
                gemini_cache_read_input_tokens = cache_result.cache_read_input_tokens
                
                if cache_result.is_hit:
                    logger.info(f"[Gemini] Prompt Cache 命中: {token_count} tokens (key: {cache_key[:16]}...)")
                else:
                    logger.info(f"[Gemini] Prompt Cache 未命中: {token_count} tokens (key: {cache_key[:16]}...)")
        
        async def claude_stream():
            async for event in handle_gemini_stream(
                gemini_byte_stream(),
                model=claude_req.model,
                account_id=gemini_account_id,
                cache_creation_input_tokens=gemini_cache_creation_input_tokens,
                cache_read_input_tokens=gemini_cache_read_input_tokens
            ):
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

    except HTTPException as e:
        # 检查是否是可重试的 429 错误
        if e.status_code == 429 and not specified_account_id and not retry_account:
            detail = str(e.detail)
            if "RATE_LIMIT_RETRY_AVAILABLE:" in detail or "QUOTA_EXHAUSTED_RETRY_AVAILABLE:" in detail:
                logger.info("检测到 429 错误，尝试切换到其他 Gemini 账号重试...")
                new_account = get_random_account(account_type="gemini", model=claude_req.model)
                if new_account and new_account['id'] != account['id']:
                    logger.info(f"找到新账号 {new_account['label']} (ID: {new_account['id']})，开始重试")
                    # 递归调用，使用新账号重试
                    return await create_gemini_message(request, _, retry_account=new_account)
                else:
                    logger.warning("没有其他可用的 Gemini 账号")
                    # 清理错误消息中的重试标记
                    e.detail = detail.replace("RATE_LIMIT_RETRY_AVAILABLE:", "").replace("QUOTA_EXHAUSTED_RETRY_AVAILABLE:", "")
        raise
    except Exception as e:
        logger.error(f"处理 Gemini 请求时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


@app.post("/v1/custom_api/messages")
async def create_custom_api_message(request: Request, _: bool = Depends(verify_api_key)):
    """
    Custom API 端点
    接收 Claude 格式的请求，根据账号配置转换为 OpenAI 或 Claude 格式并返回流式响应
    """
    try:
        # 解析请求体
        request_data = await request.json()

        # 转换为 ClaudeRequest 对象
        claude_req = parse_claude_request(request_data)

        # 检查是否指定了特定账号（用于测试）
        specified_account_id = request.headers.get("X-Account-ID")
        test_mode = request.headers.get("X-Test-Mode") == "true"  # 测试模式标志
        session_bound = False  # 标记是否使用了会话绑定

        if specified_account_id:
            # 使用指定的账号
            account = get_account(specified_account_id)
            if not account:
                raise HTTPException(status_code=404, detail=f"账号不存在: {specified_account_id}")
            # 测试模式下允许使用禁用的账号
            if not test_mode and not account.get('enabled'):
                raise HTTPException(status_code=403, detail=f"账号已禁用: {specified_account_id}")
            if account.get('type') != 'custom_api':
                raise HTTPException(status_code=400, detail=f"账号类型不是 Custom API: {specified_account_id}")
            logger.info(f"使用指定 Custom API 账号: {account.get('label', 'N/A')} (ID: {account['id']})")
        else:
            # KiroGate 风格：使用智能账号分配器
            try:
                distributor = get_account_distributor()
                # Custom API 通常不区分模型（或所有账号支持所有模型），也可以传递 model 参数用于过滤
                account = distributor.get_best_account(account_type="custom_api", model=claude_req.model)
                logger.info(f"智能分配 Custom API 账号: {account.get('label', 'N/A')} (ID: {account['id']})")
            except DistributorNoAccountError:
                # 回退到随机选择
                account = get_random_account(account_type="custom_api")
                if not account:
                    raise HTTPException(status_code=503, detail="没有可用的 Custom API 账号")
                logger.info(f"随机选择 Custom API 账号: {account.get('label', 'N/A')} (ID: {account['id']})")

        # 返回流式响应
        custom_api_account_id = account.get('id')

        # 处理 Prompt Caching 模拟
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0
        
        if _cache_manager is not None:
            # 从请求中提取可缓存内容
            cacheable_content, token_count = _cache_manager.extract_cacheable_content(request_data)
            
            if cacheable_content and token_count > 0:
                # 计算缓存键并检查缓存
                cache_key = _cache_manager.calculate_cache_key(cacheable_content)
                cache_result = _cache_manager.check_cache(cache_key, token_count)
                
                cache_creation_input_tokens = cache_result.cache_creation_input_tokens
                cache_read_input_tokens = cache_result.cache_read_input_tokens
                
                if cache_result.is_hit:
                    logger.info(f"Custom API Prompt Cache 命中: {token_count} tokens (key: {cache_key[:16]}...)")
                else:
                    logger.info(f"Custom API Prompt Cache 未命中: {token_count} tokens (key: {cache_key[:16]}...)")

        async def custom_api_stream():
            async for event in handle_custom_api_request(
                account=account,
                claude_req=claude_req,
                request_data=request_data,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens
            ):
                yield event

        return StreamingResponse(
            custom_api_stream(),
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
        logger.error(f"处理 Custom API 请求时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


# 账号管理 API 端点
@app.get("/v2/accounts")
async def list_accounts(_: bool = Depends(verify_admin_key)):
    """列出所有账号"""
    accounts = list_all_accounts()
    return JSONResponse(content=accounts)


@app.get("/v2/accounts/{account_id}")
async def get_account_detail(account_id: str, _: bool = Depends(verify_admin_key)):
    """获取账号详情"""
    account = get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    return JSONResponse(content=account)


@app.post("/v2/accounts")
async def create_account_endpoint(body: AccountCreate, _: bool = Depends(verify_admin_key)):
    """创建新账号"""
    try:
        account = create_account(
            label=body.label,
            client_id=body.clientId,
            client_secret=body.clientSecret,
            refresh_token=body.refreshToken,
            access_token=body.accessToken,
            other=body.other,
            enabled=body.enabled if body.enabled is not None else True,
            account_type=body.type,
            weight=body.weight if body.weight is not None else 50,
            rate_limit_per_hour=body.rate_limit_per_hour if body.rate_limit_per_hour is not None else 20
        )
        return JSONResponse(content=account)
    except Exception as e:
        logger.error(f"创建账号失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建账号失败: {str(e)}")


@app.patch("/v2/accounts/{account_id}")
async def update_account_endpoint(account_id: str, body: AccountUpdate, _: bool = Depends(verify_admin_key)):
    """更新账号信息"""
    try:
        # 先更新基本字段
        account = update_account(
            account_id=account_id,
            label=body.label,
            client_id=body.clientId,
            client_secret=body.clientSecret,
            refresh_token=body.refreshToken,
            access_token=body.accessToken,
            other=body.other,
            enabled=body.enabled,
            weight=body.weight
        )
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")
        
        # 如果需要更新 rate_limit_per_hour
        if body.rate_limit_per_hour is not None:
            account = update_account_rate_limit(account_id, body.rate_limit_per_hour)
        
        return JSONResponse(content=account)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新账号失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新账号失败: {str(e)}")


@app.delete("/v2/accounts/{account_id}")
async def delete_account_endpoint(account_id: str, _: bool = Depends(verify_admin_key)):
    """删除账号"""
    success = delete_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="账号不存在")
    return JSONResponse(content={"deleted": account_id})


@app.post("/v2/accounts/{account_id}/refresh")
async def manual_refresh_endpoint(account_id: str, _: bool = Depends(verify_admin_key)):
    """手动刷新账号 token"""
    try:
        account = get_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")

        account_type = account.get("type", "amazonq")

        if account_type == "gemini":
            # Gemini 账号刷新
            other = account.get("other") or {}
            if isinstance(other, str):
                import json
                try:
                    other = json.loads(other)
                except json.JSONDecodeError:
                    other = {}

            token_manager = GeminiTokenManager(
                client_id=account["clientId"],
                client_secret=account["clientSecret"],
                refresh_token=account["refreshToken"],
                api_endpoint=other.get("api_endpoint", "https://daily-cloudcode-pa.sandbox.googleapis.com")
            )
            await token_manager.refresh_access_token()

            # 更新数据库，保存 access_token 和过期时间
            other["token_expires_at"] = token_manager.token_expires_at.isoformat() if token_manager.token_expires_at else None
            refreshed_account = update_account(
                account_id=account_id,
                access_token=token_manager.access_token,
                other=other
            )
            return JSONResponse(content=refreshed_account)
        else:
            # Amazon Q 账号刷新
            refreshed_account = await refresh_account_token(account)
            return JSONResponse(content=refreshed_account)
    except TokenRefreshError as e:
        logger.error(f"刷新 token 失败: {e}")
        raise HTTPException(status_code=502, detail=f"刷新 token 失败: {str(e)}")
    except Exception as e:
        logger.error(f"刷新 token 失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新 token 失败: {str(e)}")


@app.post("/v2/accounts/refresh-all")
async def refresh_all_accounts(_: bool = Depends(verify_admin_key)):
    """批量刷新所有 Amazon Q 账号的 token，检测被封禁账号"""
    try:
        # 获取所有 Amazon Q 类型的账号
        all_accounts = list_all_accounts()
        amazonq_accounts = [acc for acc in all_accounts if acc.get('type', 'amazonq') == 'amazonq']

        if not amazonq_accounts:
            return JSONResponse(content={
                "success": True,
                "message": "没有 Amazon Q 账号需要刷新",
                "total": 0,
                "results": []
            })

        results = []
        success_count = 0
        failed_count = 0
        banned_count = 0

        logger.info(f"开始批量刷新 {len(amazonq_accounts)} 个 Amazon Q 账号")

        for account in amazonq_accounts:
            account_id = account.get('id')
            account_label = account.get('label', 'N/A')
            result = {
                "id": account_id,
                "label": account_label,
                "status": "unknown",
                "message": ""
            }

            try:
                # 尝试刷新 token
                refreshed_account = await refresh_account_token(account)
                result["status"] = "success"
                result["message"] = "Token 刷新成功"
                success_count += 1
                logger.info(f"账号 {account_id} ({account_label}) 刷新成功")

            except TokenRefreshError as e:
                error_msg = str(e)
                result["message"] = error_msg

                # 检测是否被封禁
                if "账号已被封禁" in error_msg or "invalid_grant" in error_msg.lower():
                    result["status"] = "banned"
                    banned_count += 1
                    logger.warning(f"账号 {account_id} ({account_label}) 已被封禁")
                else:
                    result["status"] = "failed"
                    failed_count += 1
                    logger.error(f"账号 {account_id} ({account_label}) 刷新失败: {error_msg}")

            except Exception as e:
                result["status"] = "error"
                result["message"] = f"未知错误: {str(e)}"
                failed_count += 1
                logger.error(f"账号 {account_id} ({account_label}) 刷新时发生错误: {e}")

            results.append(result)

        summary = {
            "success": True,
            "message": f"批量刷新完成: 成功 {success_count}, 失败 {failed_count}, 被封禁 {banned_count}",
            "total": len(amazonq_accounts),
            "success_count": success_count,
            "failed_count": failed_count,
            "banned_count": banned_count,
            "results": results
        }

        logger.info(f"批量刷新完成: 总计 {len(amazonq_accounts)}, 成功 {success_count}, 失败 {failed_count}, 被封禁 {banned_count}")
        return JSONResponse(content=summary)

    except Exception as e:
        logger.error(f"批量刷新账号失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量刷新失败: {str(e)}")


@app.get("/v2/accounts/{account_id}/quota")
async def get_account_quota(account_id: str, _: bool = Depends(verify_admin_key)):
    """获取 Gemini 账号配额信息"""
    try:
        account = get_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")

        account_type = account.get("type", "amazonq")
        if account_type != "gemini":
            raise HTTPException(status_code=400, detail="只有 Gemini 账号支持配额查询")

        other = account.get("other") or {}
        token_manager = GeminiTokenManager(
            client_id=account["clientId"],
            client_secret=account["clientSecret"],
            refresh_token=account["refreshToken"],
            api_endpoint=other.get("api_endpoint", "https://daily-cloudcode-pa.sandbox.googleapis.com")
        )

        project_id = other.get("project") or await token_manager.get_project_id()
        models_data = await token_manager.fetch_available_models(project_id)

        return JSONResponse(content=models_data)
    except Exception as e:
        logger.error(f"获取配额信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取配额信息失败: {str(e)}")


@app.get("/v2/accounts/{account_id}/stats")
async def get_account_stats(account_id: str, _: bool = Depends(verify_admin_key)):
    """获取账号调用统计信息（包含 token 用量）"""
    try:
        from src.auth.account_manager import get_account_call_stats, get_account_cooldown_remaining
        from src.processing.usage_tracker import get_usage_summary
        
        account = get_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")
        
        # 获取调用统计
        stats = get_account_call_stats(account_id)
        
        # 添加冷却状态
        cooldown_remaining = get_account_cooldown_remaining(account_id)
        stats["cooldown_remaining_seconds"] = cooldown_remaining
        stats["is_in_cooldown"] = cooldown_remaining > 0
        
        # 获取 token 用量统计（当天和当月）
        day_usage = get_usage_summary(period="day", account_id=account_id, include_cost=True)
        month_usage = get_usage_summary(period="month", account_id=account_id, include_cost=True)
        
        stats["token_usage"] = {
            "today": {
                "request_count": day_usage.get("request_count", 0),
                "input_tokens": day_usage.get("input_tokens", 0),
                "output_tokens": day_usage.get("output_tokens", 0),
                "total_tokens": day_usage.get("total_tokens", 0),
                "cache_creation_input_tokens": day_usage.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": day_usage.get("cache_read_input_tokens", 0),
                "total_cost": day_usage.get("total_cost", 0),
                "currency": day_usage.get("currency", "USD"),
            },
            "this_month": {
                "request_count": month_usage.get("request_count", 0),
                "input_tokens": month_usage.get("input_tokens", 0),
                "output_tokens": month_usage.get("output_tokens", 0),
                "total_tokens": month_usage.get("total_tokens", 0),
                "cache_creation_input_tokens": month_usage.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": month_usage.get("cache_read_input_tokens", 0),
                "total_cost": month_usage.get("total_cost", 0),
                "currency": month_usage.get("currency", "USD"),
            }
        }
        
        return JSONResponse(content=stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取账号统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取账号统计失败: {str(e)}")


@app.post("/v2/accounts/{account_id}/test")
async def test_custom_api_account(account_id: str, _: bool = Depends(verify_admin_key)):
    """
    测试 Custom API 账号连接
    
    发送一个简单的测试请求到配置的 API，验证连接和认证是否正常。
    
    Requirements: 6.1, 6.2, 6.3
    """
    try:
        account = get_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")

        account_type = account.get("type", "amazonq")
        if account_type != "custom_api":
            raise HTTPException(status_code=400, detail="只有 Custom API 账号支持此测试端点")

        # 从账号配置中提取信息
        other = account.get("other", {})
        if isinstance(other, str):
            import json as json_module
            try:
                other = json_module.loads(other)
            except json_module.JSONDecodeError:
                other = {}

        api_format = other.get("format", "openai")
        api_base = other.get("api_base", "")
        model = other.get("model", "gpt-4o")
        api_key = account.get("clientSecret", "")

        if not api_base:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "API Base URL 未配置"
                }
            )

        if not api_key:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "API Key 未配置"
                }
            )

        logger.info(f"测试 Custom API 账号: {account_id}, format={api_format}, api_base={api_base}, model={model}")

        # 根据 API 格式发送测试请求
        async with httpx.AsyncClient(timeout=30.0) as client:
            if api_format == "claude":
                # Claude 格式测试
                api_url = f"{api_base.rstrip('/')}/v1/messages"
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
                test_request = {
                    "model": model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Hi"}]
                }
            else:
                # OpenAI 格式测试
                api_url = f"{api_base.rstrip('/')}/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
                test_request = {
                    "model": model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Hi"}]
                }

            try:
                response = await client.post(api_url, json=test_request, headers=headers)
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    # 提取响应内容用于显示
                    if api_format == "claude":
                        # Claude 格式响应
                        content = response_data.get("content", [])
                        response_text = ""
                        for block in content:
                            if block.get("type") == "text":
                                response_text += block.get("text", "")
                        model_used = response_data.get("model", model)
                    else:
                        # OpenAI 格式响应
                        choices = response_data.get("choices", [])
                        response_text = ""
                        if choices:
                            message = choices[0].get("message", {})
                            response_text = message.get("content", "")
                        model_used = response_data.get("model", model)

                    return JSONResponse(content={
                        "success": True,
                        "message": "连接测试成功",
                        "details": {
                            "api_base": api_base,
                            "model": model_used,
                            "format": api_format,
                            "response_preview": response_text[:100] if response_text else "(无响应内容)"
                        }
                    })
                else:
                    # API 返回错误
                    error_text = response.text
                    try:
                        error_json = response.json()
                        if api_format == "claude":
                            error_message = error_json.get("error", {}).get("message", error_text)
                        else:
                            error_message = error_json.get("error", {}).get("message", error_text)
                    except Exception:
                        error_message = error_text

                    return JSONResponse(
                        status_code=response.status_code,
                        content={
                            "success": False,
                            "error": f"API 返回错误 ({response.status_code}): {error_message}",
                            "details": {
                                "api_base": api_base,
                                "model": model,
                                "format": api_format,
                                "status_code": response.status_code
                            }
                        }
                    )

            except httpx.TimeoutException:
                return JSONResponse(
                    status_code=504,
                    content={
                        "success": False,
                        "error": "连接超时：无法在 30 秒内连接到 API",
                        "details": {
                            "api_base": api_base,
                            "model": model,
                            "format": api_format
                        }
                    }
                )
            except httpx.ConnectError as e:
                return JSONResponse(
                    status_code=502,
                    content={
                        "success": False,
                        "error": f"连接失败：无法连接到 API ({str(e)})",
                        "details": {
                            "api_base": api_base,
                            "model": model,
                            "format": api_format
                        }
                    }
                )
            except httpx.RequestError as e:
                return JSONResponse(
                    status_code=502,
                    content={
                        "success": False,
                        "error": f"请求错误：{str(e)}",
                        "details": {
                            "api_base": api_base,
                            "model": model,
                            "format": api_format
                        }
                    }
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试 Custom API 账号失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"测试失败: {str(e)}")


# ============== URL 登录（设备授权）API ==============
# 内存中的授权会话存储
AUTH_SESSIONS: Dict[str, Dict[str, Any]] = {}


class AuthStartBody(BaseModel):
    """启动登录请求体"""
    label: Optional[str] = None
    enabled: Optional[bool] = True


@app.post("/v2/auth/start")
async def auth_start(body: AuthStartBody, _: bool = Depends(verify_admin_key)):
    """
    启动设备授权流程，返回验证链接
    
    用户需要在浏览器中打开返回的 verificationUriComplete 链接完成 AWS 登录
    """
    from src.auth.auth import register_oidc_client, start_device_authorization
    
    try:
        # 1. 注册 OIDC 客户端
        client_id, client_secret = await register_oidc_client()
        
        # 2. 获取设备授权信息
        dev = await start_device_authorization(client_id, client_secret)
        
        # 3. 创建会话并存储
        auth_id = str(uuid.uuid4())
        sess = {
            "clientId": client_id,
            "clientSecret": client_secret,
            "deviceCode": dev.get("deviceCode"),
            "interval": int(dev.get("interval", 1)),
            "expiresIn": int(dev.get("expiresIn", 600)),
            "verificationUriComplete": dev.get("verificationUriComplete"),
            "userCode": dev.get("userCode"),
            "startTime": int(time.time()),
            "label": body.label,
            "enabled": True if body.enabled is None else bool(body.enabled),
            "status": "pending",
            "error": None,
            "accountId": None,
        }
        AUTH_SESSIONS[auth_id] = sess
        
        logger.info(f"设备授权已启动: authId={auth_id}, userCode={sess['userCode']}")
        
        # 4. 返回验证信息
        return JSONResponse(content={
            "authId": auth_id,
            "verificationUriComplete": sess["verificationUriComplete"],
            "userCode": sess["userCode"],
            "expiresIn": sess["expiresIn"],
            "interval": sess["interval"],
        })
        
    except Exception as e:
        logger.error(f"启动设备授权失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动登录失败: {str(e)}")


@app.get("/v2/auth/status/{auth_id}")
async def auth_status(auth_id: str, _: bool = Depends(verify_admin_key)):
    """查询授权状态"""
    sess = AUTH_SESSIONS.get(auth_id)
    if not sess:
        raise HTTPException(status_code=404, detail="授权会话不存在")
    
    now_ts = int(time.time())
    deadline = sess["startTime"] + min(int(sess.get("expiresIn", 600)), 300)
    remaining = max(0, deadline - now_ts)
    
    return JSONResponse(content={
        "status": sess.get("status"),
        "remaining": remaining,
        "error": sess.get("error"),
        "accountId": sess.get("accountId"),
    })


@app.post("/v2/auth/claim/{auth_id}")
async def auth_claim(auth_id: str, _: bool = Depends(verify_admin_key)):
    """
    阻塞等待用户授权，成功后创建账号
    
    此端点会轮询 AWS OIDC 服务，直到用户完成授权或超时（最多 5 分钟）
    """
    from src.auth.auth import poll_device_token
    
    sess = AUTH_SESSIONS.get(auth_id)
    if not sess:
        raise HTTPException(status_code=404, detail="授权会话不存在")
    
    # 如果已完成，直接返回
    if sess.get("status") in ("completed", "timeout", "error"):
        return JSONResponse(content={
            "status": sess["status"],
            "accountId": sess.get("accountId"),
            "error": sess.get("error"),
        })
    
    try:
        # 1. 轮询获取 token（最多等待 5 分钟）
        toks = await poll_device_token(
            sess["clientId"],
            sess["clientSecret"],
            sess["deviceCode"],
            sess["interval"],
            sess["expiresIn"],
            max_timeout_sec=300,
        )
        
        access_token = toks.get("accessToken")
        refresh_token = toks.get("refreshToken")
        
        if not access_token:
            raise HTTPException(status_code=502, detail="未获取到 accessToken")
        
        # 2. 创建账号
        acc = create_account(
            label=sess.get("label"),
            client_id=sess["clientId"],
            client_secret=sess["clientSecret"],
            refresh_token=refresh_token,
            access_token=access_token,
            other=None,
            enabled=sess.get("enabled", True),
            account_type="amazonq"
        )
        
        # 3. 更新会话状态
        sess["status"] = "completed"
        sess["accountId"] = acc["id"]
        
        logger.info(f"设备授权成功，已创建账号: {acc['id']}")
        
        return JSONResponse(content={
            "status": "completed",
            "account": acc,
        })
        
    except TimeoutError:
        sess["status"] = "timeout"
        sess["error"] = "授权超时（5分钟）"
        logger.warning(f"设备授权超时: authId={auth_id}")
        raise HTTPException(status_code=408, detail="授权超时（5分钟），请重新开始登录")
    except httpx.HTTPError as e:
        sess["status"] = "error"
        sess["error"] = str(e)
        logger.error(f"设备授权失败: {e}")
        raise HTTPException(status_code=502, detail=f"OIDC 错误: {str(e)}")
    except Exception as e:
        sess["status"] = "error"
        sess["error"] = str(e)
        logger.error(f"设备授权失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建账号失败: {str(e)}")


# ============== 管理员登录系统 API ==============


@app.get("/api/admin/status")
async def admin_status(request: Request):
    """
    获取管理员系统状态
    
    检查是否存在管理员账号，以及账号是否被锁定。
    
    Returns:
        AdminStatusResponse: {needSetup: bool, locked: bool, lockRemaining: int}
    
    Requirements: 2.1, 2.4, 3.1
    """
    # 检查是否需要设置管理员账号
    need_setup = not admin_exists()
    
    # 获取客户端 IP
    client_ip = request.client.host if request.client else "unknown"
    
    # 检查账号是否被锁定
    locked, lock_remaining = is_account_locked(client_ip)
    
    return AdminStatusResponse(
        needSetup=need_setup,
        locked=locked,
        lockRemaining=lock_remaining or 0
    )


@app.post("/api/admin/setup")
async def admin_setup(body: AdminSetupRequest, request: Request):
    """
    首次设置管理员账号
    
    验证输入并创建管理员账号。只有在没有管理员账号时才能调用。
    
    Args:
        body: AdminSetupRequest - 包含 username, password, confirmPassword
    
    Returns:
        {success: bool, message: str}
    
    Requirements: 2.2, 2.3, 2.4, 2.5, 7.2, 8.3
    """
    # 检查是否已存在管理员
    if admin_exists():
        logger.warning("尝试重复创建管理员账号")
        raise HTTPException(status_code=409, detail="管理员账号已存在")
    
    # 验证用户名长度
    if len(body.username) < 3 or len(body.username) > 50:
        raise HTTPException(status_code=400, detail="用户名必须为 3-50 个字符")
    
    # 验证密码长度
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="密码必须至少 8 个字符")
    
    # 验证密码确认
    if body.password != body.confirmPassword:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    
    try:
        # 创建管理员账号
        admin = create_admin_user(body.username, body.password)
        
        # 记录日志
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"管理员账号创建成功: {body.username}, IP: {client_ip}")
        
        # 检查是否设置了 ADMIN_KEY，记录弃用警告
        import os
        if os.getenv("ADMIN_KEY"):
            logger.warning("⚠️  检测到 ADMIN_KEY 环境变量。建议迁移到用户名/密码认证后移除 ADMIN_KEY。")
        
        return JSONResponse(content={
            "success": True,
            "message": "管理员账号创建成功"
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建管理员账号失败: {e}")
        raise HTTPException(status_code=500, detail="创建管理员账号失败")


@app.post("/api/admin/login")
async def admin_login(body: AdminLoginRequest, request: Request):
    """
    管理员登录
    
    验证凭证并创建会话。包含速率限制和账号锁定检查。
    
    Args:
        body: AdminLoginRequest - 包含 username, password
    
    Returns:
        AdminLoginResponse: {success: bool, token: str, message: str}
    
    Requirements: 3.2, 3.3, 3.4, 3.5, 8.3
    """
    # 获取客户端信息
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    
    # 检查账号是否被锁定
    locked, lock_remaining = is_account_locked(client_ip)
    if locked:
        logger.warning(f"登录被拒绝：账号已锁定, IP: {client_ip}")
        raise HTTPException(
            status_code=403,
            detail=f"账号已锁定，请 {lock_remaining} 秒后重试"
        )
    
    # 检查速率限制
    allowed, error_msg = check_login_rate_limit(client_ip)
    if not allowed:
        logger.warning(f"登录被拒绝：速率限制, IP: {client_ip}")
        raise HTTPException(status_code=429, detail=error_msg)
    
    # 验证凭证（使用通用错误消息，不透露具体哪个字段错误）
    if not verify_admin_password(body.username, body.password):
        # 记录失败的登录尝试
        record_login_attempt(client_ip, success=False)
        logger.warning(f"登录失败：凭证无效, 用户名: {body.username}, IP: {client_ip}")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 获取管理员信息
    admin = get_admin_user()
    if not admin:
        raise HTTPException(status_code=500, detail="系统错误")
    
    # 创建会话
    token = create_session(admin.id, user_agent)
    
    # 记录成功的登录尝试
    record_login_attempt(client_ip, success=True)
    logger.info(f"登录成功: {body.username}, IP: {client_ip}")
    
    return AdminLoginResponse(
        success=True,
        token=token,
        message="登录成功"
    )


@app.post("/api/admin/logout")
async def admin_logout(request: Request, x_session_token: Optional[str] = Header(None)):
    """
    管理员登出
    
    使当前会话失效。
    
    Args:
        x_session_token: 会话令牌（通过 Header 传递）
    
    Returns:
        {success: bool}
    
    Requirements: 5.1, 8.3
    """
    if not x_session_token:
        raise HTTPException(status_code=401, detail="未提供会话令牌")
    
    # 获取客户端信息
    client_ip = request.client.host if request.client else "unknown"
    
    # 使会话失效
    success = invalidate_session(x_session_token)
    
    if success:
        logger.info(f"登出成功, IP: {client_ip}")
    else:
        logger.warning(f"登出失败：会话不存在, IP: {client_ip}")
    
    return JSONResponse(content={"success": True})


# 管理页面
@app.get("/admin", response_class=FileResponse)
async def admin_page():
    """管理页面
    
    安全说明：
    - 前端会检查 /api/admin/status 来决定显示登录页还是设置页
    - 实际的 API 调用需要会话令牌认证
    - 这个端点只返回静态 HTML 文件
    """
    from pathlib import Path

    # frontend 目录在项目根目录下，不在 src/ 下
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if not frontend_path.exists():
        raise HTTPException(status_code=404, detail="管理页面不存在")
    return FileResponse(str(frontend_path))


# Gemini 投喂站页面
@app.get("/donate", response_class=FileResponse)
async def donate_page():
    """Gemini 投喂站页面"""
    from pathlib import Path
    # frontend 目录在项目根目录下，不在 src/ 下
    frontend_path = Path(__file__).parent.parent / "frontend" / "donate.html"
    if not frontend_path.exists():
        raise HTTPException(status_code=404, detail="投喂站页面不存在")
    return FileResponse(str(frontend_path))


# OAuth 回调页面
@app.get("/oauth-callback-page", response_class=FileResponse)
async def oauth_callback_page():
    """OAuth 回调页面"""
    from pathlib import Path
    # frontend 目录在项目根目录下，不在 src/ 下
    frontend_path = Path(__file__).parent.parent / "frontend" / "oauth-callback-page.html"
    if not frontend_path.exists():
        raise HTTPException(status_code=404, detail="回调页面不存在")
    return FileResponse(str(frontend_path))


# Token 使用量仪表盘页面
@app.get("/dashboard", response_class=FileResponse)
async def dashboard_page():
    """Token 使用量仪表盘页面"""
    from pathlib import Path
    # frontend 目录在项目根目录下，不在 src/ 下
    frontend_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    if not frontend_path.exists():
        raise HTTPException(status_code=404, detail="仪表盘页面不存在")
    return FileResponse(str(frontend_path))


# Gemini OAuth 回调处理
@app.post("/api/gemini/oauth-callback")
async def gemini_oauth_callback_post(request: Request):
    """处理 Gemini OAuth 回调（POST 请求）"""
    try:
        body = await request.json()
        code = body.get("code")

        if not code:
            raise HTTPException(status_code=400, detail="缺少授权码")

        # 从环境变量读取 client credentials
        client_id = os.getenv("GEMINI_DONATE_CLIENT_ID", "")
        client_secret = os.getenv("GEMINI_DONATE_CLIENT_SECRET", "")
        
        if not client_id or not client_secret:
            raise HTTPException(status_code=500, detail="服务器未配置 Gemini OAuth 凭证")

        # 交换授权码获取 tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": "http://localhost:64312/oauth-callback"
                },
                headers={
                    'x-goog-api-client': 'gl-node/22.18.0',
                    'User-Agent': 'google-api-nodejs-client/10.3.0'
                }
            )

            if response.status_code != 200:
                error_msg = f"Token 交换失败: {response.text}"
                logger.error(error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

            tokens = response.json()
            refresh_token = tokens.get('refresh_token')

            if not refresh_token:
                raise HTTPException(status_code=400, detail="未获取到 refresh_token")

        # 测试账号可用性（获取项目 ID）
        token_manager = GeminiTokenManager(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            api_endpoint="https://daily-cloudcode-pa.sandbox.googleapis.com"
        )

        try:
            project_id = await token_manager.get_project_id()
            logger.info(f"账号验证成功，项目 ID: {project_id}")
        except Exception as e:
            error_msg = f"账号验证失败: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        # 获取配额信息
        try:
            models_data = await token_manager.fetch_available_models(project_id)
            credits_info = extract_credits_from_models_data(models_data)
            reset_time = extract_reset_time_from_models_data(models_data)
        except Exception as e:
            logger.warning(f"获取配额信息失败: {e}")
            credits_info = {"models": {}, "summary": {"totalModels": 0, "averageRemaining": 0}}
            reset_time = None

        # 自动导入到数据库
        import uuid
        from datetime import datetime

        label = f"Gemini-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        other_data = {
            "project": project_id,
            "api_endpoint": "https://daily-cloudcode-pa.sandbox.googleapis.com",
            "creditsInfo": credits_info,
            "resetTime": reset_time
        }

        account = create_account(
            label=label,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            access_token=tokens.get('access_token', ''),
            other=other_data,
            enabled=True,
            account_type="gemini"
        )
        logger.info(f"Gemini 账号已添加: {label}")

        return JSONResponse(content={"success": True, "message": "账号添加成功"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理 OAuth 回调失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Gemini OAuth 回调处理（GET 请求，保留兼容性）
@app.get("/api/gemini/oauth-callback")
async def gemini_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    """处理 Gemini OAuth 回调"""
    if error:
        logger.error(f"OAuth 授权失败: {error}")
        return JSONResponse(
            status_code=400,
            content={"error": error, "message": "授权失败"}
        )

    if not code:
        raise HTTPException(status_code=400, detail="缺少授权码")

    from fastapi.responses import RedirectResponse
    try:
        # 从环境变量读取 client credentials
        client_id = os.getenv("GEMINI_DONATE_CLIENT_ID", "")
        client_secret = os.getenv("GEMINI_DONATE_CLIENT_SECRET", "")
        
        if not client_id or not client_secret:
            raise HTTPException(status_code=500, detail="服务器未配置 Gemini OAuth 凭证")

        # 交换授权码获取 tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": f"{get_base_url()}/api/gemini/oauth-callback"
                },
                headers={
                    'x-goog-api-client': 'gl-node/22.18.0',
                    'User-Agent': 'google-api-nodejs-client/10.3.0'
                }
            )

            if response.status_code != 200:
                error_msg = f"Token 交换失败: {response.text}"
                logger.error(error_msg)
                from urllib.parse import quote
                return JSONResponse(
                    status_code=302,
                    headers={"Location": f"/donate?error={quote(error_msg)}"}
                )

            tokens = response.json()
            refresh_token = tokens.get('refresh_token')

            if not refresh_token:
                error_msg = "未获取到 refresh_token"
                logger.error(error_msg)
                from urllib.parse import quote
                return JSONResponse(
                    status_code=302,
                    headers={"Location": f"/donate?error={quote(error_msg)}"}
                )

        # 测试账号可用性（获取项目 ID）
        token_manager = GeminiTokenManager(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            api_endpoint="https://daily-cloudcode-pa.sandbox.googleapis.com"
        )

        try:
            project_id = await token_manager.get_project_id()
            logger.info(f"账号验证成功，项目 ID: {project_id}")
        except Exception as e:
            error_msg = f"账号验证失败: {str(e)}"
            logger.error(error_msg)
            from urllib.parse import quote
            return JSONResponse(
                status_code=302,
                headers={"Location": f"/donate?error={quote(error_msg)}"}
            )

        # 获取配额信息
        try:
            models_data = await token_manager.fetch_available_models(project_id)
            credits_info = extract_credits_from_models_data(models_data)
            reset_time = extract_reset_time_from_models_data(models_data)
        except Exception as e:
            logger.warning(f"获取配额信息失败: {e}")
            credits_info = {"models": {}, "summary": {"totalModels": 0, "averageRemaining": 0}}
            reset_time = None

        # 自动导入到数据库
        import uuid
        from datetime import datetime

        label = f"Gemini-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        other_data = {
            "project": project_id,
            "api_endpoint": "https://daily-cloudcode-pa.sandbox.googleapis.com",
            "creditsInfo": credits_info,
            "resetTime": reset_time
        }

        account = create_account(
            label=label,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            access_token=tokens.get('access_token', ''),
            other=other_data,
            enabled=True,
            account_type="gemini"
        )
        logger.info(f"Gemini 账号已添加: {label}")

        # 重定向回投喂站页面
        return RedirectResponse(url="/donate?success=true", status_code=302)

    except Exception as e:
        logger.error(f"处理 OAuth 回调失败: {e}")
        from urllib.parse import quote
        return RedirectResponse(url=f"/donate?error={quote(str(e))}", status_code=302)


# 获取 Gemini OAuth 配置（仅返回 client_id，不暴露 secret）
@app.get("/api/gemini/oauth-config")
async def get_gemini_oauth_config():
    """获取 Gemini OAuth 配置"""
    client_id = os.getenv("GEMINI_DONATE_CLIENT_ID", "")
    if not client_id:
        return JSONResponse(
            status_code=503,
            content={"error": "OAuth 未配置", "clientId": None}
        )
    return {
        "clientId": client_id,
        "redirectUri": "http://localhost:64312/oauth-callback"
    }


# 获取 Gemini 账号列表和统计信息
@app.get("/api/gemini/accounts")
async def get_gemini_accounts():
    """获取 Gemini 账号列表和统计信息"""
    try:
        accounts = list_enabled_accounts(account_type="gemini")

        # 更新每个账号的配额信息
        updated_accounts = []
        total_credits = 0

        for account in accounts:
            try:
                other = account.get("other") or {}
                if isinstance(other, str):
                    import json
                    try:
                        other = json.loads(other)
                    except json.JSONDecodeError:
                        other = {}

                # 尝试刷新配额信息
                token_manager = GeminiTokenManager(
                    client_id=account.get("clientId", ""),
                    client_secret=account.get("clientSecret", ""),
                    refresh_token=account.get("refreshToken", ""),
                    api_endpoint=other.get("api_endpoint", "https://daily-cloudcode-pa.sandbox.googleapis.com")
                )

                project_id = other.get("project") or await token_manager.get_project_id()
                models_data = await token_manager.fetch_available_models(project_id)

                credits_info = extract_credits_from_models_data(models_data)

                # 更新 other 字段
                other["creditsInfo"] = credits_info
                other["project"] = project_id

                updated_accounts.append({
                    "id": account.get("id", ""),
                    "label": account.get("label", "未命名"),
                    "enabled": account.get("enabled", False),
                    "creditsInfo": credits_info,
                    "projectId": project_id,
                    "created_at": account.get("created_at")
                })

            except Exception as e:
                logger.error(f"更新账号 {account.get('id', 'unknown')} 配额信息失败: {e}")
                other = account.get("other") or {}
                if isinstance(other, str):
                    import json
                    try:
                        other = json.loads(other)
                    except json.JSONDecodeError:
                        other = {}

                updated_accounts.append({
                    "id": account.get("id", ""),
                    "label": account.get("label", "未命名"),
                    "enabled": account.get("enabled", False),
                    "credits": other.get("credits", 0),
                    "resetTime": other.get("resetTime"),
                    "projectId": other.get("project", "N/A"),
                    "created_at": account.get("created_at")
                })

        # 计算每个模型的总配额
        model_totals = {}
        for account in updated_accounts:
            credits_info = account.get("creditsInfo", {})
            models = credits_info.get("models", {})
            for model_id, model_info in models.items():
                if model_info.get("recommended"):
                    if model_id not in model_totals:
                        model_totals[model_id] = {
                            "displayName": model_info.get("displayName", model_id),
                            "totalRemaining": 0,
                            "accountCount": 0
                        }
                    model_totals[model_id]["totalRemaining"] += model_info.get("remainingFraction", 0)
                    model_totals[model_id]["accountCount"] += 1

        # 计算每个模型的平均配额百分比
        for model_id in model_totals:
            avg_fraction = model_totals[model_id]["totalRemaining"] / model_totals[model_id]["accountCount"]
            model_totals[model_id]["averagePercent"] = int(avg_fraction * 100)

        return JSONResponse(content={
            "modelTotals": model_totals,
            "activeCount": len([a for a in accounts if a.get("enabled")]),
            "totalCount": len(accounts),
            "accounts": updated_accounts
        })

    except Exception as e:
        logger.error(f"获取 Gemini 账号列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取账号列表失败: {str(e)}")


def get_base_url() -> str:
    """获取服务器基础 URL"""
    import os
    # 优先使用环境变量
    base_url = os.getenv("BASE_URL")
    if base_url:
        return base_url.rstrip('/')

    # 默认使用 localhost
    port = os.getenv("PORT", "8383")
    return f"http://localhost:{port}"


def extract_credits_from_models_data(models_data: dict) -> dict:
    """从模型数据中提取各个模型的 credits 信息

    返回格式:
    {
        "models": {
            "gemini-3-pro-high": {"remainingFraction": 0.21, "resetTime": "2025-11-20T16:12:51Z"},
            "claude-sonnet-4-5": {"remainingFraction": 0.81, "resetTime": "2025-11-20T16:18:40Z"},
            ...
        },
        "summary": {
            "totalModels": 5,
            "averageRemaining": 0.75
        }
    }
    """
    try:
        models = models_data.get("models", {})
        result = {
            "models": {},
            "summary": {
                "totalModels": 0,
                "averageRemaining": 0
            }
        }

        total_fraction = 0
        count = 0

        for model_id, model_info in models.items():
            quota_info = model_info.get("quotaInfo", {})
            remaining_fraction = quota_info.get("remainingFraction")
            reset_time = quota_info.get("resetTime")

            if remaining_fraction is not None:
                result["models"][model_id] = {
                    "displayName": model_info.get("displayName", model_id),
                    "remainingFraction": remaining_fraction,
                    "remainingPercent": int(remaining_fraction * 100),
                    "resetTime": reset_time,
                    "recommended": model_info.get("recommended", False)
                }
                total_fraction += remaining_fraction
                count += 1

        if count > 0:
            result["summary"]["totalModels"] = count
            result["summary"]["averageRemaining"] = total_fraction / count

        return result
    except Exception as e:
        logger.error(f"提取 credits 失败: {e}")
        return {"models": {}, "summary": {"totalModels": 0, "averageRemaining": 0}}


def extract_reset_time_from_models_data(models_data: dict) -> Optional[str]:
    """从模型数据中提取最早的重置时间

    返回 ISO 8601 格式的时间字符串
    """
    try:
        models = models_data.get("models", {})

        reset_times = []
        for model_id, model_info in models.items():
            quota_info = model_info.get("quotaInfo", {})
            reset_time = quota_info.get("resetTime")
            if reset_time:
                reset_times.append(reset_time)

        # 返回最早的重置时间
        if reset_times:
            return min(reset_times)

        return None
    except Exception as e:
        logger.error(f"提取重置时间失败: {e}")
        return None


def parse_claude_request(data: dict) -> ClaudeRequest:
    """
    解析 Claude API 请求数据

    Args:
        data: 请求数据字典

    Returns:
        ClaudeRequest: Claude 请求对象
    """
    from src.models import ClaudeMessage, ClaudeTool

    # 解析消息
    messages = []
    for msg in data.get("messages", []):
        # 安全地获取 role 和 content，提供默认值
        role = msg.get("role", "user")
        content = msg.get("content", "")
        messages.append(ClaudeMessage(
            role=role,
            content=content
        ))

    # 解析工具
    tools = None
    if "tools" in data:
        tools = []
        for tool in data["tools"]:
            # 安全地获取工具字段，提供默认值
            name = tool.get("name", "")
            description = tool.get("description", "")
            input_schema = tool.get("input_schema", {})

            # 只有当 name 不为空时才添加工具
            if name:
                tools.append(ClaudeTool(
                    name=name,
                    description=description,
                    input_schema=input_schema
                ))

    return ClaudeRequest(
        model=data.get("model", "claude-sonnet-4.5"),
        messages=messages,
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature"),
        tools=tools,
        stream=data.get("stream", True),
        system=data.get("system"),
        thinking=data.get("thinking")
    )


# ============================================================================
# Token 使用量统计 API
# ============================================================================

from src.processing.usage_tracker import get_usage_summary, get_recent_usage


@app.get("/v1/usage")
async def get_usage(
    period: str = "day",
    account_id: Optional[str] = None,
    model: Optional[str] = None,
    _: bool = Depends(verify_api_key)
):
    """
    获取 token 使用量统计
    
    Query Parameters:
        period: 统计周期 (hour/day/week/month/all)，默认 day
        account_id: 按账号筛选（可选）
        model: 按模型筛选（可选）
    
    Returns:
        使用量汇总信息，包含总计和按模型分组的统计
    """
    return get_usage_summary(period=period, account_id=account_id, model=model)


@app.get("/v1/usage/recent")
async def get_recent_usage_records(
    limit: int = 100,
    _: bool = Depends(verify_api_key)
):
    """
    获取最近的使用记录
    
    Query Parameters:
        limit: 返回记录数量，默认 100
    
    Returns:
        最近的使用记录列表
    """
    return get_recent_usage(limit=limit)


# ============================================================================
# Token 计数 API（兼容 Claude API）
# ============================================================================

# 初始化 tiktoken encoder（全局复用，避免重复加载）
try:
    import tiktoken
    TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception as e:
    logger.warning(f"tiktoken 初始化失败: {e}")
    TIKTOKEN_ENCODING = None


def count_tokens_text(text: str) -> int:
    """使用 tiktoken 统计 token 数量"""
    if not text:
        return 0
    if TIKTOKEN_ENCODING:
        return len(TIKTOKEN_ENCODING.encode(text))
    # 回退到简化估算
    return max(1, len(text) // 4)


@app.post("/v1/messages/count_tokens")
async def count_tokens_endpoint(request: Request, _: bool = Depends(verify_api_key)):
    """
    Token 计数端点（兼容 Claude API）
    
    用于预估请求的 input_tokens 数量，Claude Code 等客户端会调用此接口。
    
    Returns:
        {"input_tokens": int}
    """
    try:
        import json
        request_data = await request.json()
        
        text_to_count = ""
        
        # 1. 统计 system prompt
        system = request_data.get("system", "")
        if system:
            if isinstance(system, str):
                text_to_count += system
            elif isinstance(system, list):
                for item in system:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_to_count += item.get("text", "")
        
        # 2. 统计 messages
        messages = request_data.get("messages", [])
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                text_to_count += content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_to_count += item.get("text", "")
                        elif item.get("type") == "tool_use":
                            text_to_count += item.get("name", "")
                            text_to_count += json.dumps(item.get("input", {}), ensure_ascii=False)
                        elif item.get("type") == "tool_result":
                            result_content = item.get("content", "")
                            if isinstance(result_content, str):
                                text_to_count += result_content
                            elif isinstance(result_content, list):
                                for rc in result_content:
                                    if isinstance(rc, dict) and rc.get("type") == "text":
                                        text_to_count += rc.get("text", "")
        
        # 3. 统计 tools 定义
        tools = request_data.get("tools", [])
        if tools:
            text_to_count += json.dumps(tools, ensure_ascii=False)
        
        input_tokens = count_tokens_text(text_to_count)
        
        logger.debug(f"Token 计数: {input_tokens} tokens ({len(text_to_count)} 字符)")
        
        return {"input_tokens": input_tokens}
    
    except Exception as e:
        logger.error(f"Token 计数失败: {e}")
        return {"input_tokens": 0, "error": str(e)}


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
