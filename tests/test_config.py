import os

import pytest
import sys
from types import ModuleType

from travel_core.config import build_model, model_api_base, model_name


def test_model_defaults_to_local_ollama(monkeypatch):
    monkeypatch.delenv('MODEL', raising=False)
    assert model_name() == 'ollama_chat/qwen3:8b'


def test_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv('MODEL', 'ollama_chat/qwen3:4b')
    assert model_name() == 'ollama_chat/qwen3:4b'


def test_disallow_cloud_model_values(monkeypatch):
    monkeypatch.setenv('MODEL', 'gemini-2.5-flash')
    with pytest.raises(ValueError):
        model_name()


def test_local_base_default(monkeypatch):
    monkeypatch.delenv('OLLAMA_API_BASE', raising=False)
    assert model_api_base() == 'http://localhost:11434'


def test_local_base_can_be_overridden(monkeypatch):
    monkeypatch.setenv('OLLAMA_API_BASE', 'http://127.0.0.1:11435/')
    assert model_api_base() == 'http://127.0.0.1:11435'


@pytest.mark.parametrize('value', ['https://localhost:11434', 'http://example.com:11434',
                                   'http://localhost:11434/v1', ''])
def test_reject_nonlocal_or_invalid_base(monkeypatch, value):
    monkeypatch.setenv('OLLAMA_API_BASE', value)
    with pytest.raises(ValueError):
        model_api_base()


def test_build_model_uses_adk_litellm_and_local_endpoint(monkeypatch):
    calls = []
    class FakeLiteLlm:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    # Keep this an offline unit test: only the ADK adapter import is substituted.
    module = ModuleType('google.adk.models.lite_llm')
    module.LiteLlm = FakeLiteLlm
    monkeypatch.setitem(sys.modules, 'google.adk.models.lite_llm', module)
    monkeypatch.setenv('MODEL', 'ollama_chat/qwen3:8b')
    monkeypatch.setenv('OLLAMA_API_BASE', 'http://127.0.0.1:11435')
    monkeypatch.delenv('LITELLM_LOCAL_MODEL_COST_MAP', raising=False)

    assert isinstance(build_model(), FakeLiteLlm)
    assert calls == [{'model': 'ollama_chat/qwen3:8b', 'api_base': 'http://127.0.0.1:11435'}]
    assert os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] == 'True'
