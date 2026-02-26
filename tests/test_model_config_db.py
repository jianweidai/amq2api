"""
测试模型配置数据库化：
1. get_config / set_config / get_all_config 基本 CRUD
2. 默认配置自动初始化
3. get_random_channel_by_model 从数据库读取分类
4. map_claude_model_to_gemini 从数据库读取映射
5. GET/PUT /v2/config 端点
"""
import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import patch


# ── 辅助：创建临时 SQLite 数据库 ─────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """每个测试用独立的临时数据库，避免互相污染"""
    db_path = tmp_path / "test_accounts.db"
    monkeypatch.setattr("src.auth.account_manager.SQLITE_DB_PATH", db_path)
    monkeypatch.setattr("src.auth.account_manager.USE_MYSQL", False)
    # 重新初始化数据库
    from src.auth.account_manager import _sqlite_ensure_db
    _sqlite_ensure_db()
    return db_path


# ── 1. get_config / set_config / get_all_config ───────────────────────────────

def test_get_config_returns_default(tmp_db):
    """默认配置应该在初始化时自动写入"""
    from src.auth.account_manager import get_config
    val = get_config("gemini_only_models")
    assert isinstance(val, list)
    assert len(val) > 0


def test_set_and_get_config(tmp_db):
    """set_config 写入后 get_config 应能读回"""
    from src.auth.account_manager import set_config, get_config
    set_config("supported_models", ["model-a", "model-b"])
    result = get_config("supported_models")
    assert result == ["model-a", "model-b"]


def test_set_config_overwrites(tmp_db):
    """set_config 应覆盖已有值"""
    from src.auth.account_manager import set_config, get_config
    set_config("model_mapping", {"old": "value"})
    set_config("model_mapping", {"new": "value"})
    result = get_config("model_mapping")
    assert result == {"new": "value"}


def test_get_config_missing_key_returns_none(tmp_db):
    """不存在的 key 应返回 None"""
    from src.auth.account_manager import get_config
    assert get_config("nonexistent_key_xyz") is None


def test_get_all_config_returns_dict(tmp_db):
    """get_all_config 应返回包含所有默认配置的字典"""
    from src.auth.account_manager import get_all_config
    config = get_all_config()
    assert isinstance(config, dict)
    assert "gemini_only_models" in config
    assert "amazonq_only_models" in config
    assert "supported_models" in config
    assert "model_mapping" in config


def test_default_config_not_overwritten_on_reinit(tmp_db):
    """重复初始化不应覆盖已有配置"""
    from src.auth.account_manager import set_config, get_config, _sqlite_ensure_db
    set_config("supported_models", ["custom-model"])
    _sqlite_ensure_db()  # 再次初始化
    result = get_config("supported_models")
    assert result == ["custom-model"]  # 不应被默认值覆盖


# ── 2. get_random_channel_by_model 从数据库读取 ───────────────────────────────

def test_channel_routing_gemini_only_from_db(tmp_db):
    """gemini_only_models 配置的模型应路由到 gemini"""
    from src.auth.account_manager import set_config, create_account, get_random_channel_by_model

    set_config("gemini_only_models", ["my-thinking-model"])
    set_config("amazonq_only_models", [])

    create_account(
        label="test-gemini",
        client_id="cid", client_secret="cs", refresh_token="rt",
        account_type="gemini"
    )

    channel = get_random_channel_by_model("my-thinking-model")
    assert channel == "gemini"


def test_channel_routing_amazonq_only_from_db(tmp_db):
    """amazonq_only_models 配置的模型应路由到 amazonq"""
    from src.auth.account_manager import set_config, create_account, get_random_channel_by_model

    set_config("gemini_only_models", [])
    set_config("amazonq_only_models", ["my-amazonq-model"])

    create_account(
        label="test-amazonq",
        client_id="cid", client_secret="cs", refresh_token="rt",
        account_type="amazonq"
    )

    channel = get_random_channel_by_model("my-amazonq-model")
    assert channel == "amazonq"


# ── 3. map_claude_model_to_gemini 从数据库读取 ────────────────────────────────

def test_map_model_uses_db_supported_models(tmp_db):
    """supported_models 中的模型应直接透传"""
    from src.auth.account_manager import set_config
    from src.gemini.converter import map_claude_model_to_gemini

    set_config("supported_models", ["my-custom-gemini-model"])
    set_config("model_mapping", {})

    result = map_claude_model_to_gemini("my-custom-gemini-model")
    assert result == "my-custom-gemini-model"


def test_map_model_uses_db_model_mapping(tmp_db):
    """model_mapping 中的映射应生效"""
    from src.auth.account_manager import set_config
    from src.gemini.converter import map_claude_model_to_gemini

    set_config("supported_models", [])
    set_config("model_mapping", {"claude-test-model": "gemini-target-model"})

    result = map_claude_model_to_gemini("claude-test-model")
    assert result == "gemini-target-model"


def test_map_model_fallback_when_not_in_db(tmp_db):
    """未知模型应回退到默认值"""
    from src.auth.account_manager import set_config
    from src.gemini.converter import map_claude_model_to_gemini

    set_config("supported_models", [])
    set_config("model_mapping", {})

    result = map_claude_model_to_gemini("unknown-model-xyz")
    assert result == "claude-sonnet-4-5"  # 默认回退值


# ── 4. /v2/config 端点 ────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_db):
    from fastapi.testclient import TestClient
    # 绕过 admin 认证
    from src.main import app, verify_admin_key
    app.dependency_overrides[verify_admin_key] = lambda: True
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_config_endpoint(client):
    """GET /v2/config 应返回所有配置"""
    resp = client.get("/v2/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "gemini_only_models" in data
    assert "model_mapping" in data


def test_put_config_endpoint(client):
    """PUT /v2/config 应更新指定配置项"""
    resp = client.put("/v2/config", json={
        "supported_models": ["model-x", "model-y"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "supported_models" in data["updated"]
    assert data["config"]["supported_models"] == ["model-x", "model-y"]


def test_put_config_rejects_unknown_key(client):
    """PUT /v2/config 不允许写入未知配置项"""
    resp = client.put("/v2/config", json={"unknown_key": "value"})
    assert resp.status_code == 400
