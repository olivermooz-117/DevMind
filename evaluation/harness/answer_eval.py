"""RAG answer evaluation: keyword support + citation accuracy."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from harness.config import DEFAULT_REPO, QUESTIONS_PATH, RESULTS_DIR, TOP_K
from harness.metrics import citation_support_rate, contains_any

from devmind.assistant import answer_about_code
from devmind.retrieval import search_code


def _load_questions():
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    # Optional keywords for weak answer checks
    for item in data:
        item.setdefault("must_mention", [
            Path(p).stem.replace("_", " ") for p in item["expected_files"]
        ])
    return data


def run_answer_eval(repo_path: str | None = None, limit: int | None = None) -> dict:
    repo_path = repo_path or DEFAULT_REPO
    questions = _load_questions()
    if limit:
        questions = questions[:limit]

    rows = []
    citation_scores = []
    support_scores = []
    t0 = time.time()

    for item in questions:
        q = item["question"]
        result = answer_about_code(q, repo_path=repo_path)
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        cited = [s["file_path"] for s in sources]

        retrieved = [
            r["file_path"]
            for r in search_code(q, repo_path=repo_path, limit=TOP_K)
            if not r["file_path"].startswith("evaluation/")
        ]

        cite_score = citation_support_rate(cited, retrieved)
        supported = contains_any(answer, item.get("must_mention", []))
        citation_scores.append(cite_score)
        support_scores.append(1.0 if supported else 0.0)

        rows.append({
            "question": q,
            "cited": cited,
            "retrieved": retrieved,
            "citation_support": round(cite_score, 3),
            "keyword_supported": supported,
            "answer_preview": answer[:240],
        })

    n = max(len(rows), 1)
    summary = {
        "type": "answer",
        "repo_path": repo_path,
        "n": len(rows),
        "citation_support_mean": round(sum(citation_scores) / n, 4),
        "keyword_support_rate": round(sum(support_scores) / n, 4),
        "seconds": round(time.time() - t0, 2),
        "rows": rows,
    }
    out = RESULTS_DIR / "answer_eval.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    limit = int(os.environ.get("DEVMIND_EVAL_LIMIT", "6"))
    print(json.dumps(run_answer_eval(limit=limit), indent=2))
