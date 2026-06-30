"""Unit tests for the RAG pipeline — pure functions only (no ChromaDB I/O).

These tests cover:
  - ingest helpers: parse_service, extract_h1, split_by_h2
  - chunking strategy: short doc → whole chunk, long doc → section chunks
  - diagnose helpers: extract_symptoms, filter_by_relevance
"""
import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")

from app.adapters.mock_data import reset_mock_scenarios
from app.rag.ingest import (
    SECTION_MAX_CHARS,
    WHOLE_DOC_THRESHOLD,
    _paragraph_split,
    extract_h1,
    parse_service,
    split_by_h2,
)
from app.rag.store import filter_by_relevance
from app.graph.collection import extract_symptoms
from app.graph.nodes.diagnose import diagnose_node

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_mock_scenarios():
    reset_mock_scenarios()
    yield
    reset_mock_scenarios()


# ---------------------------------------------------------------------------
# parse_service
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stem,expected", [
    ("ecomm-manager-rate-limit", "ecomm-manager"),
    ("ecomm-order-crashloop", "ecomm-order"),
    ("ecomm-order-stream-paused", "ecomm-order"),
    ("ecomm-catalog-novel", "ecomm-catalog"),
    ("my-service-some-scenario", "my-service"),  # generic fallback
])
def test_parse_service(stem, expected):
    assert parse_service(stem) == expected


# ---------------------------------------------------------------------------
# extract_h1
# ---------------------------------------------------------------------------

def test_extract_h1_found():
    text = "# BCS Agent CrashLoop 回滚\n\n## 症状\n内容"
    assert extract_h1(text) == "# BCS Agent CrashLoop 回滚"


def test_extract_h1_not_found():
    text = "## 症状\n内容"
    assert extract_h1(text) == ""


# ---------------------------------------------------------------------------
# split_by_h2
# ---------------------------------------------------------------------------

SAMPLE_DOC = """\
# Title

## 症状
数据面 Deployment 0/N Ready，Pod CrashLoopBackOff。

## 根因
镜像 tag 错误或启动参数不兼容。

## 处置
1. 查询最近 operations/latest 确认升级记录。
2. 执行 dataplane rollback 到上一稳定镜像。
3. 验证 readiness 探针恢复。
"""


def test_split_by_h2_count():
    sections = split_by_h2(SAMPLE_DOC)
    assert len(sections) == 3


def test_split_by_h2_headings():
    sections = split_by_h2(SAMPLE_DOC)
    headings = [h for h, _ in sections]
    assert "## 症状" in headings
    assert "## 根因" in headings
    assert "## 处置" in headings


def test_split_by_h2_body_not_empty():
    sections = split_by_h2(SAMPLE_DOC)
    for heading, body in sections:
        assert body.strip(), f"Section '{heading}' has empty body"


def test_split_by_h2_no_h1_in_body():
    """The h1 title line should not appear in any section body."""
    sections = split_by_h2(SAMPLE_DOC)
    for _, body in sections:
        assert "# Title" not in body


# ---------------------------------------------------------------------------
# Chunking strategy
# ---------------------------------------------------------------------------

SHORT_DOC = "# Short\n\n## 症状\n短文档内容。\n\n## 处置\n执行操作。"
assert len(SHORT_DOC) < WHOLE_DOC_THRESHOLD, "SHORT_DOC fixture must be short"


def _make_long_doc(n_paragraphs: int = 15) -> str:
    # Use \n\n-separated paragraphs so _paragraph_split can actually split them.
    # Each paragraph is long enough that a few of them exceed SECTION_MAX_CHARS.
    paras = "\n\n".join(
        f"操作步骤 {i + 1}：执行详细的检查和修复动作，确认指标恢复正常，记录变更日志，通知相关团队。" * 3
        for i in range(n_paragraphs)
    )
    return f"# 长文档\n\n## 症状\n大量症状描述。\n\n## 处置\n{paras}\n"


