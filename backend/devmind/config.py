import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DEVMIND_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "devmind.db"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2:1b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
}

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".next",
    ".turbo",
    ".vercel",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "playwright-report",
    "test-results",
    "evaluation-results",
}

# Generated or dependency metadata that adds little value to code retrieval.
IGNORED_FILES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
}

# Keep evaluation implementation code indexable, but never index benchmark
# questions or prompt variants that could leak expected answers.
IGNORED_PATHS = {
    "evaluation/llm_questions.json",
    "evaluation/questions.json",
    "evaluation/prompts/variants.json",
}

MAX_FILE_BYTES = 500_000
MAX_CHUNK_CHARS = 4_000

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "16"))

# Conversation limits
MAX_CONVERSATION_MESSAGES = int(
    os.getenv("DEVMIND_MAX_CONVERSATION_MESSAGES", "50")
)
MAX_CONTEXT_CHUNKS = int(os.getenv("DEVMIND_MAX_CONTEXT_CHUNKS", "5"))

# Retrieval limits
MAX_SEARCH_RESULTS = int(os.getenv("DEVMIND_MAX_SEARCH_RESULTS", "10"))
HYBRID_SEMANTIC_WEIGHT = float(
    os.getenv("DEVMIND_HYBRID_SEMANTIC_WEIGHT", "0.7")
)
HYBRID_KEYWORD_WEIGHT = float(
    os.getenv("DEVMIND_HYBRID_KEYWORD_WEIGHT", "0.3")
)
MAX_RESULTS_PER_FILE = int(os.getenv("DEVMIND_MAX_RESULTS_PER_FILE", "2"))
