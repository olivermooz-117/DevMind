import os

import requests
from flask import Flask, jsonify, request

from devmind.database import (
    connect,
    initialize_database,
    get_repositories,
)
from devmind.ingestion import ingest_repository
from devmind.retrieval import (
    search_code,
    EmbeddingModelMismatchError,
)
from devmind.assistant import answer_about_code
from devmind.config import CHAT_MODEL, EMBED_MODEL, OLLAMA_URL
from devmind.ollama_client import generate_response
from devmind.security import resolve_repo_path

app = Flask(__name__)
initialize_database()

OLLAMA_UNAVAILABLE = (
    "Could not reach Ollama. Check that Ollama is running "
    "and the required models are installed."
)


def optional_repo_path(data):
    repo_path = data.get("repo_path")

    if not repo_path:
        return None

    return str(resolve_repo_path(repo_path))


def model_error_response(error):
    app.logger.warning("Ollama request failed: %s", error)

    if isinstance(error, requests.exceptions.Timeout):
        return jsonify({
            "error": "The AI model took too long to respond"
        }), 504

    if isinstance(error, requests.exceptions.ConnectionError):
        return jsonify({"error": OLLAMA_UNAVAILABLE}), 503

    return jsonify({
        "error": "The AI model returned an error"
    }), 502


def embedding_index_error(error):
    return jsonify({
        "error": str(error),
        "action": "Re-index the repository using the configured embedding model.",
    }), 409


@app.get("/repositories")
def repositories():
    """List repositories currently stored in the local index."""
    try:
        return jsonify({"repositories": get_repositories()})
    except Exception:
        app.logger.exception("Could not load indexed repositories")
        return jsonify({
            "error": "Could not load indexed repositories"
        }), 500


@app.get("/health")
def health():
    """Liveness check: confirms that the Flask process is responding."""
    return jsonify({
        "status": "healthy",
        "model": CHAT_MODEL,
        "embedding_model": EMBED_MODEL,
    })


@app.get("/ready")
def readiness():
    """Readiness check: verifies SQLite, Ollama, and required models."""
    checks = {
        "database": "unknown",
        "ollama": "unknown",
        "chat_model": "unknown",
        "embedding_model": "unknown",
    }

    try:
        with connect() as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database"] = "ok"
    except Exception:
        app.logger.exception("Database readiness check failed")
        checks["database"] = "unavailable"

    try:
        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=3,
        )
        response.raise_for_status()

        available_models = {
            model.get("name") or model.get("model")
            for model in response.json().get("models", [])
        }

        checks["ollama"] = "ok"
        checks["chat_model"] = (
            "ok" if CHAT_MODEL in available_models else "missing"
        )
        checks["embedding_model"] = (
            "ok" if EMBED_MODEL in available_models else "missing"
        )

    except requests.exceptions.RequestException:
        checks["ollama"] = "unavailable"
        checks["chat_model"] = "unavailable"
        checks["embedding_model"] = "unavailable"
    except (ValueError, TypeError):
        checks["ollama"] = "invalid_response"
        checks["chat_model"] = "unknown"
        checks["embedding_model"] = "unknown"

    ready = all(value == "ok" for value in checks.values())

    return jsonify({
        "status": "ready" if ready else "degraded",
        "checks": checks,
        "models": {
            "chat": CHAT_MODEL,
            "embedding": EMBED_MODEL,
        },
    }), 200 if ready else 503


@app.post("/ingest")
def ingest():
    data = request.get_json(silent=True) or {}
    repo_path = data.get("repo_path")

    if not isinstance(repo_path, str) or not repo_path.strip():
        return jsonify({"error": "repo_path is required"}), 400

    try:
        resolved = resolve_repo_path(repo_path)
        return jsonify(ingest_repository(str(resolved)))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except requests.exceptions.RequestException as error:
        return model_error_response(error)
    except Exception:
        app.logger.exception("Repository ingestion failed")
        return jsonify({
            "error": "Repository ingestion failed"
        }), 500


@app.post("/search")
def semantic_search():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")

    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "A search query is required"}), 400

    try:
        limit = max(1, min(int(data.get("limit", 5)), 20))
        repo_path = optional_repo_path(data)
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400

    try:
        results = search_code(
            query.strip(),
            repo_path=repo_path,
            limit=limit,
        )
        return jsonify({"results": results})
    except EmbeddingModelMismatchError as error:
        return embedding_index_error(error)
    except requests.exceptions.RequestException as error:
        return model_error_response(error)


@app.post("/explain")
def explain():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "")

    if not isinstance(question, str) or not question.strip():
        return jsonify({"error": "A question is required"}), 400

    try:
        repo_path = optional_repo_path(data)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        return jsonify(answer_about_code(question.strip(), repo_path))
    except EmbeddingModelMismatchError as error:
        return embedding_index_error(error)
    except requests.exceptions.RequestException as error:
        return model_error_response(error)


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "")

    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "A valid prompt is required"}), 400

    try:
        repo_path = optional_repo_path(data)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        if repo_path:
            result = answer_about_code(prompt.strip(), repo_path)
            return jsonify({
                "response": result["answer"],
                "sources": result["sources"],
                "model": CHAT_MODEL,
            })

        return jsonify({
            "response": generate_response(prompt.strip()),
            "model": CHAT_MODEL,
        })

    except EmbeddingModelMismatchError as error:
        return embedding_index_error(error)
    except requests.exceptions.RequestException as error:
        return model_error_response(error)


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
