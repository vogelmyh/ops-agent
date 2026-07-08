import sqlite3
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import get_settings
from app.schemas import Evidence, IncidentInput

# AgentState stores these Pydantic models in checkpoints; register explicitly so
# LangGraph does not warn (and future strict msgpack mode still works).
_CHECKPOINT_ALLOWED_MSGPACK: tuple[tuple[str, str], ...] = (
    ("app.schemas", "IncidentInput"),
    ("app.schemas", "Evidence"),
)


def get_checkpoint_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            *_CHECKPOINT_ALLOWED_MSGPACK,
            IncidentInput,
            Evidence,
        ],
    )


@lru_cache(maxsize=1)
def get_checkpointer():
    serde = get_checkpoint_serde()
    settings = get_settings()
    if settings.checkpointer == "sqlite":
        path = Path(settings.checkpointer_sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        return SqliteSaver(conn, serde=serde)
    return MemorySaver(serde=serde)
