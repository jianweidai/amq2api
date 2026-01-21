"""
演示账号统计功能
展示如何查看账号的调用次数和 token 用量
"""
from src.auth.account_manager import (
    create_account,
    delete_account,
    record_api_call,
    get_account_call_stats,
    _ensure_db
)
from src.processing.usage_tracker import record_usage, get_usage_summary


def demo_account_stats():
    """演示账号统计功能"""
    print("=" * 60)
    print("账号统计功能演示")
    print("=" * 60)
    
    # 初始化数据库
    _ensure_db()
    
    # 创建测试账号
    print("\n1. 创建测试账号...")
    account = create_account(
        label="演示账号",
        client_id="demo_client_id",
        client_secret="demo_client_secret",
        refresh_token="demo_refresh_token",
        enabled=True,
        account_type="amazonq"
    )
    print(f"   ✓ 账号已创建: {account['label']} (ID: {account['id'][:8]}...)")
    
    account_id = account['id']
    
    # 模拟一些 API 调用
    print("\n2. 模拟 API 调用...")
    for i in range(5):
        record_api_call(account_id, model="claude-sonnet-4")
    print(f"   ✓ 已记录 5 次 API 调用")
    
    # 模拟 token 使用
    print("\n3. 模拟 Token 使用...")
    
    # 第一次请求
    record_usage(
        model="claude-sonnet-4",
        input_tokens=150,
        output_tokens=80,
        account_id=account_id,
        channel="amazonq"
    )
    print(f"   ✓ 请求 1: 输入 150 tokens, 输出 80 tokens")
    
    # 第二次请求（带缓存）
    record_usage(
        model="claude-sonnet-4",
        input_tokens=200,
        output_tokens=120,
        account_id=account_id,
        channel="amazonq",
        cache_creation_input_tokens=50,
        cache_read_input_tokens=30
    )
    print(f"   ✓ 请求 2: 输入 200 tokens, 输出 120 tokens (缓存创建: 50, 缓存读取: 30)")
    
    # 第三次请求
    record_usage(
        model="claude-sonnet-4",
        input_tokens=100,
        output_tokens=60,
        account_id=account_id,
        channel="amazonq"
    )
    print(f"   ✓ 请求 3: 输入 100 tokens, 输出 60 tokens")
    
    # 获取调用统计
    print("\n4. 查看调用统计...")
    call_stats = get_account_call_stats(account_id)
    print(f"   账号 ID: {call_stats['account_id'][:8]}...")
    print(f"   过去 1 小时调用: {call_stats['calls_last_hour']} 次")
    print(f"   过去 24 小时调用: {call_stats['calls_last_day']} 次")
    print(f"   总调用次数: {call_stats['total_calls']} 次")
    print(f"   每小时限制: {call_stats['rate_limit_per_hour']} 次")
    print(f"   剩余配额: {call_stats['remaining_quota']} 次")
    
    # 获取今日 token 使用统计
    print("\n5. 查看今日 Token 使用统计...")
    day_usage = get_usage_summary(period="day", account_id=account_id)
    print(f"   请求次数: {day_usage['request_count']}")
    print(f"   输入 Token: {day_usage['input_tokens']}")
    print(f"   输出 Token: {day_usage['output_tokens']}")
    print(f"   总 Token: {day_usage['total_tokens']}")
    print(f"   缓存创建 Token: {day_usage['cache_creation_input_tokens']}")
    print(f"   缓存读取 Token: {day_usage['cache_read_input_tokens']}")
    
    # 获取本月 token 使用统计
    print("\n6. 查看本月 Token 使用统计...")
    month_usage = get_usage_summary(period="month", account_id=account_id)
    print(f"   请求次数: {month_usage['request_count']}")
    print(f"   输入 Token: {month_usage['input_tokens']}")
    print(f"   输出 Token: {month_usage['output_tokens']}")
    print(f"   总 Token: {month_usage['total_tokens']}")
    print(f"   缓存创建 Token: {month_usage['cache_creation_input_tokens']}")
    print(f"   缓存读取 Token: {month_usage['cache_read_input_tokens']}")
    
    # 清理
    print("\n7. 清理测试数据...")
    delete_account(account_id)
    print(f"   ✓ 账号已删除")
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)
    print("\n在 Admin 后台中，每个账号卡片会显示：")
    print("  • 今日调用次数和 Token 用量")
    print("  • 本月调用次数和 Token 用量")
    print("  • Token 用量包含输入、输出、缓存创建和缓存读取的详细信息")
    print()


if __name__ == "__main__":
    demo_account_stats()
