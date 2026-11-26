"""Orchestrate all evaluation tracks and write a CV-friendly summary."""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python -m evaluation.harness.run_all` and direct script use
HERE = Path(__file__).resolve().parent
EVAL_ROOT = HERE.parent
sys.path.insert(0, str(EVAL_ROOT))
sys.path.insert(0, str(EVAL_ROOT.parent / "backend"))

from harness.config import DEFAULT_REPO, RESULTS_DIR
from harness.retrieval_eval import run_with_seeds
from harness.answer_eval import run_answer_eval
from harness.prompt_sensitivity import run_prompt_sensitivity
from harness.lm_eval_runner import run_lm_eval


def main():
    parser = argparse.ArgumentParser(description="DevMind LLM evaluation harness")
    parser.add_argument("--repo", default=os.environ.get("DEVMIND_REPO_PATH", DEFAULT_REPO))
    parser.add_argument("--skip-lm-eval", action="store_true", help="Skip EleutherAI lm-eval (slow on CPU)")
    parser.add_argument("--answer-limit", type=int, default=6)
    parser.add_argument("--lm-limit", type=int, default=25)
    args = parser.parse_args()

    report = {
        "project": "DevMind",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_path": args.repo,
        "tracks": {},
    }

    print("=== 1/4 Retrieval (Hit@5, MRR, seed variance) ===")
    report["tracks"]["retrieval"] = run_with_seeds(args.repo)

    print("=== 2/4 Prompt sensitivity ===")
    report["tracks"]["prompt_sensitivity"] = run_prompt_sensitivity(args.repo)

    print("=== 3/4 Answer + citation eval ===")
    report["tracks"]["answer"] = run_answer_eval(args.repo, limit=args.answer_limit)

    if not args.skip_lm_eval:
        print("=== 4/4 lm-evaluation-harness subset ===")
        report["tracks"]["lm_eval"] = run_lm_eval(limit=args.lm_limit)
    else:
        report["tracks"]["lm_eval"] = {"skipped": True}

    out = RESULTS_DIR / "report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nWrote", out)
    print(json.dumps({
        "retrieval_hit@5": report["tracks"]["retrieval"].get("hit@5_mean"),
        "retrieval_mrr": report["tracks"]["retrieval"].get("mrr_mean"),
        "citation_support": report["tracks"]["answer"].get("citation_support_mean"),
        "keyword_support": report["tracks"]["answer"].get("keyword_support_rate"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
