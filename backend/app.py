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
    export_conversation,
    import_conversation,
)
from devmind.ingestion import ingest_repository
from devmind.retrieval import (
    search_code,
    EmbeddingModelMismatchError,
)
from devmind.assistant import (
    answer_about_code,
    stream_answer_about_code,
    get_conversation_history,
    list_all_conversations,
    remove_conversation,
)
from devmind.config import CHAT_MODEL, EMBED_MODEL, OLLAMA_URL, MAX_SEARCH_RESULTS
from devmind.ollama_client import generate_response, stream_generate_response
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
STREAM_LIMIT = os.getenv("DEVMIND_RATE_LIMIT_STREAM", "60/minute")


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
    repo_paths = data.get("repo_paths")

    resolved_paths = []
    invalid_paths = []

    if repo_path is not None:
        if not isinstance(repo_path, str):
            return jsonify({"error": "repo_path must be a string"}), 400
        try:
            resolved_paths.append(str(resolve_repo_path(repo_path)))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    if repo_paths is not None:
        if not isinstance(repo_paths, list):
            return jsonify({"error": "repo_paths must be a list"}), 400
        if not repo_paths:
            return jsonify({"error": "repo_paths must not be empty"}), 400
        for rp in repo_paths:
            if not isinstance(rp, str):
                invalid_paths.append(rp)
                continue
            try:
                resolved = str(resolve_repo_path(rp))
                if resolved not in resolved_paths:
                    resolved_paths.append(resolved)
            except ValueError:
                invalid_paths.append(rp)

        # Caller explicitly scoped repos: do not silently drop a fully invalid list
        if not resolved_paths:
            return jsonify({
                "error": "No valid repository paths in repo_paths",
                "invalid_paths": invalid_paths,
            }), 400

    if not resolved_paths:
        return jsonify({"error": "At least one valid repo_path is required"}), 400

    try:
        results = []
        for path in resolved_paths:
            results.append(ingest_repository(path))
        # Backward compatible single-repo response shape
        if len(results) == 1:
            return jsonify(results[0])
        return jsonify({
            "repositories": results,
            "indexed": len(results),
            "invalid_paths": invalid_paths,
        })
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
        repo_path = data.get("repo_path")
        repo_paths = data.get("repo_paths")
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400

    resolved_paths = []
    scope_requested = False

    if repo_path is not None:
        scope_requested = True
        if not isinstance(repo_path, str):
            return jsonify({"error": "repo_path must be a string"}), 400
        try:
            resolved_paths.append(str(resolve_repo_path(repo_path)))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    if repo_paths is not None:
        scope_requested = True
        if not isinstance(repo_paths, list):
            return jsonify({"error": "repo_paths must be a list"}), 400
        if not repo_paths:
            return jsonify({"error": "repo_paths must not be empty"}), 400
        for rp in repo_paths:
            if not isinstance(rp, str):
                continue
            try:
                resolved = str(resolve_repo_path(rp))
                if resolved not in resolved_paths:
                    resolved_paths.append(resolved)
            except ValueError:
                continue
        # Explicit scope that resolved to nothing must not fall back to "all repos"
        if not resolved_paths:
            return jsonify({
                "error": "No valid repository paths in repo_paths",
            }), 400

    try:
        results = search_code(
            query.strip(),
            repo_paths=resolved_paths if scope_requested else None,
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

    raw_repo_path = data.get("repo_path")
    repo_path = None
    if raw_repo_path:
        try:
            repo_path = str(resolve_repo_path(raw_repo_path))
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


@app.post("/chat/stream")
@limiter.limit(STREAM_LIMIT)
def chat_stream():
    """Stream an AI response using Server-Sent Events.

    Request body: same as /chat (prompt, repo_path, conversation_id).
    Response: text/event-stream with data lines containing JSON chunks.
    Each chunk: {"text": "...", "done": bool, "sources": [...], "conversation_id": "...", "citation_keys": [...]}
    """
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

    def generate():
        """Generator that yields SSE-formatted chunks."""
        try:
            for chunk, done, sources, cid, citation_keys in stream_answer_about_code(
                prompt.strip(),
                repo_path=repo_path,
                conversation_id=conversation_id,
            ):
                import json as _json
                payload = _json.dumps({
                    "text": chunk,
                    "done": done,
                    "sources": sources,
                    "conversation_id": cid,
                    "citation_keys": citation_keys,
                })
                yield f"data: {payload}\n\n"
        except requests.exceptions.RequestException:
            import json as _json
            payload = _json.dumps({
                "text": "\n\n[Stream interrupted. The AI model became unavailable during response generation.]",
                "done": True,
                "sources": [],
                "conversation_id": conversation_id or "",
                "citation_keys": [],
            })
            yield f"data: {payload}\n\n"
        except Exception:
            app.logger.exception("Streaming chat failed")
            import json as _json
            payload = _json.dumps({
                "text": "\n\n[Stream failed. Please try again.]",
                "done": True,
                "sources": [],
                "conversation_id": conversation_id or "",
                "citation_keys": [],
            })
            yield f"data: {payload}\n\n"

    return app.response_class(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/conversations/<conversation_id>/export")
@limiter.limit(CONVERSATION_LIMIT)
def conversations_export(conversation_id):
    """Export a conversation as JSON or Markdown.

    Query param: format=json|markdown (default: json)
    """
    format_param = request.args.get("format", "json").lower()
    if format_param not in ("json", "markdown"):
        format_param = "json"

    try:
        content, content_type, filename = export_conversation(conversation_id, format_param)
        return app.response_class(
            content,
            mimetype=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    except Exception:
        app.logger.exception("Could not export conversation")
        return jsonify({
            "error": "Could not export conversation"
        }), 500


@app.post("/conversations/import")
@limiter.limit(CONVERSATION_LIMIT)
def conversations_import():
    """Import a conversation from a JSON file.

    Request body: JSON object with {conversation, messages} structure.
    Optional query param: repo_path to associate with a specific repository.
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON body"}), 400

    raw_repo_path = request.args.get("repo_path")
    effective_repo_path = None
    if raw_repo_path:
        try:
            effective_repo_path = str(resolve_repo_path(raw_repo_path))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    try:
        new_id = import_conversation(data, repo_path=effective_repo_path)
        conversation = get_conversation(new_id)
        return jsonify({
            "conversation_id": new_id,
            "conversation": conversation,
        }), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Could not import conversation")
        return jsonify({
            "error": "Could not import conversation"
        }), 500
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
