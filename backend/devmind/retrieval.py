import numpy as np

from .database import (
    get_repository_chunks,
    get_repository_embedding_metadata,
)
from .ollama_client import create_embedding
from .config import EMBED_MODEL


class EmbeddingModelMismatchError(ValueError):
    """Raised when an index cannot be searched with the configured model."""


def search_code(query, repo_path=None, limit=5):
    chunks = get_repository_chunks(repo_path)

    if not chunks:
        return []

    # A repository must have metadata from a successful, current ingestion.
    # Older indexes must be re-ingested once to establish this metadata.
    repository_paths = {chunk["repo_path"] for chunk in chunks}

    if repo_path:
        repository_paths = {repo_path}

    for path in repository_paths:
        metadata = get_repository_embedding_metadata(path)

        if metadata is None:
            raise EmbeddingModelMismatchError(
                "This repository index has no embedding-model metadata. "
                "Re-index the repository before searching."
            )

        if metadata["embedding_model"] != EMBED_MODEL:
            raise EmbeddingModelMismatchError(
                "This repository was indexed with "
                f"'{metadata['embedding_model']}', but the configured "
                f"embedding model is '{EMBED_MODEL}'. "
                "Re-index the repository before searching."
            )

        if any(
            len(chunk["embedding"]) != metadata["embedding_dimensions"]
            for chunk in chunks
            if chunk["repo_path"] == path
        ):
            raise EmbeddingModelMismatchError(
                "The stored embedding dimensions do not match the "
                "repository index metadata. Re-index the repository."
            )

    query_vector = np.asarray(
        create_embedding(query),
        dtype=np.float32,
    )

    if not chunks:
        return []

    matrix = np.asarray(
        [chunk["embedding"] for chunk in chunks],
        dtype=np.float32,
    )

    if matrix.ndim != 2 or matrix.shape[1] != query_vector.shape[0]:
        raise EmbeddingModelMismatchError(
            "The query embedding dimensions do not match the stored index. "
            "Re-index the repository."
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
