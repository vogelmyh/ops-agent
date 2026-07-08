from typing import Any, TypeVar

import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)

_JSON_OUTPUT_HINT = "\n\nRespond with a valid JSON object matching the required schema."
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


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


def _is_deepseek_model(model: str) -> bool:
    return (model or "").lower().startswith("deepseek")


def _is_deepseek_chat(settings: Settings, *, model: str | None = None) -> bool:
    """True when chat targets DeepSeek (by base URL or model id)."""
    base = (settings.openai_base_url or "").lower()
    if "deepseek" in base:
        return True
    if model is not None:
        return _is_deepseek_model(model)
    return _is_deepseek_model(settings.openai_model) or _is_deepseek_model(
        settings.openai_model_strong
    )


def get_chat_model(*, strong: bool = False, settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    if settings.llm_is_mock:
        return MockChatModel()
    model = settings.openai_model_strong if strong else settings.openai_model
    chat_kwargs: dict[str, Any] = {
        "model": model,
        "api_key": settings.openai_api_key,
        "base_url": settings.openai_base_url,
        "temperature": 0,
    }
    if _is_deepseek_chat(settings, model=model):
        chat_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**chat_kwargs)


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
    """Ensure 'json' appears in messages for json_object response_format (DashScope / DeepSeek)."""
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


def strip_json_markdown(text: str) -> str:
    """Remove optional ```json fences before json.loads."""
    stripped = text.strip()
    match = _JSON_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _parse_schema_from_ai_text(schema: type[T], text: str) -> T:
    cleaned = strip_json_markdown(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        msg = f"LLM output is not valid JSON for {schema.__name__}"
        raise ValueError(msg) from exc
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        msg = f"LLM JSON failed schema validation for {schema.__name__}"
        raise ValueError(msg) from exc


def _parse_schema_from_ai_message(schema: type[T], message: AIMessage) -> T | None:
    parsed = message.additional_kwargs.get("parsed")
    if parsed is not None:
        try:
            return schema.model_validate(parsed)
        except ValidationError:
            pass

    text = _ai_message_text(message)
    if not text:
        return None
    try:
        return _parse_schema_from_ai_text(schema, text)
    except ValueError:
        return None


def _invoke_plain_json_fallback(
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
) -> T:
    """Retry with json_object response_format when SDK structured parse fails."""
    json_llm = llm.bind(response_format={"type": "json_object"})
    response = json_llm.invoke(messages)
    if not isinstance(response, AIMessage):
        msg = "Plain JSON fallback did not receive an AIMessage"
        raise ValueError(msg)

    json_error: ValueError | None = None
    schema_error: ValueError | None = None
    try:
        return _parse_schema_from_ai_text(schema, _ai_message_text(response))
    except ValueError as exc:
        if "not valid JSON" in str(exc):
            json_error = exc
        else:
            schema_error = exc

    if schema_error is not None:
        raise schema_error
    msg = "Plain JSON fallback could not parse structured output from AIMessage"
    raise ValueError(msg) from json_error


def _resolve_structured_invoke_result(
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    result: dict[str, Any],
) -> T:
    parsed = result.get("parsed")
    if parsed is not None:
        if isinstance(parsed, schema):
            return parsed
        return schema.model_validate(parsed)

    raw = result.get("raw")
    if isinstance(raw, AIMessage):
        from_text = _parse_schema_from_ai_message(schema, raw)
        if from_text is not None:
            return from_text

    if result.get("parsing_error") is not None:
        return _invoke_plain_json_fallback(llm, schema, messages)

    return _invoke_plain_json_fallback(llm, schema, messages)


def _invoke_dashscope_structured(
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    **kwargs: Any,
) -> T:
    structured = llm.with_structured_output(schema, include_raw=True, **kwargs)
    try:
        result = structured.invoke(messages)
    except ValidationError:
        return _invoke_plain_json_fallback(llm, schema, messages)

    return _resolve_structured_invoke_result(llm, schema, messages, result)


def _invoke_deepseek_structured(
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    **kwargs: Any,
) -> T:
    """DeepSeek V4: use json_object mode (json_schema response_format unavailable)."""
    structured = llm.with_structured_output(
        schema,
        method="json_mode",
        include_raw=True,
        **kwargs,
    )
    try:
        result = structured.invoke(messages)
    except ValidationError:
        return _invoke_plain_json_fallback(llm, schema, messages)

    return _resolve_structured_invoke_result(llm, schema, messages, result)


def invoke_structured(
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    *,
    settings: Settings | None = None,
    **kwargs: Any,
) -> T:
    """Invoke LLM with structured output; provider-specific JSON hints and fallbacks."""
    settings = settings or get_settings()
    if _needs_dashscope_json_hint(settings):
        messages = ensure_json_in_messages(messages)
        return _invoke_dashscope_structured(llm, schema, messages, **kwargs)

    if _is_deepseek_chat(settings):
        messages = ensure_json_in_messages(messages)
        return _invoke_deepseek_structured(llm, schema, messages, **kwargs)

    return llm.with_structured_output(schema, **kwargs).invoke(messages)
