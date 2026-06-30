from app.graph.state import AgentState


def triage_node(state: AgentState) -> dict:
    incident = state["incident"]
    service = incident.service
    return {
        "service": service,
        "status": "triaged",
        "messages": [{"role": "system", "content": f"Incident on {service}: {incident.description}"}],
    }
