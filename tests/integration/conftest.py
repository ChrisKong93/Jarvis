"""Integration test fixtures — temporary file-based SQLite database."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[str, None, None]:
    """Set up an isolated file-based SQLite database before integration tests.

    Uses a temporary file (not :memory:) to avoid connection-scoping issues
    with in-memory databases across multiple async requests.
    """
    import backend.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Create a temp file for the test database
    tmp = tempfile.NamedTemporaryFile(suffix=".test.db", delete=False)
    tmp.close()
    db_path = tmp.name

    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    # Patch the module-level engine & SessionLocal
    db_mod.engine = test_engine
    db_mod.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Create all tables
    from backend.database import Base
    Base.metadata.create_all(bind=test_engine)

    yield db_path

    # Cleanup
    test_engine.dispose()
    if os.path.exists(db_path):
        os.unlink(db_path)
