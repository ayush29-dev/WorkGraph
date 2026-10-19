"""Request bodies. FastAPI uses these (via Pydantic) to validate JSON for us."""
from pydantic import BaseModel


class WorkflowIn(BaseModel):
    name: str
    graph: dict


class RunIn(BaseModel):
    input: dict = {}
    # None = auto: use mock mode when no GROQ_API_KEY is set.
    mock: bool | None = None
