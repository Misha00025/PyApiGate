"""Test response handler via Flask test client."""

from app.engine.registry import register_response_handler
from app.engine.status import ok


@register_response_handler("hello_handler")
def hello_handler(ctx):
    return ok({"message": "Hello from PyApiGate!"})


class TestResponseHandler:
    def test_hello(self, client):
        resp = client.get("/hello")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "Hello from PyApiGate!"
