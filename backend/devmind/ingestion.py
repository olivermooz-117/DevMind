import logging
import time

import requests

from .parser import discover_source_files, parse_source_file
from .ollama_client import create_embeddings
from .database import replace_repository_chunks
from .config import EMBED_BATCH_SIZE, EMBED_MODEL


logger = logging.getLogger(__name__)


_EMBED_MAX_RETRIES = 3
_EMBED_RETRY_DELAY = 2.0

_ingestion_locks = {}


def _lock_for_repo(repo_path):
    if repo_path not in _ingestion_locks:
        import threading

        _ingestion_locks[repo_path] = threading.Lock()
    return _ingestion_locks[repo_path]


def embedding_text(chunk):
    """Give the embedding model the file and symbol, not just the code."""
    return (
        f"{chunk['file_path']} :: {chunk['symbol']}\n"
        f"{chunk['content']}"
    )


def _create_embeddings_with_retry(texts):
    """Create embeddings with retry for transient Ollama failures."""
    last_error = None

    for attempt in range(_EMBED_MAX_RETRIES):
        try:
            return create_embeddings(texts)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as error:
            last_error = error
            if attempt < _EMBED_MAX_RETRIES - 1:
                logger.warning(
                    "Embedding attempt %d failed, retrying",
                    attempt + 1,
                    extra={"error": str(error)},
                )
                time.sleep(_EMBED_RETRY_DELAY * (attempt + 1))
        except Exception:
            raise

    logger.error("Embedding failed after %d attempts", _EMBED_MAX_RETRIES)
    raise last_error


def _repo_label(repo_path):
    """Return a safe, non-absolute label for log messages."""
    return repo_path.rstrip("/").split("/")[-1] or "root"


def ingest_repository(repo_path):
    start_time = time.time()
    repo_label = _repo_label(repo_path)

    root, files = discover_source_files(repo_path)
    chunks = []

    skipped_files = 0
    for file_path in files:
        relative_path = str(file_path.relative_to(root))

        parsed = parse_source_file(file_path)
        if parsed:
            for chunk in parsed:
                chunk["file_path"] = relative_path
                chunks.append(chunk)
        else:
            skipped_files += 1

    if not chunks:
        logger.warning(
            "No supported source files found",
            extra={
                "repository": repo_label,
                "files_discovered": len(files),
            },
        )
        raise ValueError(
            "No supported source files were found in that repository"
        )

    # Serialize ingestion per repository to prevent concurrent writes from
    # corrupting repository state.
    lock = _lock_for_repo(str(root))

    with lock:
        embed_start = time.time()

        # Generate every embedding before replacing the existing index.
        # If Ollama fails, the previous index remains intact.
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start:start + EMBED_BATCH_SIZE]
            vectors = _create_embeddings_with_retry([
                embedding_text(chunk) for chunk in batch
            ])

            if len(vectors) != len(batch):
                raise RuntimeError(
                    "Embedding count does not match the number of input chunks"
                )

            for chunk, vector in zip(batch, vectors):
                chunk["embedding"] = vector

        embed_duration = (time.time() - embed_start) * 1000

        dimensions = len(chunks[0]["embedding"])

        if dimensions == 0:
            raise RuntimeError("The embedding model returned an empty vector")

        if any(
            len(chunk["embedding"]) != dimensions
            for chunk in chunks
        ):
            raise RuntimeError(
                "The embedding model returned inconsistent vector dimensions"
            )

        db_start = time.time()
        replace_repository_chunks(
            str(root),
            chunks,
            embedding_model=EMBED_MODEL,
            embedding_dimensions=dimensions,
        )
        db_duration = (time.time() - db_start) * 1000

    total_duration = (time.time() - start_time) * 1000

    logger.info(
        "Repository ingestion completed",
        extra={
            "repository": repo_label,
            "files_discovered": len(files),
            "files_skipped": skipped_files,
            "chunks_indexed": len(chunks),
            "embedding_model": EMBED_MODEL,
            "embedding_dimensions": dimensions,
            "embed_duration_ms": round(embed_duration, 2),
            "db_write_duration_ms": round(db_duration, 2),
            "total_duration_ms": round(total_duration, 2),
        },
    )

    return {
        "repository": str(root),
        "files_discovered": len(files),
        "chunks_indexed": len(chunks),
        "embedding_model": EMBED_MODEL,
        "embedding_dimensions": dimensions,
    }
