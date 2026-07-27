"""Test response handler via FastAPI TestClient."""

from app.engine.registry import register_access_handler, register_response_handler
from app.engine.status import ok


@register_response_handler("hello_handler")
async def hello_handler(ctx):
    return ok({"message": "Hello from PyApiGate!"})


@register_access_handler("require_admin_role")
def require_admin_role(ctx):
    body = ctx.request.json
    if body is None or not isinstance(body, dict) or body.get("role") != "admin":
        return ctx.deny()
    return ctx.allow()


class TestResponseHandler:
    def test_hello(self, client):
        resp = client.get("/hello")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Hello from PyApiGate!"


class TestAccessWithBody:
    def test_access_denied_no_body(self, client):
        resp = client.post("/admin-only")
        assert resp.status_code == 403

    def test_access_denied_wrong_role(self, client):
        resp = client.post("/admin-only", json={"role": "user"})
        assert resp.status_code == 403

    def test_access_allowed_admin(self, client):
        resp = client.post("/admin-only", json={"role": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Hello from PyApiGate!"
