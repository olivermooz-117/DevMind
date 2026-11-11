import json
import sqlite3

from .config import DATA_DIR, DB_PATH


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS code_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_path TEXT NOT NULL,
                file_path TEXT NOT NULL,
                language TEXT NOT NULL,
                symbol TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_repo
            ON code_chunks(repo_path)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS repository_embedding_metadata (
                repo_path TEXT PRIMARY KEY,
                embedding_model TEXT NOT NULL,
                embedding_dimensions INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def replace_repository_chunks(
    repo_path,
    chunks,
    embedding_model=None,
    embedding_dimensions=None,
):
    """Replace a repository's chunks and embedding metadata atomically."""
    with connect() as connection:
        connection.execute(
            "DELETE FROM code_chunks WHERE repo_path = ?",
            (repo_path,),
        )

        connection.executemany("""
            INSERT INTO code_chunks
            (repo_path, file_path, language, symbol, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (
                repo_path,
                chunk["file_path"],
                chunk["language"],
                chunk["symbol"],
                chunk["content"],
                json.dumps(chunk["embedding"]),
            )
            for chunk in chunks
        ])

        if embedding_model and embedding_dimensions:
            connection.execute("""
                INSERT INTO repository_embedding_metadata
                    (repo_path, embedding_model, embedding_dimensions)
                VALUES (?, ?, ?)
                ON CONFLICT(repo_path) DO UPDATE SET
                    embedding_model = excluded.embedding_model,
                    embedding_dimensions = excluded.embedding_dimensions,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                repo_path,
                embedding_model,
                embedding_dimensions,
            ))
        else:
            connection.execute(
                """
                DELETE FROM repository_embedding_metadata
                WHERE repo_path = ?
                """,
                (repo_path,),
            )


def get_repository_embedding_metadata(repo_path):
    with connect() as connection:
        row = connection.execute("""
            SELECT embedding_model, embedding_dimensions
            FROM repository_embedding_metadata
            WHERE repo_path = ?
        """, (repo_path,)).fetchone()

    return dict(row) if row else None


def get_repository_chunks(repo_path=None):
    with connect() as connection:
        if repo_path:
            rows = connection.execute(
                "SELECT * FROM code_chunks WHERE repo_path = ?",
                (repo_path,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM code_chunks"
            ).fetchall()

    results = []

    for row in rows:
        item = dict(row)
        item["embedding"] = json.loads(item["embedding"])
        results.append(item)

    return results


def get_repositories():
    """Return indexed repositories with their chunk and file counts."""
    with connect() as connection:
        rows = connection.execute("""
            SELECT
                chunks.repo_path,
                chunks.chunk_count,
                chunks.file_count,
                metadata.embedding_model,
                metadata.embedding_dimensions,
                metadata.updated_at
            FROM (
                SELECT
                    repo_path,
                    COUNT(*) AS chunk_count,
                    COUNT(DISTINCT file_path) AS file_count
                FROM code_chunks
                GROUP BY repo_path
            ) AS chunks
            LEFT JOIN repository_embedding_metadata AS metadata
                ON metadata.repo_path = chunks.repo_path
            ORDER BY chunks.repo_path
        """).fetchall()

    return [dict(row) for row in rows]
