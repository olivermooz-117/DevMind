# DevMind Architecture

DevMind is a local-first AI engineering workbench.

## Components

1. Next.js provides the browser interface.
2. Flask exposes repository ingestion, semantic search, explanation, and chat APIs.
3. Tree-sitter parses supported source files into syntax-aware chunks.
4. Ollama generates local embeddings with `nomic-embed-text`.
5. SQLite stores source chunks and their embeddings.
6. Cosine similarity ranks retrieved chunks.
7. Ollama `llama3.2:1b` generates answers using retrieved repository context.

## Request flow

Browser -> Next.js -> Flask -> SQLite / Ollama

Repository ingestion:
Repository folder -> file discovery -> Tree-sitter parsing -> local embeddings -> SQLite

Question answering:
Question -> embedding -> cosine similarity -> top code chunks -> prompt context -> Ollama response

## Current limitations

- The backend must be able to access the repository folder path.
- The first embedding request downloads or initializes the local embedding model.
- Indexing is performed synchronously.
- SQLite stores embedding vectors as JSON; this is suitable for a small local MVP, not large-scale vector workloads.
- Retrieval quality and answer correctness require evaluation.
- Tree-sitter parsing falls back to text chunks when parsing fails.
