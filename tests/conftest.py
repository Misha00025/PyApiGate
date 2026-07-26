import os

import pytest
from app import create_app

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def app():
    """Flask app без аутентификации для тестов."""
    application = create_app(
        config_path=os.path.join(TESTS_DIR, "test_routes.yaml"),
        import_handlers=False,
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()
