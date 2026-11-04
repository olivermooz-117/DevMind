import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from devmind.retrieval import search_code


def main():
    repo_path = os.environ.get("DEVMIND_REPO_PATH")

    if not repo_path:
        print("Set DEVMIND_REPO_PATH to the absolute path of an indexed repository.")
        return 1

    questions_path = Path(__file__).with_name("questions.json")
    questions = json.loads(questions_path.read_text(encoding="utf-8"))

    hits = 0

    for item in questions:
        results = search_code(item["question"], repo_path=repo_path, limit=5)
        found = bool(results)
        hits += int(found)

        print(f"\nQuestion: {item['question']}")
        print(f"Expected topic: {item['expected_topic']}")
        print(f"Retrieved results: {len(results)}")

        for result in results:
            print(f"  {result['file_path']} — score {result['score']}")

    print(f"\nRetrieval availability: {hits}/{len(questions)}")
    print("This is a basic retrieval smoke test, not a full answer-quality benchmark.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
