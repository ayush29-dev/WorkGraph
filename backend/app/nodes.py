"""Node handlers. Each node type is one async function in HANDLERS.
To add a node type: write a handler, register it, add it to graph.KNOWN_TYPES."""
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .llm import call_llm


@dataclass
class NodeContext:
    node: dict                 # the node from the graph JSON
    run_input: dict            # what the user passed when starting the run
    outputs: dict[str, dict]   # node_id -> output of every finished node
    mock: bool = False


@dataclass
class NodeResult:
    output: dict
    tokens: int = 0
    input: dict = field(default_factory=dict)  # what the node actually received (for the inspector)


Handler = Callable[[NodeContext], Awaitable[NodeResult]]
HANDLERS: dict[str, Handler] = {}


def handler(node_type: str):
    def register(fn: Handler) -> Handler:
        HANDLERS[node_type] = fn
        return fn

    return register


# {{some_node.output}} is replaced with the text that node produced.
_TEMPLATE = re.compile(r"\{\{\s*([\w-]+)\.output\s*\}\}")


def render(template: str, outputs: dict[str, dict]) -> str:
    def substitute(match: re.Match) -> str:
        node_id = match.group(1)
        if node_id not in outputs:
            raise ValueError(f"template refers to node '{node_id}', which has no output yet")
        return str(outputs[node_id].get("text", ""))

    return _TEMPLATE.sub(substitute, template)


@handler("start")
async def run_start(ctx: NodeContext) -> NodeResult:
    text = str(ctx.run_input.get("text", ""))
    return NodeResult(output={"text": text}, input=ctx.run_input)


@handler("llm")
async def run_llm(ctx: NodeContext) -> NodeResult:
    data = ctx.node.get("data", {})
    prompt = render(data.get("prompt", ""), ctx.outputs)
    system = render(data.get("system", ""), ctx.outputs)
    if not prompt.strip():
        raise ValueError("LLM node has an empty prompt")
    text, tokens = await call_llm(system, prompt, data.get("model"), ctx.mock)
    return NodeResult(
        output={"text": text},
        tokens=tokens,
        input={"system": system, "prompt": prompt},
    )
