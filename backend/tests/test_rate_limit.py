import os
import sys
from pathlib import Path

import pytest
from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DEVMIND_DATA_DIR"] = "/tmp/devmind-test-rate-limit"


def make_app(ingest_limit="5/minute"):
    """Create a Flask app with rate limiting for testing."""
    app = Flask(__name__)

    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri="memory://",
        default_limits=["200/minute"],
        headers_enabled=True,
    )
    limiter.init_app(app)

    @limiter.request_filter
    def exempt_health_and_ready():
        from flask import request

        return request.path in {"/health", "/ready"}

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({
            "error": "Too many requests. Please slow down and try again later.",
        }), 429

    @app.get("/health")
    def health():
        return jsonify({"status": "healthy"})

    @app.get("/ready")
    def ready():
        return jsonify({"status": "ready"})

    @app.post("/ingest")
    @limiter.limit(ingest_limit)
    def ingest():
        return jsonify({"status": "ok"})

    @app.post("/search")
    @limiter.limit("10/minute")
    def search():
        return jsonify({"results": []})

    return app, limiter


@pytest.fixture
def client():
    app, _ = make_app()
    app.testing = True
    return app.test_client()


def test_request_within_limit(client):
    """Requests under the rate limit succeed."""
    response = client.post("/ingest", json={"repo_path": "/tmp"})
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_request_exceeding_limit(client):
    """Requests over the rate limit return HTTP 429."""
    for _ in range(5):
        client.post("/ingest", json={"repo_path": "/tmp"})
    response = client.post("/ingest", json={"repo_path": "/tmp"})
    assert response.status_code == 429


def test_rate_limit_returns_json_error(client):
    """429 responses include a sanitized JSON error body."""
    for _ in range(5):
        client.post("/ingest", json={"repo_path": "/tmp"})
    response = client.post("/ingest", json={"repo_path": "/tmp"})
    assert response.status_code == 429
    assert "error" in response.json
    assert "Too many requests" in response.json["error"]


def test_health_endpoint_not_rate_limited(client):
    """Health endpoint remains accessible even after rate limit is hit."""
    for _ in range(5):
        client.post("/ingest", json={"repo_path": "/tmp"})
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"


def test_ready_endpoint_not_rate_limited(client):
    """Readiness endpoint remains accessible even after rate limit is hit."""
    for _ in range(5):
        client.post("/ingest", json={"repo_path": "/tmp"})
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json["status"] == "ready"


def test_other_endpoints_have_different_limits():
    """Different endpoints can have different rate limits."""
    app, _ = make_app(ingest_limit="2/minute")
    app.testing = True
    client = app.test_client()

    # /ingest has a 2/minute limit
    client.post("/ingest", json={"repo_path": "/tmp"})
    client.post("/ingest", json={"repo_path": "/tmp"})
    response = client.post("/ingest", json={"repo_path": "/tmp"})
    assert response.status_code == 429

    # /search has a 10/minute limit (default from make_app)
    for _ in range(9):
        client.post("/search", json={"query": "test"})
    response = client.post("/search", json={"query": "test"})
    assert response.status_code == 200
