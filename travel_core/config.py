"""Model selection for Google ADK. No cloud API key is required."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

# ADK web discovers travel_planner/.env; loading it here also supports Streamlit.
load_dotenv(Path(__file__).resolve().parent.parent / 'travel_planner' / '.env', override=False)


def model_name() -> str:
    """Return an Ollama model identifier supported by the LiteLLM ADK adapter."""
    value = os.getenv('MODEL', 'ollama_chat/qwen3:8b').strip()
    if not value.startswith('ollama_chat/') or value == 'ollama_chat/':
        raise ValueError('MODEL must use ollama_chat/<model>, e.g. ollama_chat/qwen3:8b')
    return value


def model_api_base() -> str:
    """Ollama endpoint (normally local to the user's computer)."""
    value = os.getenv('OLLAMA_API_BASE', 'http://localhost:11434').strip().rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}
            or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password
            or not parsed.port):
        raise ValueError('OLLAMA_API_BASE must be a local HTTP URL such as http://localhost:11434')
    return value


def build_model():
    """Create the ADK-compatible model lazily (offline tests do not need ADK)."""
    # LiteLLM otherwise tries to fetch a remote price map at startup.
    os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
    from google.adk.models.lite_llm import LiteLlm

    api_base = model_api_base()
    os.environ['OLLAMA_API_BASE'] = api_base
    return LiteLlm(model=model_name(), api_base=api_base)
