"""
测试 Token 统计的时间周期计算
验证"今日"统计是否使用自然日而不是最近24小时
"""
from datetime import datetime, timezone, timedelta


def calculate_period_start(period: str, now: datetime) -> datetime:
    """
    计算统计周期的开始时间（修复后的逻辑）
    
    Args:
        period: 统计周期 (hour/day/week/month/all)
        now: 当前时间
    
    Returns:
        周期开始时间
    """
    if period == "hour":
        # 最近1小时
        return now - timedelta(hours=1)
    elif period == "day":
        # 今日（自然日）：今天 00:00:00 开始
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        # 本周（自然周）：本周一 00:00:00 开始
        start_time = now - timedelta(days=now.weekday())
        return start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        # 本月（自然月）：本月1号 00:00:00 开始
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # all
        return datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_period_calculation():
    """测试不同周期的时间计算"""
    # 使用固定时间点进行测试：2026-01-22 15:30:45
    test_time = datetime(2026, 1, 22, 15, 30, 45, tzinfo=timezone.utc)
    
    print("=" * 60)
    print(f"测试时间: {test_time}")
    print("=" * 60)
    
    # 测试今日
    day_start = calculate_period_start("day", test_time)
    expected_day = datetime(2026, 1, 22, 0, 0, 0, tzinfo=timezone.utc)
    print(f"\n【今日】")
    print(f"  计算结果: {day_start}")
    print(f"  期望结果: {expected_day}")
    print(f"  是否正确: {'✓' if day_start == expected_day else '✗'}")
    assert day_start == expected_day, f"今日统计错误: {day_start} != {expected_day}"
    
    # 测试本周（周三，应该返回本周一）
    week_start = calculate_period_start("week", test_time)
    expected_week = datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc)  # 周一
    print(f"\n【本周】")
    print(f"  计算结果: {week_start}")
    print(f"  期望结果: {expected_week} (周一)")
    print(f"  是否正确: {'✓' if week_start == expected_week else '✗'}")
    assert week_start == expected_week, f"本周统计错误: {week_start} != {expected_week}"
    
    # 测试本月
    month_start = calculate_period_start("month", test_time)
    expected_month = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    print(f"\n【本月】")
    print(f"  计算结果: {month_start}")
    print(f"  期望结果: {expected_month}")
    print(f"  是否正确: {'✓' if month_start == expected_month else '✗'}")
    assert month_start == expected_month, f"本月统计错误: {month_start} != {expected_month}"
    
    # 测试最近1小时
    hour_start = calculate_period_start("hour", test_time)
    expected_hour = datetime(2026, 1, 22, 14, 30, 45, tzinfo=timezone.utc)
    print(f"\n【最近1小时】")
    print(f"  计算结果: {hour_start}")
    print(f"  期望结果: {expected_hour}")
    print(f"  是否正确: {'✓' if hour_start == expected_hour else '✗'}")
    assert hour_start == expected_hour, f"小时统计错误: {hour_start} != {expected_hour}"
    
    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 60)
    print("边界情况测试")
    print("=" * 60)
    
    # 测试月初第一天
    test_time = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    month_start = calculate_period_start("month", test_time)
    print(f"\n月初第一天 00:00:00: {test_time}")
    print(f"  本月开始: {month_start}")
    assert month_start == test_time, "月初第一天测试失败"
    
    # 测试周一
    test_time = datetime(2026, 1, 19, 10, 0, 0, tzinfo=timezone.utc)  # 周一
    week_start = calculate_period_start("week", test_time)
    expected = datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc)
    print(f"\n周一 10:00:00: {test_time}")
    print(f"  本周开始: {week_start}")
    print(f"  期望: {expected}")
    assert week_start == expected, "周一测试失败"
    
    # 测试周日
    test_time = datetime(2026, 1, 25, 23, 59, 59, tzinfo=timezone.utc)  # 周日
    week_start = calculate_period_start("week", test_time)
    expected = datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc)  # 本周一
    print(f"\n周日 23:59:59: {test_time}")
    print(f"  本周开始: {week_start}")
    print(f"  期望: {expected}")
    assert week_start == expected, "周日测试失败"
    
    print("\n✓ 边界情况测试通过！")


if __name__ == "__main__":
    test_period_calculation()
    test_edge_cases()

