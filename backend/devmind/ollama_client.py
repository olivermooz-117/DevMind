import requests

from .config import OLLAMA_URL, CHAT_MODEL, EMBED_MODEL


def create_embeddings(texts):
    """Embed several texts in a single Ollama request."""
    if not texts:
        return []

    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={
            "model": EMBED_MODEL,
            "input": texts
        },
        timeout=180
    )
    response.raise_for_status()

    embeddings = response.json().get("embeddings", [])

    if len(embeddings) != len(texts):
        raise RuntimeError(
            f"Ollama returned {len(embeddings)} embeddings "
            f"for {len(texts)} inputs"
        )

    return embeddings


def create_embedding(text):
    return create_embeddings([text])[0]


def generate_response(prompt):
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": CHAT_MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=240
    )
    response.raise_for_status()
    return response.json().get("response", "")
