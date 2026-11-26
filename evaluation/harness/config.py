"""Shared configuration for the DevMind evaluation harness."""
from pathlib import Path
import os

EVAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = EVAL_ROOT.parent
RESULTS_DIR = EVAL_ROOT / "results"
PROMPTS_DIR = EVAL_ROOT / "prompts"
QUESTIONS_PATH = EVAL_ROOT / "questions.json"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2:1b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# Default repo under test (override with DEVMIND_REPO_PATH)
DEFAULT_REPO = os.getenv(
    "DEVMIND_REPO_PATH",
    str(PROJECT_ROOT),
)

TOP_K = 5
SEEDS = [0, 1, 2]          # variance across seeds
LM_EVAL_LIMIT = 25         # keep small on CPU
LM_EVAL_TASKS = ["hellaswag"]  # single small subset
