import requests

from .config import OLLAMA_URL, CHAT_MODEL, EMBED_MODEL


def create_embedding(text):
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={
            "model": EMBED_MODEL,
            "input": text
        },
        timeout=180
    )
    response.raise_for_status()

    data = response.json()
    embeddings = data.get("embeddings", [])

    if not embeddings:
        raise RuntimeError("Ollama returned no embedding")

    return embeddings[0]


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
