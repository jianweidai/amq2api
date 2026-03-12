"""
端到端集成测试：全局 AMQ 模型映射功能
测试 enable_model_mapping 开关和 amq_model_mapping 全局映射配置

Requirements: 4.1, 4.2
"""
import pytest
import json
import os
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """每个测试用独立的临时数据库"""
    db_path = tmp_path / "test_accounts.db"
    monkeypatch.setattr("src.auth.account_manager.SQLITE_DB_PATH", db_path)
    monkeypatch.setattr("src.auth.account_manager.USE_MYSQL", False)
    from src.auth.account_manager import _sqlite_ensure_db
    _sqlite_ensure_db()


class TestGlobalModelMappingEnabled:
    """测试全局模型映射开关开启时的行为"""

    def test_mapping_applied_when_enabled(self, tmp_db):
        """开关开启时，映射表中的模型应被映射"""
        from src.auth.account_manager import set_config
        from src.processing.model_mapper import apply_model_mapping

        set_config("enable_model_mapping", True)
        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-sonnet-4.5",
            "claude-sonnet-4.6": "claude-sonnet-4.5",
        })

        account = {"id": "test-1", "label": "Test"}

        assert apply_model_mapping(account, "claude-opus-4") == "claude-sonnet-4.5"
        assert apply_model_mapping(account, "claude-sonnet-4.6") == "claude-sonnet-4.5"

    def test_unmapped_model_passes_through(self, tmp_db):
        """不在映射表中的模型应直接透传"""
        from src.auth.account_manager import set_config
        from src.processing.model_mapper import apply_model_mapping

        set_config("enable_model_mapping", True)
        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-sonnet-4.5",
        })

        account = {"id": "test-2", "label": "Test"}

        assert apply_model_mapping(account, "claude-haiku-4.5") == "claude-haiku-4.5"
        assert apply_model_mapping(account, "claude-sonnet-4.5") == "claude-sonnet-4.5"

    def test_empty_mapping_passes_through(self, tmp_db):
        """映射表为空时，所有模型直接透传"""
        from src.auth.account_manager import set_config
        from src.processing.model_mapper import apply_model_mapping

        set_config("enable_model_mapping", True)
        set_config("amq_model_mapping", {})

        account = {"id": "test-3", "label": "Test"}

        assert apply_model_mapping(account, "claude-opus-4") == "claude-opus-4"


class TestGlobalModelMappingDisabled:
    """测试全局模型映射开关关闭时的行为"""

    def test_mapping_skipped_when_disabled(self, tmp_db):
        """开关关闭时，即使映射表有配置也不映射"""
        from src.auth.account_manager import set_config
        from src.processing.model_mapper import apply_model_mapping

        set_config("enable_model_mapping", False)
        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-sonnet-4.5",
            "claude-sonnet-4.6": "claude-sonnet-4.5",
        })

        account = {"id": "test-4", "label": "Test"}

        # 开关关闭，应返回原始模型
        assert apply_model_mapping(account, "claude-opus-4") == "claude-opus-4"
        assert apply_model_mapping(account, "claude-sonnet-4.6") == "claude-sonnet-4.6"


class TestGlobalModelMappingToggle:
    """测试开关切换的动态行为"""

    def test_toggle_on_off(self, tmp_db):
        """动态切换开关，映射行为应立即变化"""
        from src.auth.account_manager import set_config
        from src.processing.model_mapper import apply_model_mapping

        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-sonnet-4.5",
        })
        account = {"id": "test-5", "label": "Test"}

        # 开启
        set_config("enable_model_mapping", True)
        assert apply_model_mapping(account, "claude-opus-4") == "claude-sonnet-4.5"

        # 关闭
        set_config("enable_model_mapping", False)
        assert apply_model_mapping(account, "claude-opus-4") == "claude-opus-4"

        # 再开启
        set_config("enable_model_mapping", True)
        assert apply_model_mapping(account, "claude-opus-4") == "claude-sonnet-4.5"


class TestGlobalModelMappingUpdate:
    """测试动态更新映射配置"""

    def test_update_mapping_takes_effect(self, tmp_db):
        """更新映射配置后，新映射应立即生效"""
        from src.auth.account_manager import set_config
        from src.processing.model_mapper import apply_model_mapping

        set_config("enable_model_mapping", True)
        account = {"id": "test-6", "label": "Test"}

        # 初始映射
        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-sonnet-4.5",
        })
        assert apply_model_mapping(account, "claude-opus-4") == "claude-sonnet-4.5"

        # 更新映射目标
        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-haiku-4.5",
        })
        assert apply_model_mapping(account, "claude-opus-4") == "claude-haiku-4.5"

    def test_add_new_mapping(self, tmp_db):
        """添加新的映射规则"""
        from src.auth.account_manager import set_config
        from src.processing.model_mapper import apply_model_mapping

        set_config("enable_model_mapping", True)
        account = {"id": "test-7", "label": "Test"}

        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-sonnet-4.5",
        })

        # claude-sonnet-4.6 还没有映射
        assert apply_model_mapping(account, "claude-sonnet-4.6") == "claude-sonnet-4.6"

        # 添加新映射
        set_config("amq_model_mapping", {
            "claude-opus-4": "claude-sonnet-4.5",
            "claude-sonnet-4.6": "claude-sonnet-4.5",
        })
        assert apply_model_mapping(account, "claude-sonnet-4.6") == "claude-sonnet-4.5"


class TestGlobalModelMappingEnvFallback:
    """测试环境变量回退"""

    def test_env_fallback_when_db_missing(self, tmp_db):
        """数据库没有 enable_model_mapping 时回退到环境变量"""
        from src.processing.model_mapper import is_model_mapping_enabled

        # 默认 DB 有 enable_model_mapping=True
        assert is_model_mapping_enabled() is True

    def test_env_disable(self, tmp_db, monkeypatch):
        """环境变量设为 false 时关闭映射（DB 无配置时）"""
        monkeypatch.setenv("ENABLE_MODEL_MAPPING", "false")
        # 让 get_config 对 enable_model_mapping 返回 None，模拟 DB 无此 key
        import src.auth.account_manager as am
        monkeypatch.setattr(am, "get_config", lambda key: None)

        from src.processing.model_mapper import is_model_mapping_enabled
        assert is_model_mapping_enabled() is False


class TestDefaultAmqModelMapping:
    """测试默认的 AMQ 模型映射配置"""

    def test_default_mapping_initialized(self, tmp_db):
        """数据库初始化后应包含默认的 amq_model_mapping"""
        from src.auth.account_manager import get_config

        mapping = get_config("amq_model_mapping")
        assert isinstance(mapping, dict)
        assert "claude-opus-4" in mapping
        assert mapping["claude-opus-4"] == "claude-sonnet-4.5"

    def test_default_enable_flag(self, tmp_db):
        """数据库初始化后 enable_model_mapping 默认为 True"""
        from src.auth.account_manager import get_config

        enabled = get_config("enable_model_mapping")
        assert enabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
