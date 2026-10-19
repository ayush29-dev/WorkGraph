import time

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import chain_graph


def test_create_run_and_poll_until_done():
    with TestClient(app) as client:  # `with` runs startup (init_db + resume)
        assert client.get("/health").json() == {"status": "ok"}

        r = client.post("/workflows", json={"name": "demo", "graph": chain_graph()})
        assert r.status_code == 201
        wf_id = r.json()["id"]

        r = client.post(f"/workflows/{wf_id}/runs", json={"input": {"text": "hi"}, "mock": True})
        assert r.status_code == 201
        run_id = r.json()["id"]

        body = {}
        for _ in range(50):
            body = client.get(f"/runs/{run_id}").json()
            if body["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)

        assert body["status"] == "succeeded"
        assert len(body["node_runs"]) == 4
        assert client.get("/runs").json()[0]["id"] == run_id


def test_invalid_graph_is_rejected_with_reasons():
    with TestClient(app) as client:
        g = chain_graph()
        g["edges"].append({"source": "c", "target": "a"})
        r = client.post("/workflows", json={"name": "bad", "graph": g})
        assert r.status_code == 422
        assert r.json()["detail"]["errors"] == ["graph has a cycle"]
