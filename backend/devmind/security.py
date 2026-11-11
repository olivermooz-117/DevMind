import os
from pathlib import Path


def _allowed_root():
    configured_root = os.getenv("DEVMIND_ALLOWED_ROOT")
    environment = os.getenv("DEVMIND_ENV", "development").strip().lower()

    if configured_root is None:
        if environment in {"production", "prod", "shared"}:
            raise ValueError("Repository access is not configured")
        root = Path.home() / "projects"
    else:
        if not configured_root.strip():
            raise ValueError("Repository access is not configured")
        root = Path(configured_root.strip()).expanduser()

    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("Repository access is not configured") from None

    if not root.is_dir():
        raise ValueError("Repository access is not configured")

    return root


def resolve_repo_path(raw_path):
    """Resolve a repository path under a configured, existing allowed root.

    Local development defaults to ``~/projects``. Production and shared
    environments must configure ``DEVMIND_ALLOWED_ROOT`` explicitly.
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("repo_path must be a non-empty string")

    allowed_root = _allowed_root()

    try:
        path = Path(raw_path.strip()).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("Repository path is unavailable") from None

    if not path.is_dir():
        raise ValueError("Repository path must be an existing directory")

    if path != allowed_root and allowed_root not in path.parents:
        raise ValueError("Repository path is outside the allowed directory")

    return path
