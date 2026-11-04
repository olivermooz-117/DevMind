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


def replace_repository_chunks(repo_path, chunks):
    with connect() as connection:
        connection.execute(
            "DELETE FROM code_chunks WHERE repo_path = ?",
            (repo_path,)
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
                json.dumps(chunk["embedding"])
            )
            for chunk in chunks
        ])


def get_repository_chunks(repo_path=None):
    with connect() as connection:
        if repo_path:
            rows = connection.execute(
                "SELECT * FROM code_chunks WHERE repo_path = ?",
                (repo_path,)
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
