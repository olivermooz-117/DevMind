import re
from collections import OrderedDict

import numpy as np

from .database import (
    get_repository_chunks,
    get_repository_embedding_metadata,
)
from .ollama_client import create_embedding
from .config import EMBED_MODEL, MAX_RESULTS_PER_FILE, MAX_SEARCH_RESULTS


MAX_HYBRID_CANDIDATES = 50


class EmbeddingModelMismatchError(ValueError):
    """Raised when an index cannot be searched with the configured model."""


def _keyword_score(query, content):
    """Simple keyword overlap score: fraction of query words found in content."""
    query_words = set(
        w.lower() for w in re.split(r"\W+", query) if w.strip()
    )
    if not query_words:
        return 0.0

    content_words = set(
        w.lower() for w in re.split(r"\W+", content) if w.strip()
    )
    if not content_words:
        return 0.0

    overlap = query_words & content_words
    return len(overlap) / len(query_words)


def _normalize_scores(scores):
    """Normalize a list of scores to 0-1 range."""
    if not scores:
        return []
    min_s = min(scores)
    max_s = max(scores)
    if max_s == min_s:
        return [1.0] * len(scores)
    return [(s - min_s) / (max_s - min_s) for s in scores]


def search_code(query, repo_path=None, limit=None, use_hybrid=True):
    """Search indexed code chunks using semantic similarity with optional
    hybrid keyword boosting.

    Results are deduplicated by (file_path, symbol) and diversified so no
    single file dominates. Each result includes start_line and end_line
    for citation purposes.
    """
    if limit is None:
        limit = MAX_SEARCH_RESULTS
    chunks = get_repository_chunks(repo_path)

    if not chunks:
        return []

    # A repository must have metadata from a successful, current ingestion.
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

    semantic_scores = (matrix @ query_vector) / norms

    if use_hybrid:
        keyword_scores = np.asarray(
            [_keyword_score(query, chunk["content"]) for chunk in chunks],
            dtype=np.float32,
        )
        # Combine: 70% semantic + 30% keyword
        semantic_norm = _normalize_scores(semantic_scores.tolist())
        keyword_norm = _normalize_scores(keyword_scores.tolist())
        combined_scores = np.asarray(
            [0.7 * s + 0.3 * k for s, k in zip(semantic_norm, keyword_norm)],
            dtype=np.float32,
        )
    else:
        combined_scores = semantic_scores

    # Rank by combined score, best first
    ranked_indices = np.argsort(combined_scores)[::-1]

    # Deduplicate by (file_path, symbol) and diversify across files
    seen_keys = set()
    file_counts = {}
    results = []

    for i in ranked_indices:
        chunk = chunks[int(i)]
        dedup_key = (chunk["file_path"], chunk["symbol"])

        if dedup_key in seen_keys:
            continue

        file_path = chunk["file_path"]
        if file_counts.get(file_path, 0) >= MAX_RESULTS_PER_FILE:
            continue

        seen_keys.add(dedup_key)
        file_counts[file_path] = file_counts.get(file_path, 0) + 1

        results.append({
            "file_path": chunk["file_path"],
            "language": chunk["language"],
            "symbol": chunk["symbol"],
            "content": chunk["content"],
            "start_line": chunk.get("start_line"),
            "end_line": chunk.get("end_line"),
            "score": round(float(combined_scores[int(i)]), 4),
        })

        if len(results) >= limit:
            break

    return results


def hybrid_search(query, repo_path=None, limit=5):
    """Alias for search_code with hybrid mode enabled (default)."""
    return search_code(query, repo_path=repo_path, limit=limit, use_hybrid=True)
