import os

import pytest

from travel_core.config import build_model, gemini_key_available, model_name


def test_native_gemini_default_ignores_old_ollama_setting(monkeypatch):
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    monkeypatch.setenv('MODEL', 'ollama_chat/llama3.2:3b')
    assert model_name() == 'gemini-3.1-flash-lite'


def test_gemini_model_can_be_configured(monkeypatch):
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-2.5-flash')
    assert model_name() == 'gemini-2.5-flash'
    monkeypatch.setenv('GEMINI_MODEL', 'ollama_chat/qwen3:8b')
    with pytest.raises(ValueError):
        model_name()


def test_build_model_uses_native_adk_and_disables_vertex(monkeypatch):
    monkeypatch.setenv('GOOGLE_GENAI_USE_VERTEXAI', 'TRUE')
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    assert build_model() == 'gemini-3.1-flash-lite'
    assert os.environ['GOOGLE_GENAI_USE_VERTEXAI'] == 'FALSE'


def test_missing_key_can_be_detected_without_printing_it(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    assert gemini_key_available() is False
    monkeypatch.setenv('GOOGLE_API_KEY', 'test-key')
    assert gemini_key_available() is True
