#!/usr/bin/env python3
"""
验证多账号实现的结构完整性
不需要安装依赖,仅检查代码结构
"""

import os
import sys
import ast
import re

def check_file_exists(filepath):
    """检查文件是否存在"""
    exists = os.path.isfile(filepath)
    status = "✓" if exists else "✗"
    print(f"  {status} {filepath}")
    return exists

def check_module_structure(filepath, expected_items):
    """检查模块中是否包含预期的类/函数/变量"""
    print(f"\n检查 {filepath} 结构:")

    if not os.path.isfile(filepath):
        print(f"  ✗ 文件不存在")
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    all_found = True
    for item_type, item_name in expected_items:
        if item_type == 'class':
            pattern = rf'class\s+{item_name}\b'
        elif item_type == 'function':
            pattern = rf'(async\s+)?def\s+{item_name}\s*\('
        elif item_type == 'variable':
            pattern = rf'{item_name}\s*='
        else:
            pattern = item_name

        found = re.search(pattern, content)
        status = "✓" if found else "✗"
        print(f"  {status} {item_type}: {item_name}")
        if not found:
            all_found = False

    return all_found

def check_imports(filepath, expected_imports):
    """检查文件是否包含预期的导入"""
    print(f"\n检查 {filepath} 的导入:")

    if not os.path.isfile(filepath):
        print(f"  ✗ 文件不存在")
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    all_found = True
    for module in expected_imports:
        # 匹配 "import module" 或 "from module import ..."
        pattern = rf'(^|\n)(import\s+{module}\b|from\s+{module}\s+import)'
        found = re.search(pattern, content)
        status = "✓" if found else "✗"
        print(f"  {status} {module}")
        if not found:
            all_found = False

    return all_found

