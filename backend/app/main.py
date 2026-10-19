import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import SessionLocal, init_db
from .engine import resume_unfinished_runs, start_run
from .graph import GraphError, validate_graph
from .models import NodeRun, Run, Workflow
from .schemas import RunIn, WorkflowIn


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    resume_unfinished_runs()  # crash recovery: finish whatever was in flight
    yield


app = FastAPI(title="WorkGraph", lifespan=lifespan)
app.add_middleware(  # lets the Vite dev server (Day 2) call this API
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _workflow(w: Workflow) -> dict:
    return {"id": w.id, "name": w.name, "graph": w.graph,
            "created_at": _iso(w.created_at), "updated_at": _iso(w.updated_at)}


def _node_run(n: NodeRun) -> dict:
    return {"id": n.id, "node_id": n.node_id, "node_type": n.node_type, "status": n.status,
            "attempt": n.attempt, "input": n.input, "output": n.output, "error": n.error,
            "duration_ms": n.duration_ms, "tokens": n.tokens, "started_at": _iso(n.started_at)}


def _run(r: Run, with_nodes: bool = False) -> dict:
    data = {"id": r.id, "workflow_id": r.workflow_id, "status": r.status, "input": r.input,
            "output": r.output, "error": r.error, "mock": r.mock, "total_tokens": r.total_tokens,
            "created_at": _iso(r.created_at), "started_at": _iso(r.started_at),
            "finished_at": _iso(r.finished_at)}
    if with_nodes:
        data["graph"] = r.graph
        data["node_runs"] = [_node_run(n) for n in r.node_runs]
    return data


def _check_graph(graph: dict) -> None:
    try:
        validate_graph(graph)
    except GraphError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/workflows", status_code=201)
def create_workflow(body: WorkflowIn):
    _check_graph(body.graph)
    with SessionLocal() as db:
        wf = Workflow(name=body.name, graph=body.graph)
        db.add(wf)
        db.commit()
        return _workflow(wf)


@app.get("/workflows")
def list_workflows():
    with SessionLocal() as db:
        return [_workflow(w) for w in db.query(Workflow).order_by(Workflow.id.desc())]


@app.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: int):
    with SessionLocal() as db:
        wf = db.get(Workflow, workflow_id)
        if wf is None:
            raise HTTPException(404, "workflow not found")
        return _workflow(wf)


@app.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: int, body: WorkflowIn):
    _check_graph(body.graph)
    with SessionLocal() as db:
        wf = db.get(Workflow, workflow_id)
        if wf is None:
            raise HTTPException(404, "workflow not found")
        wf.name = body.name
        wf.graph = body.graph
        db.commit()
        return _workflow(wf)


@app.post("/workflows/{workflow_id}/runs", status_code=201)
async def create_run(workflow_id: int, body: RunIn):
    with SessionLocal() as db:
        wf = db.get(Workflow, workflow_id)
        if wf is None:
            raise HTTPException(404, "workflow not found")
        mock = body.mock if body.mock is not None else not os.getenv("GROQ_API_KEY")
        run = Run(workflow_id=wf.id, graph=wf.graph, input=body.input, mock=mock, status="queued")
        db.add(run)
        db.commit()
        out = _run(run)
    start_run(out["id"])  # runs in the background, this request returns right away
    return out


@app.get("/runs")
def list_runs(limit: int = 50):
    with SessionLocal() as db:
        return [_run(r) for r in db.query(Run).order_by(Run.id.desc()).limit(limit)]


@app.get("/runs/{run_id}")
def get_run(run_id: int):
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return _run(run, with_nodes=True)
