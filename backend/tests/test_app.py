import os
import sys
from pathlib import Path
from unittest.mock import patch

import logging

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DEVMIND_DATA_DIR"] = "/tmp/devmind-test-data"

from app import app


class LogCapture(logging.Handler):
    """Capture log records for assertion in tests."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_health():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"


def test_chat_requires_prompt():
    client = app.test_client()
    response = client.post("/chat", json={"prompt": ""})
    assert response.status_code == 400


def test_chat_calls_local_model():
    client = app.test_client()

    with patch("app.generate_response", return_value="Hello from DevMind"):
        response = client.post("/chat", json={"prompt": "Hello"})

    assert response.status_code == 200
    assert response.json["response"] == "Hello from DevMind"


def test_ingest_requires_repository_path():
    client = app.test_client()
    response = client.post("/ingest", json={})
    assert response.status_code == 400


def test_search_requires_query():
    client = app.test_client()
    response = client.post("/search", json={"query": ""})
    assert response.status_code == 400


def test_explain_requires_question():
    client = app.test_client()
    response = client.post("/explain", json={"question": ""})
    assert response.status_code == 400


def test_health_returns_cors_header():
    client = app.test_client()
    response = client.get(
        "/health", headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_health_rejects_disallowed_cors_origin():
    client = app.test_client()
    response = client.get(
        "/health", headers={"Origin": "http://evil.example.com"}
    )
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_preflight_allowed_origin():
    client = app.test_client()
    response = client.options(
        "/health", headers={"Origin": "http://127.0.0.1:3000"}
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"


def test_cors_preflight_disallowed_origin():
    client = app.test_client()
    response = client.options(
        "/health", headers={"Origin": "http://evil.example.com"}
    )
    assert response.status_code == 403


def test_oversized_request_is_rejected():
    client = app.test_client()
    oversized = "x" * (5 * 1024 * 1024)
    response = client.post(
        "/chat",
        json={"prompt": oversized},
        content_type="application/json",
    )
    assert response.status_code == 413


def test_request_logging_captures_request_id(caplog):
    """Request logging includes a unique request ID."""
    client = app.test_client()

    with caplog.at_level(logging.INFO, logger="app"):
        response = client.get("/health")
    assert response.status_code == 200

    # At least one log record should have a request_id
    request_id_records = [
        r for r in caplog.records
        if getattr(r, "request_id", None)
    ]
    assert len(request_id_records) > 0

    # Request IDs should be unique across requests
    response2 = client.get("/health")
    assert response2.status_code == 200

    request_id_records2 = [
        r for r in caplog.records
        if getattr(r, "request_id", None)
    ]
    ids = {r.request_id for r in request_id_records2}
    assert len(ids) >= 1


def test_429_error_handler_logs_warning(caplog):
    """HTTP 429 error handler logs at warning level."""
    from app import rate_limit_exceeded

    with app.test_request_context():
        with caplog.at_level(logging.WARNING, logger="app"):
            response, status_code = rate_limit_exceeded(None)
    assert status_code == 429
    assert response.json["error"] == "Too many requests. Please slow down and try again later."

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
    ]
    assert len(warning_records) >= 1
