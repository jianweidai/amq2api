"""
Token 定时刷新调度模块
负责后台定时刷新所有 Amazon Q 账号的 access_token
"""
import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


async def refresh_all_amazonq_accounts() -> Dict[str, Any]:
    """
    刷新所有启用的 Amazon Q 账号的 token
    
    Returns:
        Dict[str, Any]: 刷新结果统计
    """
    from account_manager import list_enabled_accounts
    from auth import refresh_account_token, TokenRefreshError
    
    accounts = list_enabled_accounts(account_type="amazonq")
    
    if not accounts:
        logger.info("没有可用的 Amazon Q 账号需要刷新")
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
    
    total = len(accounts)
    success_count = 0
    failed_count = 0
    
    logger.info(f"开始定时刷新 {total} 个 Amazon Q 账号的 token")
    
    for account in accounts:
        account_id = account.get("id")
        account_label = account.get("label", "未命名")
        
        try:
            # 刷新账号 token
            await refresh_account_token(account)
            success_count += 1
            logger.info(f"✅ 账号 [{account_label}] (ID: {account_id}) token 刷新成功")
            
        except TokenRefreshError as e:
            failed_count += 1
            logger.error(f"❌ 账号 [{account_label}] (ID: {account_id}) token 刷新失败: {str(e)}")
            
        except Exception as e:
            failed_count += 1
            logger.error(f"❌ 账号 [{account_label}] (ID: {account_id}) 刷新时发生未知错误: {str(e)}")
        
        # 避免频繁调用 API，账号之间间隔 1 秒
        await asyncio.sleep(1)
    
    result = {
        "total": total,
        "success": success_count,
        "failed": failed_count,
        "skipped": 0
    }
    
    logger.info(
        f"定时刷新完成 - 总计: {total}, 成功: {success_count}, 失败: {failed_count}"
    )
    
    return result


async def scheduled_token_refresh():
    """
    定时刷新任务主循环
    根据配置的间隔时间，定期刷新所有 Amazon Q 账号的 token
    """
    from config import read_global_config
    
    # 读取配置
    config = await read_global_config()
    
    if not config.enable_auto_refresh:
        logger.info("定时 token 刷新功能已禁用（ENABLE_AUTO_REFRESH=false）")
        return
    
    refresh_interval_hours = config.token_refresh_interval_hours
    refresh_interval_seconds = refresh_interval_hours * 3600
    
    logger.info("=" * 60)
    logger.info("🚀 Token 定时刷新任务已启动")
    logger.info(f"   刷新间隔: {refresh_interval_hours} 小时 ({refresh_interval_seconds} 秒)")
    logger.info(f"   下次刷新: {refresh_interval_hours} 小时后")
    logger.info("=" * 60)
    
    loop_count = 0
    
    while True:
        try:
            # 等待指定的时间间隔
            await asyncio.sleep(refresh_interval_seconds)
            
            loop_count += 1
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            logger.info("=" * 60)
            logger.info(f"⏰ 定时刷新触发 - 第 {loop_count} 次")
            logger.info(f"   触发时间: {current_time}")
            logger.info("=" * 60)
            
            # 执行刷新
            result = await refresh_all_amazonq_accounts()
            
            # 计算下次刷新时间
            next_refresh_time = datetime.now()
            from datetime import timedelta
            next_refresh_time = next_refresh_time + timedelta(hours=refresh_interval_hours)
            next_refresh_str = next_refresh_time.strftime("%Y-%m-%d %H:%M:%S")
            
            logger.info("=" * 60)
            logger.info(f"✅ 定时刷新任务完成")
            logger.info(f"   成功: {result['success']}/{result['total']}")
            logger.info(f"   失败: {result['failed']}/{result['total']}")
            logger.info(f"   下次刷新: {next_refresh_str}")
            logger.info("=" * 60)
            
        except asyncio.CancelledError:
            logger.info("=" * 60)
            logger.info("⏹️  定时刷新任务已停止")
            logger.info(f"   总执行次数: {loop_count}")
            logger.info("=" * 60)
            break
            
        except Exception as e:
            logger.error(f"定时刷新任务发生错误: {str(e)}", exc_info=True)
            # 出错后继续运行，不退出循环
            await asyncio.sleep(60)  # 出错后等待 1 分钟再继续
