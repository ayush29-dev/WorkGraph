import os
import tempfile

# Must be set BEFORE the app is imported, so tests use a throwaway database.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.gettempdir()}/workgraph_test.db"
os.environ["MOCK_DELAY"] = "0"

import pytest  # noqa: E402

from app.db import Base, engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
