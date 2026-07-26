import os

import pytest
from fastapi.testclient import TestClient
from app import create_app

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def app():
    """FastAPI app without authentication for tests."""
    application = create_app(
        config_path=os.path.join(TESTS_DIR, "test_routes.yaml"),
    )
    return application


@pytest.fixture
def client(app):
    return TestClient(app)
