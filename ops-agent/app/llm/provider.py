from typing import Any, TypeVar

import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)

_JSON_OUTPUT_HINT = "\n\nRespond with a valid JSON object matching the required schema."


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


def _needs_dashscope_json_hint(settings: Settings) -> bool:
    base = (settings.openai_base_url or "").lower()
    model = (settings.openai_model or "").lower()
    return "dashscope" in base or "aliyuncs.com" in base or model.startswith("qwen")


def _message_content_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", "")))
        return " ".join(parts)
    return str(content)


def _messages_contain_json(messages: list[BaseMessage]) -> bool:
    combined = " ".join(_message_content_text(m).lower() for m in messages)
    return "json" in combined


def ensure_json_in_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """DashScope qwen3.x requires 'json' in messages when using json_object response_format."""
    if _messages_contain_json(messages):
        return messages
    out = list(messages)
    for i, message in enumerate(out):
        if isinstance(message, SystemMessage):
            out[i] = SystemMessage(content=_message_content_text(message) + _JSON_OUTPUT_HINT)
            return out
    out.insert(0, SystemMessage(content=_JSON_OUTPUT_HINT.strip()))
    return out


def _ai_message_text(message: AIMessage) -> str:
    return _message_content_text(message).strip()


def _parse_schema_from_ai_text(schema: type[T], text: str) -> T:
    payload = json.loads(text)
    return schema.model_validate(payload)


def invoke_structured(
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    *,
    settings: Settings | None = None,
    **kwargs: Any,
) -> T:
    """Invoke LLM with structured output; inject JSON hint for DashScope/Qwen compatibility."""
    settings = settings or get_settings()
    if _needs_dashscope_json_hint(settings):
        messages = ensure_json_in_messages(messages)
        structured = llm.with_structured_output(schema, include_raw=True, **kwargs)
        result = structured.invoke(messages)
        parsed = result.get("parsed")
        if parsed is not None:
            if isinstance(parsed, schema):
                return parsed
            return schema.model_validate(parsed)

        raw = result.get("raw")
        if isinstance(raw, AIMessage):
            text = _ai_message_text(raw)
            if text:
                try:
                    return _parse_schema_from_ai_text(schema, text)
                except (json.JSONDecodeError, ValueError):
                    pass

        parsing_error = result.get("parsing_error")
        if parsing_error is not None:
            raise parsing_error
        msg = "Structured output missing parsed payload and text JSON fallback failed"
        raise ValueError(msg)

    return llm.with_structured_output(schema, **kwargs).invoke(messages)
