import os

import requests
from flask import Flask, jsonify, request

from devmind.database import initialize_database
from devmind.ingestion import ingest_repository
from devmind.retrieval import search_code
from devmind.assistant import answer_about_code
from devmind.config import CHAT_MODEL, OLLAMA_URL
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
        return jsonify({"error": "The AI model took too long to respond"}), 504

    if isinstance(error, requests.exceptions.ConnectionError):
        return jsonify({"error": OLLAMA_UNAVAILABLE}), 503

    return jsonify({"error": "The AI model returned an error"}), 502


@app.get("/health")
def health():
    return jsonify({
        "status": "healthy",
        "model": CHAT_MODEL,
        "ollama_url": OLLAMA_URL,
    })


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
        return jsonify({"error": "Repository ingestion failed"}), 500


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
        results = search_code(query.strip(), repo_path=repo_path, limit=limit)
        return jsonify({"results": results})
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

    except requests.exceptions.RequestException as error:
        return model_error_response(error)


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
