from .parser import discover_source_files, parse_source_file
from .ollama_client import create_embedding
from .database import replace_repository_chunks


def ingest_repository(repo_path):
    root, files = discover_source_files(repo_path)
    all_chunks = []

    for file_path in files:
        parsed_chunks = parse_source_file(file_path)

        for chunk in parsed_chunks:
            try:
                chunk["file_path"] = str(
                    file_path.relative_to(root)
                )
                chunk["embedding"] = create_embedding(chunk["content"])
                all_chunks.append(chunk)
            except Exception as error:
                print(f"Skipping chunk in {file_path}: {error}")

    replace_repository_chunks(str(root), all_chunks)

    return {
        "repository": str(root),
        "files_discovered": len(files),
        "chunks_indexed": len(all_chunks),
    }
