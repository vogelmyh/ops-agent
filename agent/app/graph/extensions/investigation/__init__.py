"""Collaborative investigation extension (detached from main graph).

Re-attach via attach_investigation(graph) — see INVESTIGATE_EXTENSION hooks in builder.py.
"""

from app.graph.extensions.investigation.subgraph import attach_investigation

__all__ = ["attach_investigation"]
