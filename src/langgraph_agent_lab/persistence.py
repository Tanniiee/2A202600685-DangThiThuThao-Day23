"""Checkpointer adapter."""

from __future__ import annotations

from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer.

    Supported kinds:
    - "none"    → no checkpointing
    - "memory"  → MemorySaver (fast, non-persistent across restarts)
    - "sqlite"  → SqliteSaver with WAL mode (persistent, good for demos and crash-resume)
    - "postgres"→ Not implemented (optional extension)

    For SQLite, set DATABASE_URL to a file path, e.g. "outputs/checkpoints.db".
    Defaults to "outputs/checkpoints.db" if DATABASE_URL is not set.
    """
    if kind == "none":
        return None

    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError(
                "SQLite checkpointer requires: pip install langgraph-checkpoint-sqlite"
            ) from exc

        import sqlite3
        from pathlib import Path

        db_path = database_url or "outputs/checkpoints.db"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path, check_same_thread=False)
        # Enable WAL mode for better concurrency and crash safety
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()

        return SqliteSaver(conn)

    if kind == "postgres":
        raise NotImplementedError(
            "TODO(student): implement Postgres checkpointer (optional extension)"
        )

    raise ValueError(f"Unknown checkpointer kind: {kind}")
