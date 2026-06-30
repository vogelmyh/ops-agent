from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.rag.store import search_documents


class SearchRunbookInput(BaseModel):
    query: str = Field(description="Symptom or error description")
    top_k: int = Field(default=3, ge=1, le=10)


@tool(args_schema=SearchRunbookInput)
def search_runbook(query: str, top_k: int = 3) -> list:
    """Search runbooks and incident playbooks for grounding."""
    return search_documents(query, top_k=top_k)
