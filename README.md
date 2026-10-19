# WorkGraph

Build a workflow of AI steps on a canvas, run it, and watch every step.
Runs are saved after each step, so a crash resumes instead of restarting.

> Status: Day 1 of 3, backend core. The UI comes next.

## Run the backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env  (add GROQ_API_KEY, or skip for mock mode)
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs. This page lets you call every endpoint from the browser.

## Try it

1. `POST /workflows`: paste the contents of `backend/samples/summarize_critique.json`.
2. `POST /workflows/1/runs`: body `{"input": {"text": "Cats sleep a lot."}, "mock": true}`.
3. `GET /runs/1`: repeat until `status` is `succeeded`. Each node shows input, output, tokens, duration.

`"mock": true` returns canned replies. Leave it out to use Groq (needs `GROQ_API_KEY`).

## Crash recovery demo

Start a run with `MOCK_DELAY=5` set (slow mock nodes), kill the server with Ctrl+C or `kill -9`
while a node is running, start it again. The run continues from the last finished node.

## Tests

```bash
cd backend
python -m pytest
```

## How it works (so far)

- A workflow is a graph: `{nodes, edges}`, the same JSON shape React Flow uses.
- `engine.py` finds nodes whose parents are finished, runs them, and saves each result
  to SQLite before continuing. That saved row is the checkpoint.
- On startup the server looks for runs still marked `running` and resumes them.
- Each node row has a unique key `run_id:node_id`, so one node can never be recorded twice.
