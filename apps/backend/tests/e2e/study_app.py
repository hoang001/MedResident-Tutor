"""Explicit synthetic graph override for the isolated browser-test stack only."""

import sys
from pathlib import Path

sys.path.insert(0, "/test-support")

from knowledge_fixture import FixtureStore  # noqa: E402

from app.main import app  # noqa: E402
from app.modules.knowledge.service import get_graph_store  # noqa: E402

if Path("/test-support/knowledge_fixture.py").is_file():
    fixture_store = FixtureStore()
    app.dependency_overrides[get_graph_store] = lambda: fixture_store
else:
    raise RuntimeError("Isolated study test fixture is missing")
