"""Native Gemini model selection for the local Google ADK workflow."""

import os
from pathlib import Path

from dotenv import load_dotenv


# The ignored file is shared by ADK Web, FastAPI, and the Streamlit fallback.
load_dotenv(Path(__file__).resolve().parent.parent / 'travel_planner' / '.env',
            override=False)


def model_name() -> str:
    """Use a free-tier-compatible Gemini model without an Ollama adapter."""
    name = os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite').strip()
    if not name.startswith('gemini-'):
        raise ValueError('GEMINI_MODEL must be a Gemini model name')
    return name


def gemini_key_available() -> bool:
    """Check credentials without exposing them in logs or responses."""
    return bool(os.getenv('GOOGLE_API_KEY', '').strip())


def build_model() -> str:
    """ADK uses its native Gemini provider for a plain model name."""
    os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'FALSE'
    return model_name()
