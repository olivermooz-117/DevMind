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


def stream_generate_response(prompt):
    """Stream generated text from Ollama, yielding chunks as they arrive.

    Yields (text_chunk, done) tuples. When done is True, the stream is complete
    and the full response is available by concatenating all yielded chunks.
    """
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": CHAT_MODEL,
                "prompt": prompt,
                "stream": True
            },
            timeout=240,
            stream=True,
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = line.decode("utf-8", errors="replace")
                if data.startswith("data: "):
                    data = data[6:]
                import json as _json
                parsed = _json.loads(data)
                chunk = parsed.get("response", "")
                done = parsed.get("done", False)
                yield chunk, done
                if done:
                    return
            except (ValueError, json.JSONDecodeError):
                # Skip malformed lines in the stream
                continue

    except requests.exceptions.RequestException as error:
        raise error
