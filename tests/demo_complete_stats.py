"""
完整的账号统计和价格计算演示
展示从记录使用到查看统计和成本的完整流程
"""
from src.auth.account_manager import (
    create_account,
    delete_account,
    record_api_call,
    get_account_call_stats,
    _ensure_db
)
from src.processing.usage_tracker import record_usage, get_usage_summary
from src.processing.pricing_calculator import format_cost


def demo_complete_stats():
    """完整演示"""
    print("=" * 80)
    print("账号统计和价格计算完整演示")
    print("=" * 80)
    
    # 初始化数据库
    _ensure_db()
    
    # 创建测试账号
    print("\n📝 步骤 1: 创建测试账号")
    print("-" * 80)
    account = create_account(
        label="演示账号 - Sonnet 4.5",
        client_id="demo_client",
        client_secret="demo_secret",
        refresh_token="demo_token",
        enabled=True,
        account_type="amazonq"
    )
    account_id = account['id']
    print(f"✓ 账号已创建: {account['label']}")
    print(f"  ID: {account_id[:16]}...")
    
    # 模拟多次 API 调用
    print("\n📝 步骤 2: 模拟 API 调用")
    print("-" * 80)
    
    # 调用 1: Sonnet 4.5 基础使用
    print("调用 1: Claude Sonnet 4.5 (基础)")
    record_api_call(account_id, model="claude-sonnet-4.5")
    record_usage(
        model="claude-sonnet-4.5",
        input_tokens=50_000,
        output_tokens=25_000,
        account_id=account_id,
        channel="amazonq"
    )
    print("  ✓ 输入: 50K tokens, 输出: 25K tokens")
    
    # 调用 2: Sonnet 4.5 带缓存
    print("调用 2: Claude Sonnet 4.5 (带缓存)")
    record_api_call(account_id, model="claude-sonnet-4.5")
    record_usage(
        model="claude-sonnet-4.5",
        input_tokens=30_000,
        output_tokens=15_000,
        account_id=account_id,
        channel="amazonq",
        cache_creation_input_tokens=10_000,
        cache_read_input_tokens=5_000
    )
    print("  ✓ 输入: 30K, 输出: 15K, 缓存创建: 10K, 缓存读取: 5K")
    
    # 调用 3: Haiku 4.5 (更便宜)
    print("调用 3: Claude Haiku 4.5 (经济型)")
    record_api_call(account_id, model="claude-haiku-4.5")
    record_usage(
        model="claude-haiku-4.5",
        input_tokens=100_000,
        output_tokens=50_000,
        account_id=account_id,
        channel="amazonq"
    )
    print("  ✓ 输入: 100K tokens, 输出: 50K tokens")
    
    # 调用 4: Opus 4.5 (最强大)
    print("调用 4: Claude Opus 4.5 (最强大)")
    record_api_call(account_id, model="claude-opus-4.5")
    record_usage(
        model="claude-opus-4.5",
        input_tokens=20_000,
        output_tokens=10_000,
        account_id=account_id,
        channel="amazonq"
    )
    print("  ✓ 输入: 20K tokens, 输出: 10K tokens")
    
    # 调用 5: 不支持的模型 (不计算成本)
    print("调用 5: Claude Sonnet 4 (不支持价格计算)")
    record_api_call(account_id, model="claude-sonnet-4")
    record_usage(
        model="claude-sonnet-4",
        input_tokens=50_000,
        output_tokens=25_000,
        account_id=account_id,
        channel="amazonq"
    )
    print("  ✓ 输入: 50K tokens, 输出: 25K tokens (不计入成本)")
    
    # 查看调用统计
    print("\n📝 步骤 3: 查看调用统计")
    print("-" * 80)
    call_stats = get_account_call_stats(account_id)
    print(f"总调用次数: {call_stats['total_calls']}")
    print(f"过去 1 小时: {call_stats['calls_last_hour']}")
    print(f"过去 24 小时: {call_stats['calls_last_day']}")
    print(f"每小时限制: {call_stats['rate_limit_per_hour']}")
    print(f"剩余配额: {call_stats['remaining_quota']}")
    
    # 查看 Token 使用统计（今日）
    print("\n📝 步骤 4: 查看今日 Token 使用和成本")
    print("-" * 80)
    day_usage = get_usage_summary(period="day", account_id=account_id, include_cost=True)
    
    print(f"请求次数: {day_usage['request_count']}")
    print(f"输入 Token: {day_usage['input_tokens']:,}")
    print(f"输出 Token: {day_usage['output_tokens']:,}")
    print(f"总 Token: {day_usage['total_tokens']:,}")
    print(f"缓存创建: {day_usage['cache_creation_input_tokens']:,}")
    print(f"缓存读取: {day_usage['cache_read_input_tokens']:,}")
    print(f"\n💰 今日总花费: {format_cost(day_usage['total_cost'])}")
    
    # 按模型分组显示成本
    print("\n📊 按模型分组的成本明细:")
    print("-" * 80)
    print(f"{'模型':<30} {'请求数':<10} {'Token':<15} {'成本':<15}")
    print("-" * 80)
    
    for model_cost in day_usage.get('model_costs', []):
        model_name = model_cost['model']
        request_count = model_cost['request_count']
        total_tokens = model_cost['total_tokens']
        cost = model_cost['cost']
        print(f"{model_name:<30} {request_count:<10} {total_tokens:>12,}   {format_cost(cost):<15}")
    
    # 显示未计算成本的模型
    print("\n⚠️  未计算成本的模型:")
    for model_data in day_usage.get('by_model', []):
        model = model_data['model']
        # 检查是否在 model_costs 中
        if not any(mc['model'] == model for mc in day_usage.get('model_costs', [])):
            print(f"  • {model} (不支持价格计算)")
    
    # 成本分析
    print("\n📈 成本分析:")
    print("-" * 80)
    total_cost = day_usage['total_cost']
    total_tokens = day_usage['total_tokens']
    
    if total_tokens > 0:
        avg_cost_per_1k = (total_cost / total_tokens) * 1000
        print(f"平均成本: {format_cost(avg_cost_per_1k)} / 1K tokens")
    
    if day_usage['request_count'] > 0:
        avg_cost_per_request = total_cost / day_usage['request_count']
        print(f"平均每次请求: {format_cost(avg_cost_per_request)}")
    
    # 预估月度成本
    if total_cost > 0:
        estimated_monthly = total_cost * 30
        print(f"\n📅 预估月度成本 (按今日使用量): {format_cost(estimated_monthly)}")
    
    # 清理
    print("\n📝 步骤 5: 清理测试数据")
    print("-" * 80)
    delete_account(account_id)
    print("✓ 测试账号已删除")
    
    print("\n" + "=" * 80)
    print("演示完成！")
    print("=" * 80)
    print("\n✨ 功能总结:")
    print("  • 自动识别 Claude 4.5 系列模型 (Opus/Sonnet/Haiku)")
    print("  • 精确计算输入、输出和缓存 token 的成本")
    print("  • 支持按账号、时间周期查看统计")
    print("  • 在 Admin 后台显示今日和本月花费")
    print("  • 在 Token 管理界面显示总花费")
    print("  • 基于 Anthropic 官方定价")
    print()


if __name__ == "__main__":
    demo_complete_stats()
