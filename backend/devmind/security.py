import os
from pathlib import Path


def resolve_repo_path(raw_path):
    """Resolve a user-supplied repository path and enforce the allowed root.

    When DEVMIND_ALLOWED_ROOT is set, only that directory (and anything
    inside it) may be indexed or queried.
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("repo_path must be a non-empty string")

    path = Path(raw_path.strip()).expanduser().resolve()
    allowed_root = os.getenv("DEVMIND_ALLOWED_ROOT")

    if allowed_root:
        root = Path(allowed_root).expanduser().resolve()
        if path != root and root not in path.parents:
            raise ValueError("Repository path is outside the allowed directory")

    return path
