def root_cause_match(expected: str, actual: str) -> bool:
    return expected in actual


def _tool_call_name(item) -> str:
    if isinstance(item, dict):
        return item.get("name") or item.get("action", "")
    if hasattr(item, "name"):
        return item.name
    if hasattr(item, "action"):
        return item.action
    return ""


def action_match(expected: str, tool_calls: list) -> bool:
    return any(_tool_call_name(tc) == expected for tc in tool_calls)


def llm_judge_score(expected_root: str, actual_root: str) -> float:
    """Offline heuristic judge; swap with real LLM when LLM_MODE=real."""
    if not actual_root:
        return 0.0
    return 1.0 if root_cause_match(expected_root, actual_root) else 0.0
