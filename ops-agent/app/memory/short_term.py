import sqlite3
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import get_settings


@lru_cache(maxsize=1)
def get_checkpointer():
    settings = get_settings()
    if settings.checkpointer == "sqlite":
        path = Path(settings.checkpointer_sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        return SqliteSaver(conn)
    return MemorySaver()
