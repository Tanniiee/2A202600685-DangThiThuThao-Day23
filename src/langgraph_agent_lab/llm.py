"""LLM factory helper with optional LangSmith tracing.

Automatically loads .env from the project root (python-dotenv).

LangSmith tracing activates when:
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=lsv2_...
    LANGCHAIN_PROJECT=day08-langgraph-lab

Usage:
    from .llm import get_llm
    llm = get_llm()
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env from the project root (two levels above this file's src/ dir)."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass  # python-dotenv not installed -- rely on env vars set externally


def _configure_langsmith() -> None:
    """Enable LangSmith tracing if credentials are present."""
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower()
    if api_key and tracing == "true":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = api_key
        project = os.getenv("LANGCHAIN_PROJECT", "day08-langgraph-lab")
        os.environ["LANGCHAIN_PROJECT"] = project


def get_llm(model: str | None = None, temperature: float = 0.0):
    """Create an LLM client from environment configuration.

    Key priority: OPENAI_API_KEY -> GEMINI_API_KEY -> ANTHROPIC_API_KEY
    .env is loaded automatically from the project root.
    """
    _load_dotenv()
    _configure_langsmith()

    if os.getenv("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("Run: pip install langchain-openai") from exc
        return ChatOpenAI(
            model=model or os.getenv("LLM_MODEL", "gpt-4o-mini"),
            temperature=temperature,
        )

    if os.getenv("GEMINI_API_KEY"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("Run: pip install langchain-google-genai") from exc
        return ChatGoogleGenerativeAI(
            model=model or os.getenv("LLM_MODEL", "gemini-2.5-flash"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=temperature,
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("Run: pip install langchain-anthropic") from exc
        return ChatAnthropic(
            model=model or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
            temperature=temperature,
        )

    raise RuntimeError(
        "No LLM API key found.\n"
        "Open the .env file in your project folder and set:\n"
        "  OPENAI_API_KEY=sk-...      (recommended)\n"
        "  or GEMINI_API_KEY=AIza...\n"
        "  or ANTHROPIC_API_KEY=sk-ant-...\n"
        "See .env.example for the full template."
    )
