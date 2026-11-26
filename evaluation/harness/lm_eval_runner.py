"""Thin wrapper: run a small lm-evaluation-harness subset against local Ollama."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness.config import (
    CHAT_MODEL,
    LM_EVAL_LIMIT,
    LM_EVAL_TASKS,
    OLLAMA_URL,
    RESULTS_DIR,
)


def run_lm_eval(
    tasks: list[str] | None = None,
    limit: int | None = None,
    model: str | None = None,
) -> dict:
    tasks = tasks or LM_EVAL_TASKS
    limit = limit if limit is not None else LM_EVAL_LIMIT
    model = model or CHAT_MODEL

    # Ollama exposes OpenAI-compatible chat at /v1
    base_url = f"{OLLAMA_URL.rstrip('/')}/v1/chat/completions"
    model_args = (
        f"model={model},"
        f"base_url={base_url},"
        "num_concurrent=1,"
        "max_retries=2,"
        "tokenized_requests=False"
    )

    cmd = [
        sys.executable, "-m", "lm_eval",
        "--model", "local-chat-completions",
        "--model_args", model_args,
        "--tasks", ",".join(tasks),
        "--limit", str(limit),
        "--batch_size", "1",
        "--output_path", str(RESULTS_DIR / "lm_eval"),
        "--log_samples",
    ]

    env = os.environ.copy()
    env.setdefault("OPENAI_API_KEY", "ollama")  # Ollama ignores key

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    summary = {
        "type": "lm_eval",
        "tasks": tasks,
        "limit": limit,
        "model": model,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    out = RESULTS_DIR / "lm_eval_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run_lm_eval(), indent=2))
