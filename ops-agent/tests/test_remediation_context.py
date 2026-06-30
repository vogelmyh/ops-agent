from app.graph.remediation_context import (
    DECIDE_RETRY_GUIDANCE,
    EVAL_DIAGNOSIS_RETRY_GUIDANCE,
    format_remediation_context,
)


def test_format_remediation_context_empty_on_first_pass():
    assert format_remediation_context({}) == ""
    assert format_remediation_context({"remediation_attempt": 0, "remediation_history": []}) == ""


def test_format_remediation_context_includes_history_and_guidance():
    state = {
        "remediation_attempt": 1,
        "root_cause": "限流阈值误配",
        "remediation_eval_reasoning": "QPS still low",
        "remediation_history": [
            {
                "attempt": 1,
                "root_cause": "限流阈值误配",
                "tools_attempted": ["patch_config"],
                "exec_results": [{"status": "SUCCEEDED", "message": "Mock config patch"}],
                "resolved": False,
                "reasoning": "Rate limit issue persists",
                "residual_symptoms": ["admin API QPS degraded"],
            },
        ],
    }
    text = format_remediation_context(
        state,
        prior_root_cause="限流阈值误配",
        extra_guidance=DECIDE_RETRY_GUIDANCE,
    )
    assert "Prior remediation attempts" in text
    assert "Previous diagnosis (before this re-diagnosis): 限流阈值误配" in text
    assert "patch_config" in text
    assert "Tools that failed verification: patch_config" in text
    assert DECIDE_RETRY_GUIDANCE in text


def test_eval_diagnosis_guidance_constant():
    assert "Re-diagnosis after failed remediation" in EVAL_DIAGNOSIS_RETRY_GUIDANCE
