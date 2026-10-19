from app.db import SessionLocal
from app.models import NodeRun, Run, Workflow


def chain_graph(prompts=None):
    """start -> a -> b -> c, each LLM node feeding the next."""
    prompts = prompts or {
        "a": "Summarize: {{start.output}}",
        "b": "Critique: {{a.output}}",
        "c": "Improve: {{b.output}}",
    }
    nodes = [{"id": "start", "type": "start", "data": {}}]
    nodes += [{"id": k, "type": "llm", "data": {"prompt": v}} for k, v in prompts.items()]
    ids = ["start", *prompts]
    edges = [{"id": f"e{i}", "source": s, "target": t} for i, (s, t) in enumerate(zip(ids, ids[1:]))]
    return {"nodes": nodes, "edges": edges}


def make_run(graph, text="hello", mock=True) -> int:
    with SessionLocal() as db:
        wf = Workflow(name="t", graph=graph)
        db.add(wf)
        db.flush()
        run = Run(workflow_id=wf.id, graph=graph, input={"text": text}, mock=mock, status="queued")
        db.add(run)
        db.commit()
        return run.id


def get_run(run_id):
    with SessionLocal() as db:
        return db.get(Run, run_id)


def node_runs(run_id) -> dict:
    with SessionLocal() as db:
        return {n.node_id: n for n in db.query(NodeRun).filter_by(run_id=run_id)}
