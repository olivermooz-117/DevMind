from .parser import discover_source_files, parse_source_file
from .ollama_client import create_embeddings
from .database import replace_repository_chunks
from .config import EMBED_BATCH_SIZE


def embedding_text(chunk):
    """Give the embedding model the file and symbol, not just the code."""
    return f"{chunk['file_path']} :: {chunk['symbol']}\n{chunk['content']}"


def ingest_repository(repo_path):
    root, files = discover_source_files(repo_path)
    chunks = []

    for file_path in files:
        relative_path = str(file_path.relative_to(root))

        for chunk in parse_source_file(file_path):
            chunk["file_path"] = relative_path
            chunks.append(chunk)

    if not chunks:
        raise ValueError("No supported source files were found in that repository")

    # Embed everything first. If Ollama fails, the exception propagates and
    # the existing index is left untouched.
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start:start + EMBED_BATCH_SIZE]
        vectors = create_embeddings([embedding_text(chunk) for chunk in batch])

        for chunk, vector in zip(batch, vectors):
            chunk["embedding"] = vector

    replace_repository_chunks(str(root), chunks)

    return {
        "repository": str(root),
        "files_discovered": len(files),
        "chunks_indexed": len(chunks),
    }
