"""Graph rules. A workflow graph is {"nodes": [...], "edges": [...]},
the same shape React Flow uses, so the frontend can send it as is."""
from collections import defaultdict, deque

KNOWN_TYPES = {"start", "llm"}  # Day 2 adds: condition, validator, approval, ...


class GraphError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def parents_of(graph: dict) -> dict[str, list[str]]:
    """node id -> ids of the nodes that feed into it. Assumes a valid graph."""
    parents: dict[str, list[str]] = {n["id"]: [] for n in graph["nodes"]}
    for e in graph.get("edges", []):
        parents[e["target"]].append(e["source"])
    return parents


def validate_graph(graph: dict) -> None:
    """Raise GraphError listing every problem found."""
    nodes = graph.get("nodes")
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not nodes:
        raise GraphError(["graph needs a non-empty 'nodes' list"])
    if not isinstance(edges, list):
        raise GraphError(["'edges' must be a list"])

    errors: list[str] = []
    ids: list[str] = []
    for n in nodes:
        if not isinstance(n, dict) or "id" not in n or "type" not in n:
            raise GraphError(["every node needs an 'id' and a 'type'"])
        ids.append(n["id"])
        if n["type"] not in KNOWN_TYPES:
            errors.append(f"node '{n['id']}' has unknown type '{n['type']}'")
    if len(set(ids)) != len(ids):
        errors.append("node ids must be unique")

    start_ids = [n["id"] for n in nodes if n["type"] == "start"]
    if len(start_ids) != 1:
        errors.append(f"expected exactly 1 start node, found {len(start_ids)}")

    id_set = set(ids)
    adj: dict[str, list[str]] = defaultdict(list)
    indegree = {i: 0 for i in id_set}
    for e in edges:
        src, dst = e.get("source"), e.get("target")
        if src not in id_set or dst not in id_set:
            errors.append(f"edge {src!r} -> {dst!r} points to a missing node")
            continue
        adj[src].append(dst)
        indegree[dst] += 1

    if errors:  # cycle / reachability checks need a structurally sound graph
        raise GraphError(errors)

    # Cycle check (Kahn's algorithm): peel off nodes with no incoming edges.
    # If some nodes can never be peeled, they sit on a cycle.
    remaining = dict(indegree)
    queue = deque(i for i, d in remaining.items() if d == 0)
    peeled = 0
    while queue:
        cur = queue.popleft()
        peeled += 1
        for nxt in adj[cur]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                queue.append(nxt)
    if peeled != len(id_set):
        raise GraphError(["graph has a cycle"])

    start = start_ids[0]
    if indegree[start] > 0:
        errors.append("start node cannot have incoming edges")

    # Every node must be reachable from start, or it would never run.
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    unreachable = sorted(id_set - seen)
    if unreachable:
        errors.append(f"nodes not reachable from start: {', '.join(map(str, unreachable))}")

    if errors:
        raise GraphError(errors)
