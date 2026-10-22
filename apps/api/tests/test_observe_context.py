"""Per-request probe context (correlation id + route as flow id)."""
import contextlib

from app import observe


def test_request_context_is_a_no_op_without_the_sdk(monkeypatch):
    monkeypatch.setattr(observe, "enabled", lambda: False)
    with observe.request_context("c", "GET /api/x"):
        pass


def test_middleware_binds_the_matched_route_template(client, monkeypatch):
    seen = []

    @contextlib.contextmanager
    def fake(correlation_id, flow_id):
        seen.append((correlation_id, flow_id))
        yield

    monkeypatch.setattr(observe, "enabled", lambda: True)
    monkeypatch.setattr(observe, "request_context", fake)
    r = client.get("/api/threads/1", headers={"X-User-Id": "1"})
    assert r.status_code == 200
    assert seen and seen[0][1] == "GET /api/threads/{tid}"
    assert r.headers["X-Probe-Correlation-Id"] == seen[0][0]