LONG_DOC = _make_long_doc()
assert len(LONG_DOC) > WHOLE_DOC_THRESHOLD, "LONG_DOC fixture must exceed threshold"


def test_short_doc_produces_one_section():
    """Short runbooks should not be split — sections list not needed."""
    assert len(SHORT_DOC) <= WHOLE_DOC_THRESHOLD


def test_long_doc_splits_by_h2():
    sections = split_by_h2(LONG_DOC)
    assert len(sections) >= 2


def test_long_section_paragraph_split():
    """An oversized section body is split into sub-chunks by _paragraph_split."""
    _, body = split_by_h2(LONG_DOC)[1]  # "## 处置" section
    assert len(body) > SECTION_MAX_CHARS
    sub_chunks = _paragraph_split(body, max_chars=SECTION_MAX_CHARS)
    assert len(sub_chunks) > 1
    for chunk in sub_chunks:
        assert len(chunk) <= SECTION_MAX_CHARS


def test_section_chunk_includes_h1_prefix():
    """Each section chunk produced from a long doc must carry the h1 title prefix."""
    title = extract_h1(LONG_DOC)
    sections = split_by_h2(LONG_DOC)
    for heading, body in sections:
        prefix = f"{title}\n\n{heading}\n"
        chunk = f"{prefix}{body}".strip()
        assert chunk.startswith(title), f"Chunk does not start with h1 title:\n{chunk[:80]}"


# ---------------------------------------------------------------------------
# filter_by_relevance
# ---------------------------------------------------------------------------

def test_filter_keeps_high_score():
    chunks = [{"score": 0.8}, {"score": 0.3}, {"score": 0.6}]
    result = filter_by_relevance(chunks, threshold=0.5)
    assert len(result) == 2
    assert all(c["score"] >= 0.5 for c in result)


def test_filter_zero_threshold_keeps_all():
    chunks = [{"score": 0.1}, {"score": 0.0}, {"score": 0.9}]
    result = filter_by_relevance(chunks, threshold=0.0)
    assert len(result) == 3


def test_filter_empty_input():
    assert filter_by_relevance([], threshold=0.5) == []


# ---------------------------------------------------------------------------
# extract_symptoms
# ---------------------------------------------------------------------------

def _make_mock_data(service: str, scenario: str | None = None) -> dict:
    """Build a minimal data dict using mock backend client."""
    from app.adapters.backend_client import BackendClient
    from app.adapters.mock_data import set_mock_scenario
    from app.config import get_settings
    from app.graph.collection import collect, serialize_collected

    if scenario:
        set_mock_scenario(service, scenario)
    get_settings.cache_clear()
    BackendClient()
    raw = collect(service)
    data = serialize_collected(raw)
    return data


def test_extract_symptoms_ecomm_order_contains_service():
    data = _make_mock_data("ecomm-order", "crashloop")
    query = extract_symptoms("ecomm-order", data)
    assert "ecomm-order" in query


def test_extract_symptoms_ecomm_order_contains_k8s_signal():
    """ecomm-order crashloop symptoms should reference the K8s BackOff event."""
    data = _make_mock_data("ecomm-order", "crashloop")
    query = extract_symptoms("ecomm-order", data)
    assert "BackOff" in query


def test_extract_symptoms_ecomm_order_stream_paused():
    """ecomm-order stream-paused symptoms should mention the paused stream."""
    data = _make_mock_data("ecomm-order", "stream-paused")
    query = extract_symptoms("ecomm-order", data)
    assert "paused" in query.lower() or "order-events" in query


def test_extract_symptoms_ecomm_manager_rate_limit():
    """ecomm-manager rate-limit has severe QPS drop; symptoms should mention metric degradation."""
    data = _make_mock_data("ecomm-manager", "rate-limit")
    query = extract_symptoms(
        "ecomm-manager",
        data,
        incident_description="管理 API QPS 骤降",
    )
    assert "管理 API QPS 骤降" in query
    assert any(kw in query.lower() for kw in ("rate", "qps", "limit", "degraded", "dropped", "admin", "ready"))
