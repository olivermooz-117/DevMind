from unittest.mock import Mock, patch

from app import app
from devmind.config import CHAT_MODEL, EMBED_MODEL


def test_health_is_a_liveness_check():
    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "healthy"


@patch("app.requests.get")
def test_ready_when_database_and_models_are_available(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "models": [
            {"name": CHAT_MODEL},
            {"name": EMBED_MODEL},
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    response = app.test_client().get("/ready")

    assert response.status_code == 200
    assert response.json["status"] == "ready"
    assert response.json["checks"]["database"] == "ok"
    assert response.json["checks"]["ollama"] == "ok"


@patch("app.requests.get")
def test_ready_returns_503_when_ollama_is_unavailable(mock_get):
    import requests

    mock_get.side_effect = requests.exceptions.ConnectionError(
        "Ollama unavailable"
    )

    response = app.test_client().get("/ready")

    assert response.status_code == 503
    assert response.json["status"] == "degraded"
    assert response.json["checks"]["ollama"] == "unavailable"


@patch("app.requests.get")
def test_ready_returns_503_when_required_models_are_missing(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {"models": [{"name": CHAT_MODEL}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    response = app.test_client().get("/ready")

    assert response.status_code == 503
    assert response.json["checks"]["chat_model"] == "ok"
    assert response.json["checks"]["embedding_model"] == "missing"
