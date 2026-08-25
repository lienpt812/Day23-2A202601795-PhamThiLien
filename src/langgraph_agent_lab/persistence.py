"""Checkpointer adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> object | None:
    """Return a LangGraph checkpointer.

    The memory saver is useful for tests. SQLite gives the lab a durable
    checkpoint store that can be inspected or reused across runs.
    """
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        from langgraph.checkpoint.sqlite import SqliteSaver

        path = Path(database_url or "outputs/checkpoints.sqlite")
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return SqliteSaver(conn=conn)
    if kind == "postgres":
        raise ValueError("Postgres checkpointer is optional for this lab; use memory or sqlite.")
    raise ValueError(f"Unknown checkpointer kind: {kind}")
