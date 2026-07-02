"""Tests for LLM provider helpers (DashScope JSON hint compatibility)."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import Settings
from app.graph.decide_spec import DecideAssessment, DecideOutcome
from app.graph.eval_schemas import RunbookEvalLLMOutput
from app.llm.provider import (
    _invoke_plain_json_fallback,
    _is_deepseek_chat,
    _needs_dashscope_json_hint,
    _parse_schema_from_ai_text,
    ensure_json_in_messages,
    get_chat_model,
    invoke_structured,
    strip_json_markdown,
)


def test_needs_dashscope_json_hint_for_qwen_model():
    settings = Settings(
        openai_base_url="https://api.deepseek.com",
        openai_model="qwen3.7-plus",
    )
    assert _needs_dashscope_json_hint(settings) is True


def test_needs_dashscope_json_hint_for_dashscope_base_url():
    settings = Settings(
        openai_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        openai_model="gpt-4o",
    )
    assert _needs_dashscope_json_hint(settings) is True


def test_needs_dashscope_json_hint_for_other_providers():
    settings = Settings(
        openai_base_url="https://api.deepseek.com",
        openai_model="deepseek-v4-flash",
    )
    assert _needs_dashscope_json_hint(settings) is False


def test_is_deepseek_chat_by_base_url():
    settings = Settings(
        openai_base_url="https://api.deepseek.com",
        openai_model="deepseek-v4-flash",
    )
    assert _is_deepseek_chat(settings) is True


def test_is_deepseek_chat_by_model_name():
    settings = Settings(
        openai_base_url="https://api.openai.com/v1",
        openai_model="deepseek-v4-pro",
    )
    assert _is_deepseek_chat(settings) is True


def test_get_chat_model_deepseek_disables_thinking():
    settings = Settings(
        llm_mode="real",
        openai_api_key="sk-test",
        openai_base_url="https://api.deepseek.com",
        openai_model="deepseek-v4-flash",
    )
    with patch("app.llm.provider.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        get_chat_model(settings=settings)
        assert mock_cls.call_args.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_get_chat_model_non_deepseek_no_extra_body():
    settings = Settings(
        llm_mode="real",
        openai_api_key="sk-test",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o-mini",
        openai_model_strong="gpt-4o",
    )
    with patch("app.llm.provider.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        get_chat_model(settings=settings)
        assert "extra_body" not in mock_cls.call_args.kwargs


def test_invoke_structured_deepseek_adds_json_hint():
    settings = Settings(
        openai_base_url="https://api.deepseek.com",
        openai_model="deepseek-v4-flash",
    )
    llm = MagicMock()
    structured = MagicMock()
    llm.with_structured_output.return_value = structured
    structured.invoke.return_value = {
        "parsed": RunbookEvalLLMOutput(),
        "raw": None,
    }
    messages = [HumanMessage(content="Score this incident.")]
    invoke_structured(llm, RunbookEvalLLMOutput, messages, settings=settings)
    llm.with_structured_output.assert_called_once_with(
        RunbookEvalLLMOutput,
        method="json_mode",
        include_raw=True,
    )
    sent_messages = structured.invoke.call_args.args[0]
    assert "json" in sent_messages[0].content.lower()


def test_ensure_json_in_messages_appends_to_system_prompt():
    messages = [
        SystemMessage(content="You are an eval module."),
        HumanMessage(content="Score this incident."),
    ]
    updated = ensure_json_in_messages(messages)
    assert updated is not messages
    assert "json" in updated[0].content.lower()
    assert updated[1].content == messages[1].content


def test_ensure_json_in_messages_noop_when_json_present():
    messages = [
        SystemMessage(content="Return JSON with scores."),
        HumanMessage(content="Incident details."),
    ]
    updated = ensure_json_in_messages(messages)
    assert updated is messages


def test_ensure_json_in_messages_inserts_system_when_missing():
    messages = [HumanMessage(content="Only human content.")]
    updated = ensure_json_in_messages(messages)
    assert len(updated) == 2
    assert isinstance(updated[0], SystemMessage)
    assert "json" in updated[0].content.lower()


def test_parse_schema_from_ai_text_nested_rubrics():
    text = """{
      "rubrics": [{
        "doc_id": "ecomm-order-crashloop",
        "relevance": {"service_scope_match": 0.25, "symptom_match": 0.25},
        "coverage": {"root_cause_fit": 0.25}
      }]
    }"""
    output = _parse_schema_from_ai_text(RunbookEvalLLMOutput, text)
    assert output.rubrics[0].service_scope_match == 0.25
    assert output.rubrics[0].symptom_match == 0.25


def test_parse_schema_from_ai_text_bare_rubric_array():
    text = """[{
      "doc_id": "ecomm-cache-redis-memory-full",
      "relevance": {"service_scope_match": 0.25, "symptom_match": 0.25},
      "coverage": {"root_cause_fit": 0.25}
    }]"""
    output = _parse_schema_from_ai_text(RunbookEvalLLMOutput, text)
    assert len(output.rubrics) == 1
    assert output.rubrics[0].doc_id == "ecomm-cache-redis-memory-full"


def test_strip_json_markdown_removes_fence():
    fenced = """```json
{"outcome": "uncertain", "reasoning": "need logs"}
```"""
    assert strip_json_markdown(fenced).startswith("{")


def test_parse_schema_from_ai_text_decide_assessment_with_classification():
    text = """{
      "classification": "out_of_scope",
      "recommendations": "Escalate to dev team"
    }"""
    output = _parse_schema_from_ai_text(DecideAssessment, text)
    assert output.outcome == DecideOutcome.OUT_OF_SCOPE
    assert output.recommendations == ["Escalate to dev team"]
    assert output.reasoning == ""


def test_plain_json_fallback_binds_json_object():
    llm = MagicMock()
    bound = MagicMock()
    llm.bind.return_value = bound
    bound.invoke.return_value = AIMessage(content=(
        '{"classification": "uncertain", "reasoning": "ambiguous", "recommendations": []}'
    ))
    result = _invoke_plain_json_fallback(
        llm,
        DecideAssessment,
        [HumanMessage(content="Assess incident.")],
    )
    llm.bind.assert_called_once_with(response_format={"type": "json_object"})
    assert result.outcome == DecideOutcome.UNCERTAIN
