"""The three tables. Day 2 adds `outbox`."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    # Naive UTC. SQLite does not keep timezones, so we stay consistent.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    graph: Mapped[dict] = mapped_column(JSON)  # {"nodes": [...], "edges": [...]}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"))
    # queued -> running -> succeeded | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # Copy of the graph at run time, so editing the workflow
    # while a run is in progress (or being resumed) cannot break it.
    graph: Mapped[dict] = mapped_column(JSON)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    mock: Mapped[bool] = mapped_column(default=False)
    total_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    node_runs: Mapped[list["NodeRun"]] = relationship(
        order_by="NodeRun.id", cascade="all, delete-orphan"
    )


class NodeRun(Base):
    """One row per node per run. This row IS the checkpoint."""

    __tablename__ = "node_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    node_id: Mapped[str] = mapped_column(String(100))
    node_type: Mapped[str] = mapped_column(String(50))
    # pending -> running -> succeeded | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempt: Mapped[int] = mapped_column(default=0)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    tokens: Mapped[int] = mapped_column(default=0)
    # "<run_id>:<node_id>". UNIQUE, so one node can never have two rows.
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
