import pytest

from app.graph import GraphError, validate_graph
from tests.helpers import chain_graph


def errors_of(graph):
    with pytest.raises(GraphError) as exc:
        validate_graph(graph)
    return exc.value.errors


def test_valid_chain_passes():
    validate_graph(chain_graph())


def test_no_start_node():
    g = {"nodes": [{"id": "a", "type": "llm"}], "edges": []}
    assert any("exactly 1 start" in e for e in errors_of(g))


def test_two_start_nodes():
    g = {"nodes": [{"id": "s1", "type": "start"}, {"id": "s2", "type": "start"}], "edges": []}
    assert any("found 2" in e for e in errors_of(g))


def test_unknown_node_type():
    g = chain_graph()
    g["nodes"][1]["type"] = "teleport"
    assert any("unknown type" in e for e in errors_of(g))


def test_edge_to_missing_node():
    g = chain_graph()
    g["edges"].append({"source": "a", "target": "ghost"})
    assert any("missing node" in e for e in errors_of(g))


def test_cycle_detected():
    g = chain_graph()
    g["edges"].append({"source": "c", "target": "a"})
    assert errors_of(g) == ["graph has a cycle"]


def test_unreachable_node():
    g = chain_graph()
    g["nodes"].append({"id": "island", "type": "llm", "data": {"prompt": "x"}})
    assert any("not reachable" in e for e in errors_of(g))