def main():
    print("=" * 80)
    print("多账号实现结构验证")
    print("=" * 80)

    # 检查新增文件
    print("\n1. 检查新增文件:")
    new_files = [
        "account_config.py",
        "exceptions.py",
        "load_balancer.py",
        "account_pool.py",
        "metrics.py",
        "MULTI_ACCOUNT.md",
        ".env.multi_account.example"
    ]

    files_ok = all(check_file_exists(f) for f in new_files)

    # 检查核心模块结构
    print("\n2. 检查核心模块结构:")

    # account_config.py
    account_config_ok = check_module_structure("account_config.py", [
        ('class', 'LoadBalanceStrategy'),
        ('class', 'AccountConfig'),
        ('function', 'is_available'),
        ('function', 'mark_success'),
        ('function', 'mark_error'),
        ('function', 'to_dict')
    ])

    # exceptions.py
    exceptions_ok = check_module_structure("exceptions.py", [
        ('class', 'NoAvailableAccountError'),
        ('class', 'TokenRefreshError'),
        ('class', 'CircuitBreakerOpenError'),
        ('class', 'AccountNotFoundError')
    ])

    # load_balancer.py
    load_balancer_ok = check_module_structure("load_balancer.py", [
        ('class', 'LoadBalancer'),
        ('function', 'select_account'),
        ('function', '_select_round_robin'),
        ('function', '_select_weighted_round_robin'),
        ('function', '_select_least_used'),
        ('function', '_select_random')
    ])

    # account_pool.py
    account_pool_ok = check_module_structure("account_pool.py", [
        ('class', 'AccountPool'),
        ('function', 'select_account'),
        ('function', 'get_account'),
        ('function', 'mark_success'),
        ('function', 'mark_error'),
        ('function', '_open_circuit_breaker'),
        ('function', 'reset_circuit_breaker'),
        ('function', 'enable_account'),
        ('function', 'disable_account'),
        ('function', 'get_stats')
    ])

    # metrics.py
    metrics_ok = check_module_structure("metrics.py", [
        ('variable', 'request_counter'),
        ('variable', 'error_counter'),
        ('variable', 'account_availability'),
        ('function', 'record_request'),
        ('function', 'record_error'),
        ('function', 'set_account_availability'),
        ('function', 'get_metrics')
    ])

    # 检查 main.py 的多账号集成
    print("\n3. 检查 main.py 的多账号集成:")
    main_ok = check_module_structure("main.py", [
        ('function', 'health_check_loop'),
        ('function', 'get_accounts_stats'),
        ('function', 'get_account_detail'),
        ('function', 'enable_account'),
        ('function', 'disable_account'),
        ('function', 'reset_account_errors'),
        ('function', 'get_metrics')
    ])

    # 检查 main.py 的导入
    main_imports_ok = check_imports("main.py", [
        'account_config',
        'exceptions',
        'metrics'
    ])

    # 检查 config.py 的重构
    print("\n4. 检查 config.py 的重构:")
    config_ok = check_module_structure("config.py", [
        ('class', 'GlobalConfig'),
        ('function', '_load_accounts_from_env'),
        ('function', 'load_account_pool'),
        ('function', 'get_account_pool'),
        ('function', 'get_account_cache_dir'),
        ('function', 'get_account_cache_file'),
        ('function', '_load_account_cache'),
        ('function', '_save_account_cache'),
        ('function', 'save_all_account_caches')
    ])

    # 检查 auth.py 的账号参数
    print("\n5. 检查 auth.py 的账号支持:")
    auth_ok = check_module_structure("auth.py", [
        ('function', 'refresh_token'),
        ('function', 'ensure_valid_token'),
        ('function', 'get_auth_headers')
    ])

    # 检查 auth.py 的函数签名(确保接受 AccountConfig 参数)
    with open("auth.py", 'r', encoding='utf-8') as f:
        auth_content = f.read()

    has_account_param = all([
        'async def refresh_token(account: AccountConfig)' in auth_content,
        'async def ensure_valid_token(account: AccountConfig)' in auth_content,
        'async def get_auth_headers(account: AccountConfig)' in auth_content
    ])

    status = "✓" if has_account_param else "✗"
    print(f"  {status} 函数签名包含 AccountConfig 参数")

    # 检查 requirements.txt
    print("\n6. 检查依赖配置:")
    if os.path.isfile("requirements.txt"):
        with open("requirements.txt", 'r') as f:
            reqs = f.read()
        has_prometheus = 'prometheus-client' in reqs
        status = "✓" if has_prometheus else "✗"
        print(f"  {status} prometheus-client 已添加到 requirements.txt")
    else:
        print("  ✗ requirements.txt 不存在")
        has_prometheus = False

    # 检查文档
    print("\n7. 检查文档:")
    doc_items = [
        ("MULTI_ACCOUNT.md", [
            "快速开始",
            "环境变量",
            "负载均衡策略",
            "熔断器",
            "管理 API",
            "Prometheus 指标"
        ]),
        (".env.multi_account.example", [
            "AMAZONQ_ACCOUNT_COUNT",
            "AMAZONQ_ACCOUNT_1_",
            "LOAD_BALANCE_STRATEGY",
            "CIRCUIT_BREAKER_ENABLED"
        ])
    ]

    docs_ok = True
    for doc_file, keywords in doc_items:
        if os.path.isfile(doc_file):
            with open(doc_file, 'r', encoding='utf-8') as f:
                content = f.read()
            missing = [kw for kw in keywords if kw not in content]
            if missing:
                print(f"  ✗ {doc_file} 缺少关键词: {', '.join(missing)}")
                docs_ok = False
            else:
                print(f"  ✓ {doc_file} 包含所有关键内容")
        else:
            print(f"  ✗ {doc_file} 不存在")
            docs_ok = False

    # 总结
    print("\n" + "=" * 80)
    print("验证结果:")
    print("=" * 80)

    results = {
        "新增文件": files_ok,
        "account_config.py": account_config_ok,
        "exceptions.py": exceptions_ok,
        "load_balancer.py": load_balancer_ok,
        "account_pool.py": account_pool_ok,
        "metrics.py": metrics_ok,
        "main.py 集成": main_ok and main_imports_ok,
        "config.py 重构": config_ok,
        "auth.py 重构": auth_ok and has_account_param,
        "依赖配置": has_prometheus,
        "文档": docs_ok
    }

    all_ok = all(results.values())

    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")

    print("\n" + "=" * 80)
    if all_ok:
        print("✓ 所有检查通过! 多账号实现结构完整。")
        print("\n下一步:")
        print("  1. 安装依赖: pip3 install -r requirements.txt")
        print("  2. 配置环境变量: cp .env.multi_account.example .env")
        print("  3. 填写账号信息并启动: ./start.sh")
        return 0
    else:
        print("✗ 部分检查未通过,请修复上述问题。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
