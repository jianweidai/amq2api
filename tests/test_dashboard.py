"""
测试 Dashboard 页面和缓存统计功能
"""
import pytest
from pathlib import Path


def test_dashboard_html_exists():
    """测试 dashboard.html 文件是否存在"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    assert dashboard_path.exists(), "dashboard.html 文件不存在"
    
    # 验证文件不为空
    content = dashboard_path.read_text(encoding='utf-8')
    assert len(content) > 0, "dashboard.html 文件为空"
    assert "缓存统计" in content, "dashboard.html 缺少标题"
    assert "/v1/usage" in content, "dashboard.html 缺少 API 调用"


def test_dashboard_route_exists():
    """测试 /dashboard 路由是否存在于 main.py"""
    main_path = Path(__file__).parent.parent / "src" / "main.py"
    content = main_path.read_text(encoding='utf-8')
    
    assert '@app.get("/dashboard"' in content, "main.py 中缺少 /dashboard 路由"
    assert 'async def dashboard_page' in content, "main.py 中缺少 dashboard_page 函数"
    assert 'dashboard.html' in content, "dashboard_page 函数未返回 dashboard.html"


def test_admin_page_has_dashboard_link():
    """测试 admin 页面是否包含 dashboard 链接"""
    admin_path = Path(__file__).parent.parent / "frontend" / "index.html"
    content = admin_path.read_text(encoding='utf-8')
    
    assert '/dashboard' in content, "index.html 中缺少 dashboard 链接"
    assert '缓存统计' in content, "index.html 中缺少缓存统计链接文本"


def test_dashboard_html_structure():
    """测试 dashboard.html 的基本结构"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    content = dashboard_path.read_text(encoding='utf-8')
    
    # 检查必要的 HTML 元素
    assert '<!DOCTYPE html>' in content, "缺少 DOCTYPE 声明"
    assert '<html' in content, "缺少 html 标签"
    assert '<head>' in content, "缺少 head 标签"
    assert '<body>' in content, "缺少 body 标签"
    assert '<title>' in content, "缺少 title 标签"
    
    # 检查关键功能
    assert 'loadCacheStats' in content, "缺少 loadCacheStats 函数"
    assert 'displayStats' in content, "缺少 displayStats 函数"
    assert 'fetch(\'/v1/usage\')' in content, "缺少 API 调用"
    assert 'setInterval' in content, "缺少自动刷新功能"


def test_dashboard_styling():
    """测试 dashboard.html 是否包含样式"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    content = dashboard_path.read_text(encoding='utf-8')
    
    # 检查 CSS 变量
    assert ':root' in content, "缺少 CSS 变量定义"
    assert '--bg:' in content or '--bg :' in content, "缺少背景色变量"
    assert '--panel:' in content or '--panel :' in content, "缺少面板色变量"
    
    # 检查暗色模式支持
    assert 'prefers-color-scheme: dark' in content, "缺少暗色模式支持"
    
    # 检查关键样式类
    assert '.stat-card' in content, "缺少 stat-card 样式"
    assert '.panel' in content, "缺少 panel 样式"


def test_dashboard_back_button():
    """测试 dashboard 页面是否有返回按钮"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    content = dashboard_path.read_text(encoding='utf-8')
    
    assert '/admin' in content, "缺少返回 admin 页面的链接"
    assert '返回' in content or '← ' in content, "缺少返回按钮文本"


def test_dashboard_displays_cache_metrics():
    """测试 dashboard 是否显示所有关键缓存指标"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    content = dashboard_path.read_text(encoding='utf-8')
    
    # 检查关键指标
    metrics = [
        '命中率',
        '缓存条目',
        '内存使用',
        '驱逐次数',
        'TTL',
        '最大条目数',
    ]
    
    for metric in metrics:
        assert metric in content, f"缺少指标: {metric}"


def test_dashboard_error_handling():
    """测试 dashboard 是否有错误处理"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    content = dashboard_path.read_text(encoding='utf-8')
    
    assert 'displayError' in content, "缺少 displayError 函数"
    assert 'catch' in content, "缺少错误捕获"
    assert 'try' in content, "缺少 try-catch 块"


def test_dashboard_loading_state():
    """测试 dashboard 是否有加载状态"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    content = dashboard_path.read_text(encoding='utf-8')
    
    assert 'loading' in content.lower(), "缺少加载状态"
    assert 'spinner' in content.lower(), "缺少加载动画"


def test_dashboard_auto_refresh():
    """测试 dashboard 是否有自动刷新功能"""
    dashboard_path = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    content = dashboard_path.read_text(encoding='utf-8')
    
    assert 'setInterval' in content, "缺少自动刷新定时器"
    assert '5000' in content or '5秒' in content, "缺少刷新间隔配置"
    assert 'clearInterval' in content, "缺少清理定时器的代码"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
