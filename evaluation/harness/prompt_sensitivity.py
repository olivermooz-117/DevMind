"""Measure sensitivity of retrieval + answers to prompt wording variants."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from harness.config import DEFAULT_REPO, PROMPTS_DIR, RESULTS_DIR, TOP_K
from harness.metrics import hit_at_k, mean_std, reciprocal_rank

from devmind.retrieval import search_code


def _clean(results):
    seen = []
    for r in results:
        p = r["file_path"]
        if p.startswith("evaluation/") or p in seen:
            continue
        seen.append(p)
        if len(seen) >= TOP_K:
            break
    return seen


def run_prompt_sensitivity(repo_path: str | None = None) -> dict:
    repo_path = repo_path or DEFAULT_REPO
    variants_path = PROMPTS_DIR / "variants.json"
    variants = json.loads(variants_path.read_text(encoding="utf-8"))

    group_stats = []
    for group in variants:
        expected = set(group["expected_files"])
        scores_hit = []
        scores_mrr = []
        detail = []
        for wording in group["wordings"]:
            retrieved = _clean(search_code(wording, repo_path=repo_path, limit=50))
            h = hit_at_k(retrieved, expected, TOP_K)
            rr = reciprocal_rank(retrieved, expected)
            scores_hit.append(h)
            scores_mrr.append(rr)
            detail.append({"wording": wording, "retrieved": retrieved, "hit@5": h, "rr": rr})
        hm, hs = mean_std(scores_hit)
        mm, ms = mean_std(scores_mrr)
        group_stats.append({
            "id": group["id"],
            "hit@5_mean": round(hm, 4),
            "hit@5_std": round(hs, 4),
            "mrr_mean": round(mm, 4),
            "mrr_std": round(ms, 4),
            "variants": detail,
        })

    summary = {
        "type": "prompt_sensitivity",
        "repo_path": repo_path,
        "groups": group_stats,
    }
    out = RESULTS_DIR / "prompt_sensitivity.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run_prompt_sensitivity(), indent=2))
