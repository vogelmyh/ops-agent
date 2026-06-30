"""Tests for LLM provider helpers (DashScope JSON hint compatibility)."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.graph.eval_schemas import RunbookEvalLLMOutput
from app.llm.provider import (
    _needs_dashscope_json_hint,
    _parse_schema_from_ai_text,
    ensure_json_in_messages,
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
    assert output.rubrics[0].root_cause_fit == 0.25


def test_parse_schema_from_ai_text_bare_rubric_array():
    text = """[{
      "doc_id": "ecomm-cache-redis-memory-full",
      "relevance": {"service_scope_match": 0.25, "symptom_match": 0.25},
      "coverage": {"root_cause_fit": 0.25}
    }]"""
    output = _parse_schema_from_ai_text(RunbookEvalLLMOutput, text)
    assert len(output.rubrics) == 1
    assert output.rubrics[0].doc_id == "ecomm-cache-redis-memory-full"
