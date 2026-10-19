import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.engine import execute_run, unfinished_run_ids
from app.models import NodeRun
from app.nodes import HANDLERS
from tests.helpers import chain_graph, get_run, make_run, node_runs


def test_chain_runs_and_checkpoints_every_node():
    run_id = make_run(chain_graph())
    asyncio.run(execute_run(run_id))

    run = get_run(run_id)
    assert run.status == "succeeded"
    assert run.total_tokens > 0
    assert set(run.output) == {"c"}  # only the last node has no outgoing edge
    done = node_runs(run_id)
    assert {k: v.status for k, v in done.items()} == {
        "start": "succeeded", "a": "succeeded", "b": "succeeded", "c": "succeeded",
    }
    # Template worked: b received a's output.
    assert "[mock reply] Summarize: hello" in done["b"].input["prompt"]


class SimulatedCrash(BaseException):
    """Not an Exception subclass, so the engine cannot catch it.
    Same effect as the process being killed mid-node."""


def test_resume_after_crash_skips_finished_nodes(monkeypatch):
    real_llm = HANDLERS["llm"]
    calls: list[str] = []
    crash_on = {"node": "b"}

    async def flaky_llm(ctx):
        calls.append(ctx.node["id"])
        if ctx.node["id"] == crash_on["node"]:
            raise SimulatedCrash()
        return await real_llm(ctx)

    monkeypatch.setitem(HANDLERS, "llm", flaky_llm)
    run_id = make_run(chain_graph())

    # First process: dies while running node b.
    with pytest.raises(SimulatedCrash):
        asyncio.run(execute_run(run_id))
    assert get_run(run_id).status == "running"
    assert {k: v.status for k, v in node_runs(run_id).items()} == {
        "start": "succeeded", "a": "succeeded", "b": "running",
    }

    # Server restarts: it finds the unfinished run and resumes it.
    crash_on["node"] = None
    assert unfinished_run_ids() == [run_id]
    asyncio.run(execute_run(run_id))

    assert get_run(run_id).status == "succeeded"
    done = node_runs(run_id)
    assert done["a"].attempt == 1   # NOT re-run
    assert done["b"].attempt == 2   # retried after the crash
    assert done["c"].attempt == 1
    assert calls == ["a", "b", "b", "c"]


def test_failed_node_fails_the_run_and_stops():
    graph = chain_graph({"a": "Summarize: {{start.output}}", "b": "   ", "c": "never runs {{b.output}}"})
    run_id = make_run(graph)
    asyncio.run(execute_run(run_id))

    run = get_run(run_id)
    assert run.status == "failed"
    assert "node 'b' failed" in run.error and "empty prompt" in run.error
    done = node_runs(run_id)
    assert done["b"].status == "failed"
    assert "c" not in done  # downstream node was never started


def test_template_with_unknown_node_fails_clearly():
    graph = chain_graph({"a": "Use {{nope.output}}"})
    run_id = make_run(graph)
    asyncio.run(execute_run(run_id))
    assert get_run(run_id).status == "failed"
    assert "nope" in get_run(run_id).error


def test_one_row_per_node_per_run():
    """Idempotency key is UNIQUE: the database itself refuses duplicates."""
    run_id = make_run(chain_graph())
    with SessionLocal() as db:
        db.add(NodeRun(run_id=run_id, node_id="a", node_type="llm", idempotency_key=f"{run_id}:a"))
        db.commit()
        db.add(NodeRun(run_id=run_id, node_id="a", node_type="llm", idempotency_key=f"{run_id}:a"))
        with pytest.raises(IntegrityError):
            db.commit()
