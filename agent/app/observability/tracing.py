import logging
import os

from app.config import Settings

logger = logging.getLogger(__name__)

_TRACING_ENV_KEYS = (
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_PROJECT",
    "LANGCHAIN_ENDPOINT",
)


def _clear_tracing_env() -> None:
    for key in _TRACING_ENV_KEYS:
        os.environ.pop(key, None)


def init_langsmith(settings: Settings) -> None:
    """Enable LangSmith when configured; otherwise clear tracing env vars."""
    if not settings.langsmith_enabled:
        _clear_tracing_env()
        return

    api_key = settings.langsmith_api_key or ""
    project = settings.langsmith_project
    endpoint = settings.langsmith_endpoint

    # Official LangSmith env vars (preferred).
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGSMITH_ENDPOINT"] = endpoint

    # Legacy LangChain aliases still read by langchain_core callbacks.
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint

    logger.info("LangSmith tracing enabled for project=%s", project)
