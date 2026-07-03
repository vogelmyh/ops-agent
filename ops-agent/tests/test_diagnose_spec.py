"""Tests for RootCauseDraft LLM JSON coercion."""

from app.graph.diagnose_spec import (
    RootCauseDraft,
    coerce_root_cause_draft,
    normalize_evidence_source,
)


def test_normalize_evidence_source_human_labels():
    assert normalize_evidence_source("Application Logs") == "app_logs"
    assert normalize_evidence_source("Metrics (order_amount_error_rate)") == "metrics"
    assert normalize_evidence_source("k8s_events") == "k8s_events"


def test_coerce_root_cause_draft_evidence_sources():
    data = coerce_root_cause_draft({
        "root_cause": "折扣校验逻辑缺陷",
        "evidence": [
            {
                "source": "Application Logs",
                "snippet": "discount validation error",
                "ref": "query_app_logs:ecomm-manager",
            },
            {
                "source": "Metrics (order_amount_error_rate)",
                "snippet": "error rate 12%",
                "ref": "get_metrics:ecomm-manager",
            },
        ],
    })
    model = RootCauseDraft.model_validate(data)
    assert model.evidence[0].source == "app_logs"
    assert model.evidence[1].source == "metrics"


def test_root_cause_draft_validator_applies_coercion():
    model = RootCauseDraft.model_validate({
        "root_cause": "OOM 导致缓存不可用",
        "evidence": [
            {
                "source": "Kubernetes Events",
                "snippet": "OOMKilled",
                "ref": "get_k8s_events:ecomm-cache",
            },
        ],
    })
    assert model.evidence[0].source == "k8s_events"
