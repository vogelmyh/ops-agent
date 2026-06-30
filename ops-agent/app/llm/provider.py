from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings


class MockChatModel(BaseChatModel):
    """Deterministic mock model for offline tests and demos."""

    @property
    def _llm_type(self) -> str:
        return "mock-chat"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = "Mock analysis: inspect logs, metrics, and runbooks for grounding."
        if messages:
            last = messages[-1].content
            if isinstance(last, str) and "ecomm-order" in last:
                text = "Root cause likely bad image upgrade causing CrashLoopBackOff."
            elif isinstance(last, str) and "ecomm-manager" in last:
                if "CrashLoop" in last or "镜像" in last:
                    text = "Root cause likely bad image upgrade causing CrashLoopBackOff."
                else:
                    text = "Root cause likely rate limit or config misconfiguration."
            elif isinstance(last, str) and (
                "stream" in last.lower() or "order-events" in last
            ):
                text = "Root cause likely paused order event stream blocking inventory sync."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def bind_tools(self, tools: list, **kwargs: Any) -> "MockChatModel":
        return self


def get_chat_model(*, strong: bool = False, settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    if settings.llm_is_mock:
        return MockChatModel()
    model = settings.openai_model_strong if strong else settings.openai_model
    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )
