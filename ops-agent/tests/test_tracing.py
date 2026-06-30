import os

import pytest
from langsmith import utils as ls_utils

from app.config import Settings, get_settings
from app.observability.tracing import init_langsmith


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    ls_utils.get_env_var.cache_clear()
    get_settings.cache_clear()
    yield
    ls_utils.get_env_var.cache_clear()
    get_settings.cache_clear()


def test_langsmith_env_vars_enable_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "ops-agent")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    settings = Settings(_env_file=None)
    assert settings.langsmith_enabled is True

    init_langsmith(settings)
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "test-key"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert ls_utils.tracing_is_enabled() is True


def test_legacy_langchain_env_vars_still_work(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "legacy-key")

    settings = Settings(_env_file=None)
    assert settings.langsmith_enabled is True
    assert settings.langsmith_api_key == "legacy-key"

    init_langsmith(settings)
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGCHAIN_API_KEY"] == "legacy-key"


def test_disabled_tracing_clears_env(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)

    settings = Settings(_env_file=None)
    assert settings.langsmith_enabled is False

    init_langsmith(settings)
    assert "LANGSMITH_TRACING" not in os.environ
    assert "LANGCHAIN_TRACING_V2" not in os.environ
