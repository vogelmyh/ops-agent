from app.graph.state import AgentState


def compress_node(state: AgentState) -> dict:
    findings = state.get("findings", [])
    compressed = {"summary": f"{len(findings)} finding groups compressed"}
    return {"findings": [compressed], "status": "compressed"}
