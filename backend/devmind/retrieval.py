import numpy as np

from .database import get_repository_chunks
from .ollama_client import create_embedding


def search_code(query, repo_path=None, limit=5):
    chunks = get_repository_chunks(repo_path)

    if not chunks:
        return []

    query_vector = np.asarray(create_embedding(query), dtype=np.float32)

    # Ignore chunks embedded with a different model (different dimensions).
    chunks = [
        chunk for chunk in chunks
        if len(chunk["embedding"]) == query_vector.shape[0]
    ]

    if not chunks:
        return []

    matrix = np.asarray(
        [chunk["embedding"] for chunk in chunks], dtype=np.float32
    )
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vector)
    norms[norms == 0] = 1.0
    scores = (matrix @ query_vector) / norms

    best = np.argsort(scores)[::-1][:limit]

    return [
        {
            "file_path": chunks[i]["file_path"],
            "language": chunks[i]["language"],
            "symbol": chunks[i]["symbol"],
            "content": chunks[i]["content"],
            "score": round(float(scores[i]), 4),
        }
        for i in best
    ]
