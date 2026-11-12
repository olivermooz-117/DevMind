import json
import logging
import re
import sqlite3
import time

from .config import DATA_DIR, DB_PATH


logger = logging.getLogger(__name__)


_DB_MAX_RETRIES = 3
_DB_RETRY_DELAY = 0.5


def _execute_with_retry(connection, sql, parameters=()):
    """Execute a SQL statement with retry for transient lock errors."""
    last_error = None

    for attempt in range(_DB_MAX_RETRIES):
        try:
            return connection.execute(sql, parameters)
        except sqlite3.OperationalError as error:
            last_error = error
            if "locked" in str(error).lower() and attempt < _DB_MAX_RETRIES - 1:
                logger.warning(
                    "Database locked, retrying (%d/%d)",
                    attempt + 1,
                    _DB_MAX_RETRIES,
                )
                time.sleep(_DB_RETRY_DELAY * (attempt + 1))
            else:
                logger.error(
                    "Database operation failed after %d retries",
                    _DB_MAX_RETRIES,
                )
                raise

    raise last_error


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _column_exists(connection, table, column):
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


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

        if not _column_exists(connection, "code_chunks", "start_line"):
            connection.execute(
                "ALTER TABLE code_chunks ADD COLUMN start_line INTEGER"
            )
        if not _column_exists(connection, "code_chunks", "end_line"):
            connection.execute(
                "ALTER TABLE code_chunks ADD COLUMN end_line INTEGER"
            )

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

        connection.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                repo_path TEXT,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                sources TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_created
            ON messages(created_at)
        """)


def replace_repository_chunks(
    repo_path,
    chunks,
    embedding_model=None,
    embedding_dimensions=None,
):
    """Replace a repository's chunks and embedding metadata atomically."""
    with connect() as connection:
        _execute_with_retry(
            connection,
            "DELETE FROM code_chunks WHERE repo_path = ?",
            (repo_path,),
        )

        connection.executemany("""
            INSERT INTO code_chunks
            (repo_path, file_path, language, symbol, content, embedding,
             start_line, end_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                repo_path,
                chunk["file_path"],
                chunk["language"],
                chunk["symbol"],
                chunk["content"],
                json.dumps(chunk["embedding"]),
                chunk.get("start_line"),
                chunk.get("end_line"),
            )
            for chunk in chunks
        ])

        if embedding_model and embedding_dimensions:
            _execute_with_retry(
                connection,
                """
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
                ),
            )
        else:
            _execute_with_retry(
                connection,
                """
                DELETE FROM repository_embedding_metadata
                WHERE repo_path = ?
                """,
                (repo_path,),
            )


def get_repository_embedding_metadata(repo_path):
    with connect() as connection:
        row = _execute_with_retry(
            connection,
            """
            SELECT embedding_model, embedding_dimensions
            FROM repository_embedding_metadata
            WHERE repo_path = ?
            """,
            (repo_path,),
        ).fetchone()

    return dict(row) if row else None


def get_repository_chunks(repo_path=None):
    with connect() as connection:
        if repo_path:
            rows = _execute_with_retry(
                connection,
                "SELECT * FROM code_chunks WHERE repo_path = ?",
                (repo_path,),
            ).fetchall()
        else:
            rows = _execute_with_retry(
                connection,
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
        rows = _execute_with_retry(
            connection,
            """
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
        """,
        ).fetchall()

    return [dict(row) for row in rows]


def create_conversation(repo_path=None, title=None):
    """Create a new conversation and return its ID."""
    import uuid
    from datetime import datetime, timezone

    conversation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    display_title = title or "New conversation"

    with connect() as connection:
        _execute_with_retry(
            connection,
            """
            INSERT INTO conversations (id, repo_path, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, repo_path, display_title, now, now),
        )

    return conversation_id


def get_conversation(conversation_id):
    """Return a conversation dict or None if not found."""
    with connect() as connection:
        row = _execute_with_retry(
            connection,
            """
            SELECT id, repo_path, title, created_at, updated_at
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()

    return dict(row) if row else None


def list_conversations():
    """Return all conversations ordered by most recently updated."""
    with connect() as connection:
        rows = _execute_with_retry(
            connection,
            """
            SELECT id, repo_path, title, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            """,
        ).fetchall()

    return [dict(row) for row in rows]


def update_conversation_title(conversation_id, title):
    """Update a conversation's title and updated_at timestamp."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    with connect() as connection:
        _execute_with_retry(
            connection,
            """
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, now, conversation_id),
        )


def delete_conversation(conversation_id):
    """Delete a conversation and all its messages."""
    with connect() as connection:
        _execute_with_retry(
            connection,
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )


def add_message(conversation_id, role, content, sources=None):
    """Add a message to a conversation. Returns the message ID."""
    import json
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps(sources) if sources is not None else None

    with connect() as connection:
        cursor = _execute_with_retry(
            connection,
            """
            INSERT INTO messages
                (conversation_id, role, content, sources, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, role, content, sources_json, now),
        )

        _execute_with_retry(
            connection,
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
            """,
            (now, conversation_id),
        )

    return cursor.lastrowid


def get_messages(conversation_id, limit=None):
    """Return messages for a conversation, oldest first."""
    with connect() as connection:
        if limit:
            rows = _execute_with_retry(
                connection,
                """
                SELECT id, conversation_id, role, content, sources, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        else:
            rows = _execute_with_retry(
                connection,
                """
                SELECT id, conversation_id, role, content, sources, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        if item["sources"]:
            item["sources"] = json.loads(item["sources"])
        results.append(item)

    return results


# --- Conversation export/import ---

import re as _re
from datetime import datetime as _datetime
from uuid import uuid4 as _uuid4

MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB max import file
MAX_IMPORT_MESSAGES = 1000  # Max messages per import

_INVALID_ID_PATTERN = _re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)


