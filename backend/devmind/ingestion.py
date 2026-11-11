from .parser import discover_source_files, parse_source_file
from .ollama_client import create_embeddings
from .database import replace_repository_chunks
from .config import EMBED_BATCH_SIZE, EMBED_MODEL


def embedding_text(chunk):
    """Give the embedding model the file and symbol, not just the code."""
    return (
        f"{chunk['file_path']} :: {chunk['symbol']}\n"
        f"{chunk['content']}"
    )


def ingest_repository(repo_path):
    root, files = discover_source_files(repo_path)
    chunks = []

    for file_path in files:
        relative_path = str(file_path.relative_to(root))

        for chunk in parse_source_file(file_path):
            chunk["file_path"] = relative_path
            chunks.append(chunk)

    if not chunks:
        raise ValueError(
            "No supported source files were found in that repository"
        )

    # Generate every embedding before replacing the existing index.
    # If Ollama fails, the previous index remains intact.
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start:start + EMBED_BATCH_SIZE]
        vectors = create_embeddings([
            embedding_text(chunk) for chunk in batch
        ])

        if len(vectors) != len(batch):
            raise RuntimeError(
                "Embedding count does not match the number of input chunks"
            )

        for chunk, vector in zip(batch, vectors):
            chunk["embedding"] = vector

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

    replace_repository_chunks(
        str(root),
        chunks,
        embedding_model=EMBED_MODEL,
        embedding_dimensions=dimensions,
    )

    return {
        "repository": str(root),
        "files_discovered": len(files),
        "chunks_indexed": len(chunks),
        "embedding_model": EMBED_MODEL,
        "embedding_dimensions": dimensions,
    }
