"""Shared fixtures for all tests."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Generator
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _setup_test_env():
    """Set test environment variables before each test."""
    os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    yield


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary SQLite database for tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# Tool fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_tool_registry():
    """Create a clean ToolRegistry for testing."""
    from backend.tools.base import ToolRegistry
    registry = ToolRegistry()
    return registry


# ---------------------------------------------------------------------------
# Mock HTTP responses
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_httpx_client() -> Generator[MagicMock, None, None]:
    """Mock httpx.Client for testing LLM calls."""
    with patch("httpx.Client") as mock:
        client_instance = MagicMock()
        mock.return_value.__enter__.return_value = client_instance
        yield client_instance


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create the FastAPI application for testing."""
    from main import app
    return app


@pytest.fixture
async def async_client(app):
    """Create an async test client for integration tests."""
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
