"""
测试 GET /v1/models 端点
"""
import pytest
from unittest.mock import patch


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("src.auth.account_manager.SQLITE_DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("src.auth.account_manager.USE_MYSQL", False)
    from src.auth.account_manager import _sqlite_ensure_db
    _sqlite_ensure_db()

    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)


def test_list_models_returns_openai_format(client):
    """应返回 OpenAI 兼容的 list 格式"""
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


def test_list_models_each_item_has_required_fields(client):
    """每个模型条目应有 id / object / created / owned_by"""
    resp = client.get("/v1/models")
    for item in resp.json()["data"]:
        assert "id" in item
        assert item["object"] == "model"
        assert "created" in item
        assert item["owned_by"] in ("amazon-q", "gemini")


def test_list_models_amazonq_only_tagged_correctly(client):
    """amazonq_only_models 中的模型 owned_by 应为 amazon-q"""
    from src.auth.account_manager import set_config
    set_config("amazonq_only_models", ["my-amazonq-exclusive"])
    set_config("supported_models", ["my-gemini-model"])

    resp = client.get("/v1/models")
    data = {item["id"]: item for item in resp.json()["data"]}

    assert data["my-amazonq-exclusive"]["owned_by"] == "amazon-q"
    assert data["my-gemini-model"]["owned_by"] == "gemini"


def test_list_models_no_duplicates(client):
    """模型列表不应有重复"""
    from src.auth.account_manager import set_config
    set_config("amazonq_only_models", ["model-a"])
    set_config("supported_models", ["model-a", "model-b"])  # model-a 重复

    resp = client.get("/v1/models")
    ids = [item["id"] for item in resp.json()["data"]]
    assert len(ids) == len(set(ids))
