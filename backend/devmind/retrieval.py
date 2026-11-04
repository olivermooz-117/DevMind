import math

from .database import get_repository_chunks
from .ollama_client import create_embedding


def cosine_similarity(first, second):
    if not first or not second or len(first) != len(second):
        return 0.0

    dot = sum(a * b for a, b in zip(first, second))
    first_norm = math.sqrt(sum(a * a for a in first))
    second_norm = math.sqrt(sum(b * b for b in second))

    if not first_norm or not second_norm:
        return 0.0

    return dot / (first_norm * second_norm)


def search_code(query, repo_path=None, limit=5):
    query_embedding = create_embedding(query)
    chunks = get_repository_chunks(repo_path)

    ranked = []
    for chunk in chunks:
        score = cosine_similarity(query_embedding, chunk["embedding"])
        ranked.append({
            "file_path": chunk["file_path"],
            "language": chunk["language"],
            "symbol": chunk["symbol"],
            "content": chunk["content"],
            "score": round(score, 4),
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]
