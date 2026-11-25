import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DEVMIND_DATA_DIR", "/tmp/devmind-test-data")

from app import app
from devmind.security import resolve_repo_path


def make_dirs(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    return allowed, outside


def test_ingest_rejects_path_outside_allowed_root(tmp_path, monkeypatch):
    allowed, outside = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    response = app.test_client().post(
        "/ingest", json={"repo_path": str(outside)}
    )

    assert response.status_code == 400
    assert "outside the allowed directory" in response.json["error"]


def test_ingest_rejects_parent_traversal(tmp_path, monkeypatch):
    allowed, _ = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    response = app.test_client().post(
        "/ingest", json={"repo_path": str(allowed / ".." / "outside")}
    )

    assert response.status_code == 400


def test_resolves_repository_inside_allowed_root(tmp_path, monkeypatch):
    allowed, _ = make_dirs(tmp_path)
    repo = allowed / "project"
    repo.mkdir()
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    assert resolve_repo_path(str(repo)) == repo.resolve()


def test_rejects_symlink_escape(tmp_path, monkeypatch):
    allowed, outside = make_dirs(tmp_path)
    (allowed / "escaped").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    response = app.test_client().post(
        "/ingest", json={"repo_path": str(allowed / "escaped")}
    )

    assert response.status_code == 400
    assert "outside the allowed directory" in response.json["error"]
    assert str(outside) not in response.get_data(as_text=True)


def test_rejects_missing_allowed_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(tmp_path / "missing"))

    with pytest.raises(ValueError, match="Repository access is not configured"):
        resolve_repo_path(str(tmp_path))


def test_rejects_non_directory_allowed_root(tmp_path, monkeypatch):
    configured_root = tmp_path / "not-a-directory"
    configured_root.write_text("not a directory")
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(configured_root))

    with pytest.raises(ValueError, match="Repository access is not configured"):
        resolve_repo_path(str(repo))


def test_production_requires_explicit_allowed_root(tmp_path, monkeypatch):
    monkeypatch.delenv("DEVMIND_ALLOWED_ROOT", raising=False)
    monkeypatch.setenv("DEVMIND_ENV", "production")

    with pytest.raises(ValueError, match="Repository access is not configured"):
        resolve_repo_path(str(tmp_path))


def test_local_default_is_home_projects(tmp_path, monkeypatch):
    home = tmp_path / "home"
    projects = home / "projects"
    repo = projects / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("DEVMIND_ALLOWED_ROOT", raising=False)
    monkeypatch.delenv("DEVMIND_ENV", raising=False)

    assert resolve_repo_path(str(repo)) == repo.resolve()


def test_search_rejects_path_outside_allowed_root(tmp_path, monkeypatch):
    allowed, outside = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    response = app.test_client().post(
        "/search", json={"query": "x", "repo_path": str(outside)}
    )

    assert response.status_code == 400


def test_ingest_error_details_are_not_leaked(tmp_path, monkeypatch):
    allowed, _ = make_dirs(tmp_path)
    monkeypatch.setenv("DEVMIND_ALLOWED_ROOT", str(allowed))

    with patch("app.ingest_repository", side_effect=RuntimeError("secret detail")):
        response = app.test_client().post(
            "/ingest", json={"repo_path": str(allowed)}
        )

    assert response.status_code == 500
    assert "secret detail" not in response.get_data(as_text=True)