def _validate_uuid(value):
    """Return True if value looks like a valid UUID v4."""
    return isinstance(value, str) and bool(_INVALID_ID_PATTERN.match(value.lower()))


def _validate_import_data(data):
    """Validate an imported conversation data structure.

    Returns (conversation_dict, messages_list) or raises ValueError.
    """
    if not isinstance(data, dict):
        raise ValueError("Import file must contain a JSON object")

    conversation = data.get("conversation")
    if not isinstance(conversation, dict):
        raise ValueError("Import data missing 'conversation' object")

    conv_id = conversation.get("id")
    if not _validate_uuid(conv_id):
        raise ValueError("Invalid conversation ID in import data")

    title = conversation.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Invalid conversation title in import data")

    repo_path = conversation.get("repo_path")
    if repo_path is not None and not isinstance(repo_path, str):
        raise ValueError("Invalid repo_path in import data")

    created_at = conversation.get("created_at")
    updated_at = conversation.get("updated_at")
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise ValueError("Invalid timestamps in import data")

    messages = data.get("messages")
    if not isinstance(messages, list):
        raise ValueError("Import data missing 'messages' array")

    if len(messages) > MAX_IMPORT_MESSAGES:
        raise ValueError(
            f"Import exceeds maximum of {MAX_IMPORT_MESSAGES} messages"
        )

    validated_messages = []
    for index, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValueError(f"Message {index} is not an object")

        role = msg.get("role")
        if role not in ("user", "assistant"):
            raise ValueError(f"Message {index} has invalid role: {role}")

        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Message {index} has invalid content")

        created_at_msg = msg.get("created_at")
        if not isinstance(created_at_msg, str):
            raise ValueError(f"Message {index} has invalid created_at")

        sources = msg.get("sources")
        if sources is not None:
            if not isinstance(sources, list):
                raise ValueError(f"Message {index} has invalid sources")
            for src_index, src in enumerate(sources):
                if not isinstance(src, dict):
                    raise ValueError(
                        f"Message {index} source {src_index} is not an object"
                    )
                if "file_path" not in src or not isinstance(src["file_path"], str):
                    raise ValueError(
                        f"Message {index} source {src_index} missing file_path"
                    )

        validated_messages.append({
            "role": role,
            "content": content,
            "sources": sources,
            "created_at": created_at_msg,
        })

    return conversation, validated_messages


def export_conversation(conversation_id, format="json"):
    """Export a conversation as JSON or Markdown.

    Returns (content_string, content_type, filename) or raises ValueError
    if the conversation is not found.
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")

    messages = get_messages(conversation_id)

    if format == "markdown":
        lines = [
            f"# {conversation['title']}",
            "",
            f"**Conversation ID:** {conversation['id']}",
            f"**Created:** {conversation['created_at']}",
            f"**Updated:** {conversation['updated_at']}",
        ]
        if conversation.get("repo_path"):
            lines.append(f"**Repository:** {conversation['repo_path']}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for msg in messages:
            role_label = "You" if msg["role"] == "user" else "DevMind"
            lines.append(f"## {role_label}")
            lines.append("")
            lines.append(msg["content"])
            lines.append("")
            if msg.get("sources"):
                lines.append("*Sources:*")
                for src in msg["sources"]:
                    location = src.get("file_path", "unknown")
                    if src.get("start_line") is not None:
                        location += f":{src['start_line']}"
                    lines.append(f"- {location}")
                lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines), "text/markdown", f"conversation-{conversation_id}.md"

    # Default: JSON export
    export_data = {
        "conversation": {
            "id": conversation["id"],
            "repo_path": conversation.get("repo_path"),
            "title": conversation["title"],
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"],
        },
        "messages": [
            {
                "role": msg["role"],
                "content": msg["content"],
                "sources": msg.get("sources"),
                "created_at": msg["created_at"],
            }
            for msg in messages
        ],
    }

    return (
        json.dumps(export_data, indent=2),
        "application/json",
        f"conversation-{conversation_id}.json",
    )


def import_conversation(data, repo_path=None):
    """Import a conversation from validated data.

    Returns the new conversation ID. Raises ValueError if data is invalid
    or the conversation ID already exists.
    """
    conversation, messages = _validate_import_data(data)

    new_id = str(_uuid4())

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # Use the repo_path from the import data if no override provided
    effective_repo_path = repo_path or conversation.get("repo_path")

    # Validate repo_path against allowed root if provided
    if effective_repo_path:
        from .security import resolve_repo_path
        try:
            effective_repo_path = str(resolve_repo_path(effective_repo_path))
        except ValueError:
            effective_repo_path = None

    with connect() as connection:
        _execute_with_retry(
            connection,
            """
            INSERT INTO conversations
                (id, repo_path, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                new_id,
                effective_repo_path,
                conversation["title"],
                now,
                now,
            ),
        )

        for msg in messages:
            sources_json = json.dumps(msg["sources"]) if msg.get("sources") else None
            _execute_with_retry(
                connection,
                """
                INSERT INTO messages
                    (conversation_id, role, content, sources, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    msg["role"],
                    msg["content"],
                    sources_json,
                    msg["created_at"],
                ),
            )

    return new_id
