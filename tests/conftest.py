import os

import pytest
from fastapi.testclient import TestClient
from app import create_app

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_APP_JSON = os.path.join(TESTS_DIR, "test_app.json")


@pytest.fixture
def app():
    """FastAPI app without authentication for tests."""
    application = create_app(
        config_path=TEST_APP_JSON,
    )
    return application


@pytest.fixture
def client(app):
    return TestClient(app)
