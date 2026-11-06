import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from devmind.retrieval import search_code

TOP_K = 5


def reciprocal_rank(retrieved, expected):
    for rank, path in enumerate(retrieved, start=1):
        if path in expected:
            return 1.0 / rank
    return 0.0


def main():
    repo_path = os.environ.get("DEVMIND_REPO_PATH")

    if not repo_path:
        print("Set DEVMIND_REPO_PATH to the path of an already indexed repository.")
        return 1

    repo_path = str(Path(repo_path).expanduser().resolve())
    questions_path = Path(__file__).with_name("questions.json")
    questions = json.loads(questions_path.read_text(encoding="utf-8"))

    hits = 0
    total_reciprocal_rank = 0.0

    for item in questions:
        results = search_code(item["question"], repo_path=repo_path, limit=50)

        # One entry per file, and ignore the evaluation files themselves
        # (questions.json contains the questions, so it would match itself).
        retrieved = []
        for result in results:
            path = result["file_path"]
            if path.startswith("evaluation/") or path in retrieved:
                continue
            retrieved.append(path)
        retrieved = retrieved[:TOP_K]
        score = reciprocal_rank(retrieved, set(item["expected_files"]))

        hits += int(score > 0)
        total_reciprocal_rank += score

        print(f"\nQuestion: {item['question']}")
        print(f"Expected: {', '.join(item['expected_files'])}")
        print(f"Reciprocal rank: {score:.2f}")

        for rank, path in enumerate(retrieved, start=1):
            print(f"  {rank}. {path}")

    total = len(questions)
    print(f"\nhit@{TOP_K}: {hits}/{total}")
    print(f"MRR: {total_reciprocal_rank / total:.3f}")
    print("Retrieval only. Answer correctness still needs manual review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
