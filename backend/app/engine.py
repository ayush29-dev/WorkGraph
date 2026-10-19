"""The workflow engine.

Core idea: after every node finishes, its result is saved to the database
BEFORE we look at the next node. If the process dies, the database says
exactly which nodes are done. On restart we skip those and carry on.
"""
import asyncio
import logging
import time

from .db import SessionLocal
from .graph import parents_of
from .models import NodeRun, Run, utcnow
from .nodes import HANDLERS, NodeContext

log = logging.getLogger("workgraph.engine")

_active: set[int] = set()            # runs executing in this process right now
_tasks: set[asyncio.Task] = set()    # keeps references so tasks aren't garbage collected


def start_run(run_id: int) -> None:
    """Fire-and-forget: execute a run in the background."""
    task = asyncio.create_task(execute_run(run_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def unfinished_run_ids() -> list[int]:
    with SessionLocal() as db:
        rows = db.query(Run.id).filter(Run.status.in_(["queued", "running"])).all()
    return [r[0] for r in rows]


def resume_unfinished_runs() -> list[int]:
    """Called on server startup. Picks up runs a previous process left behind."""
    ids = unfinished_run_ids()
    for run_id in ids:
        log.info("resuming run %s", run_id)
        start_run(run_id)
    return ids


async def execute_run(run_id: int) -> None:
    if run_id in _active:  # never execute the same run twice at once
        return
    _active.add(run_id)
    try:
        await _execute(run_id)
    finally:
        _active.discard(run_id)


async def _execute(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None or run.status in ("succeeded", "failed"):
            return
        run.status = "running"
        if run.started_at is None:
            run.started_at = utcnow()
        db.commit()
        graph, run_input, mock = run.graph, run.input, run.mock

    nodes = {n["id"]: n for n in graph["nodes"]}
    parents = parents_of(graph)

    while True:
        # What is already finished? (After a crash, this is what we resume from.)
        with SessionLocal() as db:
            finished = db.query(NodeRun).filter_by(run_id=run_id, status="succeeded").all()
            outputs = {nr.node_id: nr.output for nr in finished}

        # Ready = not done yet, and every parent is done.
        ready = [
            n for node_id, n in nodes.items()
            if node_id not in outputs and all(p in outputs for p in parents[node_id])
        ]
        if not ready:
            break

        # Day 2: run `ready` nodes together with asyncio.gather.
        for node in ready:
            error = await _run_node(run_id, node, run_input, outputs, mock)
            if error:
                _finish(run_id, graph, failed_node=node["id"], error=error)
                return

    _finish(run_id, graph)


async def _run_node(run_id: int, node: dict, run_input: dict, outputs: dict, mock: bool) -> str | None:
    """Run one node and checkpoint the result. Returns an error message, or None on success."""
    key = f"{run_id}:{node['id']}"

    # 1. Mark running. Reuse the row if a crashed attempt left one behind.
    with SessionLocal() as db:
        nr = db.query(NodeRun).filter_by(idempotency_key=key).one_or_none()
        if nr is None:
            nr = NodeRun(run_id=run_id, node_id=node["id"], node_type=node["type"],
                         idempotency_key=key, attempt=0)
            db.add(nr)
        nr.status = "running"
        nr.attempt += 1
        nr.error = None
        nr.started_at = utcnow()
        db.commit()
        nr_id = nr.id

    # 2. Do the work.
    started = time.perf_counter()
    error: str | None = None
    result = None
    try:
        fn = HANDLERS.get(node["type"])
        if fn is None:
            raise ValueError(f"no handler for node type '{node['type']}'")
        result = await fn(NodeContext(node=node, run_input=run_input, outputs=outputs, mock=mock))
    except Exception as exc:  # a real crash (kill -9, power cut) never reaches this line
        error = f"{type(exc).__name__}: {exc}"
        log.warning("node %s failed: %s", key, error)
    duration_ms = int((time.perf_counter() - started) * 1000)

    # 3. Checkpoint: save the outcome before moving on.
    with SessionLocal() as db:
        nr = db.get(NodeRun, nr_id)
        nr.duration_ms = duration_ms
        if error:
            nr.status = "failed"
            nr.error = error
        else:
            nr.status = "succeeded"
            nr.output = result.output
            nr.input = result.input
            nr.tokens = result.tokens
        db.commit()
    return error


def _finish(run_id: int, graph: dict, failed_node: str | None = None, error: str | None = None) -> None:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        node_runs = db.query(NodeRun).filter_by(run_id=run_id).all()
        run.total_tokens = sum(nr.tokens for nr in node_runs)
        run.finished_at = utcnow()
        if failed_node:
            run.status = "failed"
            run.error = f"node '{failed_node}' failed: {error}"
        else:
            run.status = "succeeded"
            # The run's result = output of every node that has no outgoing edge.
            has_outgoing = {e["source"] for e in graph.get("edges", [])}
            run.output = {
                nr.node_id: nr.output
                for nr in node_runs
                if nr.status == "succeeded" and nr.node_id not in has_outgoing
            }
        db.commit()
