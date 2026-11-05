import pytest

from devmind import database, retrieval


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "devmind.db")
    database.initialize_database()
    database.replace_repository_chunks("/repo", [
        {
            "file_path": "a.py", "language": "python", "symbol": "a",
            "content": "def a(): pass", "embedding": [1.0, 0.0],
        },
        {
            "file_path": "b.py", "language": "python", "symbol": "b",
            "content": "def b(): pass", "embedding": [0.0, 1.0],
        },
    ])


def test_search_ranks_most_similar_chunk_first(seeded_db, monkeypatch):
    monkeypatch.setattr(retrieval, "create_embedding", lambda text: [0.9, 0.1])

    results = retrieval.search_code("anything", repo_path="/repo", limit=2)

    assert [item["file_path"] for item in results] == ["a.py", "b.py"]
    assert results[0]["score"] > results[1]["score"]


def test_search_ignores_chunks_with_other_dimensions(seeded_db, monkeypatch):
    monkeypatch.setattr(
        retrieval, "create_embedding", lambda text: [1.0, 0.0, 0.0]
    )

    assert retrieval.search_code("anything", repo_path="/repo") == []


def test_search_with_no_index_returns_empty(seeded_db, monkeypatch):
    monkeypatch.setattr(retrieval, "create_embedding", lambda text: [1.0, 0.0])

    assert retrieval.search_code("anything", repo_path="/missing") == []
