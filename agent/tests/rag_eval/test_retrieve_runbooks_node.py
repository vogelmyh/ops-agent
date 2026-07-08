import os

import pytest

os.environ["BACKEND_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ["CHECKPOINTER"] = "memory"

from app.adapters.mock_data import reset_mock_scenarios
from app.config import get_settings
from app.graph.builder import build_graph
from app.graph.nodes.retrieve_runbooks import retrieve_runbooks_node
from app.schemas import IncidentInput

pytestmark = pytest.mark.rag_only


@pytest.fixture(autouse=True)
def _reset():
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    yield
    reset_mock_scenarios()
    build_graph.cache_clear()


def test_retrieve_runbooks_node_outputs_retrieval_only():
    state = {
        "service": "ecomm-manager",
        "incident": IncidentInput(
            service="ecomm-manager",
            description="【P1】ecomm-manager admin_api_qps 低于阈值",
        ),
    }
    result = retrieve_runbooks_node(state)

    assert result["status"] == "runbooks_retrieved"
    assert result.get("symptom_query")
    assert result.get("runbook_candidates")
    assert "runbook_available" not in result
    assert "selected_runbook_id" not in result
    assert "match_gate_reason" not in result
    assert "relevant_runbook" not in result

    for candidate in result["runbook_candidates"]:
        assert candidate.get("retrieval_scores") is not None or candidate.get("doc_id")
        assert candidate.get("relevance") is None
        assert candidate.get("coverage") is None
