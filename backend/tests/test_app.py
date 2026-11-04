import os
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DEVMIND_DATA_DIR"] = "/tmp/devmind-test-data"

from app import app


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
