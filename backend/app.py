import os
import time
import uuid

import requests
from flask import Flask, jsonify, request, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devmind.database import (
    connect,
    initialize_database,
    get_repositories,
    create_conversation,
    get_conversation,
    list_conversations,
    delete_conversation,
    get_messages,
)
from devmind.ingestion import ingest_repository
from devmind.retrieval import (
    search_code,
    EmbeddingModelMismatchError,
)
from devmind.assistant import (
    answer_about_code,
    get_conversation_history,
    list_all_conversations,
    remove_conversation,
)
from devmind.config import CHAT_MODEL, EMBED_MODEL, OLLAMA_URL, MAX_SEARCH_RESULTS
from devmind.ollama_client import generate_response
from devmind.security import resolve_repo_path

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
initialize_database()


def _rate_limit(key):
    return f"{key}/minute"


INGEST_LIMIT = os.getenv("DEVMIND_RATE_LIMIT_INGEST", "30/minute")
SEARCH_LIMIT = os.getenv("DEVMIND_RATE_LIMIT_SEARCH", "60/minute")
EXPLAIN_LIMIT = os.getenv("DEVMIND_RATE_LIMIT_EXPLAIN", "60/minute")
CHAT_LIMIT = os.getenv("DEVMIND_RATE_LIMIT_CHAT", "60/minute")
CONVERSATION_LIMIT = os.getenv("DEVMIND_RATE_LIMIT_CONVERSATION", "120/minute")


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200/minute"],
    headers_enabled=True,
)


@limiter.request_filter
def exempt_health_and_ready():
    return request.path in {"/health", "/ready"}


@app.errorhandler(429)
def rate_limit_exceeded(error):
    app.logger.warning(
        "Rate limit exceeded",
        extra={
            "request_id": getattr(g, "request_id", None),
            "path": request.path,
            "method": request.method,
        },
    )
    return jsonify({
        "error": "Too many requests. Please slow down and try again later.",
    }), 429


_ALLOWED_ORIGINS = {
    "http://127.0.0.1:3000",
    "http://localhost:3000",
}


@app.before_request
def assign_request_id():
    g.request_id = str(uuid.uuid4())
    g.start_time = time.time()

    app.logger.info(
        "Request started",
        extra={
            "request_id": g.request_id,
            "method": request.method,
            "path": request.path,
        },
    )


@app.after_request
def log_request(response):
    duration = (time.time() - getattr(g, "start_time", 0)) * 1000
    app.logger.info(
        "Request completed",
        extra={
            "request_id": getattr(g, "request_id", None),
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round(duration, 2),
        },
    )
    return response


@app.before_request
def handle_cors_preflight():
    if request.method == "OPTIONS":
        origin = request.headers.get("Origin", "")
        if origin in _ALLOWED_ORIGINS:
            response = jsonify({})
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response, 200
        return jsonify({"error": "CORS origin not allowed"}), 403


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin in _ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

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
        "error": "Repository index is incompatible with the configured embedding model.",
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
@limiter.limit(INGEST_LIMIT)
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
@limiter.limit(SEARCH_LIMIT)
def semantic_search():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")

    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "A search query is required"}), 400

    try:
        limit = max(1, min(int(data.get("limit", MAX_SEARCH_RESULTS)), MAX_SEARCH_RESULTS))
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
@limiter.limit(EXPLAIN_LIMIT)
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
@limiter.limit(CHAT_LIMIT)
def chat():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "")
    conversation_id = data.get("conversation_id")
    repo_path = None

    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "A valid prompt is required"}), 400

    raw_repo_path = data.get("repo_path")
    if raw_repo_path:
        try:
            repo_path = str(resolve_repo_path(raw_repo_path))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    try:
        if repo_path:
            result = answer_about_code(
                prompt.strip(),
                repo_path=repo_path,
                conversation_id=conversation_id,
            )

            return jsonify({
                "response": result["answer"],
                "sources": result["sources"],
                "conversation_id": result["conversation_id"],
                "citation_keys": result.get("citation_keys", []),
                "model": CHAT_MODEL,
            })

        # General chat without repository context
        response_text = generate_response(prompt.strip())
        return jsonify({
            "response": response_text,
            "model": CHAT_MODEL,
        })

    except EmbeddingModelMismatchError as error:
        return embedding_index_error(error)
    except requests.exceptions.RequestException as error:
        return model_error_response(error)


@app.get("/conversations")
@limiter.limit(CONVERSATION_LIMIT)
def conversations_list():
    """List all conversations, most recently updated first."""
    try:
        return jsonify({"conversations": list_all_conversations()})
    except Exception:
        app.logger.exception("Could not load conversations")
        return jsonify({
            "error": "Could not load conversations"
        }), 500


@app.post("/conversations")
@limiter.limit(CONVERSATION_LIMIT)
def conversations_create():
    """Create a new conversation, optionally associated with a repository."""
    data = request.get_json(silent=True) or {}
    repo_path = data.get("repo_path")

    if repo_path is not None:
        try:
            repo_path = str(resolve_repo_path(repo_path))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    try:
        conversation_id = create_conversation(repo_path=repo_path)
        conversation = get_conversation(conversation_id)
        return jsonify({
            "conversation_id": conversation_id,
            "conversation": conversation,
        }), 201
    except Exception:
        app.logger.exception("Could not create conversation")
        return jsonify({
            "error": "Could not create conversation"
        }), 500


@app.get("/conversations/<conversation_id>")
@limiter.limit(CONVERSATION_LIMIT)
def conversations_get(conversation_id):
    """Get a conversation with all its messages."""
    try:
        history = get_conversation_history(conversation_id)
        if history is None:
            return jsonify({
                "error": "Conversation not found"
            }), 404
        return jsonify(history)
    except Exception:
        app.logger.exception("Could not load conversation")
        return jsonify({
            "error": "Could not load conversation"
        }), 500


@app.delete("/conversations/<conversation_id>")
@limiter.limit(CONVERSATION_LIMIT)
def conversations_delete(conversation_id):
    """Delete a conversation and all its messages."""
    try:
        conversation = get_conversation(conversation_id)
        if conversation is None:
            return jsonify({
                "error": "Conversation not found"
            }), 404
        remove_conversation(conversation_id)
        return jsonify({"status": "deleted"})
    except Exception:
        app.logger.exception("Could not delete conversation")
        return jsonify({
            "error": "Could not delete conversation"
        }), 500


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
