"""
演示价格计算功能
展示如何计算 Claude 4.5 系列模型的使用成本
"""
from src.processing.pricing_calculator import (
    identify_model_type,
    calculate_cost,
    format_cost,
    PRICING_TABLE
)


def demo_pricing():
    """演示价格计算功能"""
    print("=" * 70)
    print("Claude 4.5 系列价格计算演示")
    print("=" * 70)
    
    # 显示价格表
    print("\n📋 官方定价表 (基于 Anthropic 官方定价):")
    print("-" * 70)
    print(f"{'模型':<20} {'基础输入':<15} {'缓存写入(5m)':<15} {'缓存读取':<15} {'输出':<15}")
    print("-" * 70)
    
    for model_key, pricing in PRICING_TABLE.items():
        model_name = model_key.replace("-", " ").title()
        print(f"{model_name:<20} "
              f"${pricing['base_input']}/MTok{'':<6} "
              f"${pricing['cache_write_5m']}/MTok{'':<5} "
              f"${pricing['cache_hits']}/MTok{'':<6} "
              f"${pricing['output']}/MTok")
    
    print("\n" + "=" * 70)
    print("示例计算")
    print("=" * 70)
    
    # 示例 1: Sonnet 4.5 基础使用
    print("\n📝 示例 1: Claude Sonnet 4.5 基础使用")
    print("-" * 70)
    print("输入: 100,000 tokens")
    print("输出: 50,000 tokens")
    
    cost1 = calculate_cost(
        model="claude-sonnet-4.5",
        input_tokens=100_000,
        output_tokens=50_000
    )
    
    print(f"\n计算:")
    print(f"  输入成本: (100,000 / 1,000,000) × $3 = $0.30")
    print(f"  输出成本: (50,000 / 1,000,000) × $15 = $0.75")
    print(f"  总成本: {format_cost(cost1)}")
    
    # 示例 2: Sonnet 4.5 带缓存
    print("\n📝 示例 2: Claude Sonnet 4.5 带缓存使用")
    print("-" * 70)
    print("基础输入: 100,000 tokens")
    print("缓存创建: 20,000 tokens (5m)")
    print("缓存读取: 10,000 tokens")
    print("输出: 50,000 tokens")
    
    cost2 = calculate_cost(
        model="claude-sonnet-4.5",
        input_tokens=100_000,
        output_tokens=50_000,
        cache_creation_input_tokens=20_000,
        cache_read_input_tokens=10_000
    )
    
    print(f"\n计算:")
    print(f"  基础输入: (100,000 / 1,000,000) × $3 = $0.300")
    print(f"  缓存创建: (20,000 / 1,000,000) × $3.75 = $0.075")
    print(f"  缓存读取: (10,000 / 1,000,000) × $0.30 = $0.003")
    print(f"  输出成本: (50,000 / 1,000,000) × $15 = $0.750")
    print(f"  总成本: {format_cost(cost2)}")
    
    # 示例 3: Haiku 4.5 (最便宜)
    print("\n📝 示例 3: Claude Haiku 4.5 (最经济)")
    print("-" * 70)
    print("输入: 100,000 tokens")
    print("输出: 50,000 tokens")
    
    cost3 = calculate_cost(
        model="claude-haiku-4.5",
        input_tokens=100_000,
        output_tokens=50_000
    )
    
    print(f"\n计算:")
    print(f"  输入成本: (100,000 / 1,000,000) × $1 = $0.10")
    print(f"  输出成本: (50,000 / 1,000,000) × $5 = $0.25")
    print(f"  总成本: {format_cost(cost3)}")
    
    # 示例 4: Opus 4.5 (最强大)
    print("\n📝 示例 4: Claude Opus 4.5 (最强大)")
    print("-" * 70)
    print("输入: 100,000 tokens")
    print("输出: 50,000 tokens")
    
    cost4 = calculate_cost(
        model="claude-opus-4.5",
        input_tokens=100_000,
        output_tokens=50_000
    )
    
    print(f"\n计算:")
    print(f"  输入成本: (100,000 / 1,000,000) × $5 = $0.50")
    print(f"  输出成本: (50,000 / 1,000,000) × $25 = $1.25")
    print(f"  总成本: {format_cost(cost4)}")
    
    # 成本对比
    print("\n" + "=" * 70)
    print("💰 成本对比 (相同使用量)")
    print("=" * 70)
    print(f"Haiku 4.5:  {format_cost(cost3)} (最经济)")
    print(f"Sonnet 4.5: {format_cost(cost1)} (平衡)")
    print(f"Opus 4.5:   {format_cost(cost4)} (最强大)")
    
    # 模型识别测试
    print("\n" + "=" * 70)
    print("🔍 模型识别测试")
    print("=" * 70)
    
    test_models = [
        "claude-sonnet-4.5",
        "claude-sonnet-4-5",
        "claude-sonnet-4.5-20250929",
        "CLAUDE-SONNET-4.5",
        "claude-sonnet-4",  # 不支持
        "gpt-4",  # 不支持
    ]
    
    for model in test_models:
        model_type = identify_model_type(model)
        if model_type:
            print(f"✓ {model:<35} → {model_type}")
        else:
            print(f"✗ {model:<35} → 无法识别 (不计算成本)")
    
    print("\n" + "=" * 70)
    print("演示完成！")
    print("=" * 70)
    print("\n在 Admin 后台中，系统会自动:")
    print("  • 识别使用的模型类型")
    print("  • 计算每个账号的今日和本月花费")
    print("  • 在 Token 管理界面显示总花费")
    print("  • 仅计算 Claude 4.5 系列模型 (Opus/Sonnet/Haiku)")
    print("  • 基于 Anthropic 官方定价")
    print()


if __name__ == "__main__":
    demo_pricing()
