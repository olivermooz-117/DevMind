"""Retrieval evaluation with Hit@5, MRR, and multi-seed variance."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from harness.config import DEFAULT_REPO, QUESTIONS_PATH, RESULTS_DIR, TOP_K, SEEDS
from harness.metrics import hit_at_k, mean_std, reciprocal_rank

from devmind.retrieval import search_code


def _load_questions():
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def _clean_retrieved(results, limit=TOP_K):
    seen = []
    for r in results:
        path = r["file_path"]
        if path.startswith("evaluation/") or path in seen:
            continue
        seen.append(path)
        if len(seen) >= limit:
            break
    return seen


def run_once(repo_path: str, seed: int | None = None) -> dict:
    questions = _load_questions()
    hits = 0
    mrr_sum = 0.0
    rows = []

    t0 = time.time()
    for item in questions:
        results = search_code(item["question"], repo_path=repo_path, limit=50)
        retrieved = _clean_retrieved(results)
        expected = set(item["expected_files"])
        rr = reciprocal_rank(retrieved, expected)
        hit = hit_at_k(retrieved, expected, TOP_K)
        hits += int(hit)
        mrr_sum += rr
        rows.append({
            "question": item["question"],
            "expected": list(expected),
            "retrieved": retrieved,
            "hit@5": hit,
            "rr": rr,
        })
    elapsed = time.time() - t0
    n = len(questions)
    return {
        "seed": seed,
        "hit@5": hits / n,
        "mrr": mrr_sum / n,
        "n": n,
        "seconds": round(elapsed, 2),
        "rows": rows,
    }


def run_with_seeds(repo_path: str | None = None, seeds: list[int] | None = None) -> dict:
    repo_path = repo_path or DEFAULT_REPO
    seeds = seeds or SEEDS
    runs = [run_once(repo_path, seed=s) for s in seeds]
    hit_vals = [r["hit@5"] for r in runs]
    mrr_vals = [r["mrr"] for r in runs]
    hit_mean, hit_std = mean_std(hit_vals)
    mrr_mean, mrr_std = mean_std(mrr_vals)
    summary = {
        "type": "retrieval",
        "repo_path": repo_path,
        "seeds": seeds,
        "hit@5_mean": round(hit_mean, 4),
        "hit@5_std": round(hit_std, 4),
        "mrr_mean": round(mrr_mean, 4),
        "mrr_std": round(mrr_std, 4),
        "runs": [{k: v for k, v in r.items() if k != "rows"} for r in runs],
    }
    out = RESULTS_DIR / "retrieval_seeds.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    repo = os.environ.get("DEVMIND_REPO_PATH", DEFAULT_REPO)
    result = run_with_seeds(repo)
    print(json.dumps(result, indent=2))
