"""Reusable retrieval and LLM evaluation harness for DevMind."""

import argparse
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from devmind.config import CHAT_MODEL, OLLAMA_URL
from devmind.retrieval import search_code

TOP_K = 5

PROMPT_VARIANTS = {
    "baseline": (
        "Answer the developer's question using only the supplied "
        "repository evidence. Never invent implementation details."
    ),
    "concise": (
        "Act as a precise senior software engineer. Give a concise "
        "answer supported exclusively by the supplied repository evidence. "
        "Do not guess."
    ),
    "step_by_step": (
        "Analyze the supplied repository evidence carefully. Identify "
        "the relevant implementation, explain how it works step by step, "
        "and never claim anything unsupported by the evidence."
    ),
    "strict_grounding": (
        "You are a source-grounded code analyst. Every factual claim "
        "must be supported by the supplied code. If evidence is missing, "
        "explicitly state that you cannot establish the answer."
    ),
}


def reciprocal_rank(retrieved, expected):
    for rank, path in enumerate(retrieved, start=1):
        if path in expected:
            return 1.0 / rank
    return 0.0


def retrieval_metrics(retrieved, expected, k=TOP_K):
    expected = set(expected)
    retrieved = retrieved[:k]

    relevant = sum(path in expected for path in retrieved)

    return {
        f"hit@{k}": float(relevant > 0),
        f"recall@{k}": relevant / len(expected) if expected else 0.0,
        "mrr": reciprocal_rank(retrieved, expected),
        "precision": relevant / len(retrieved) if retrieved else 0.0,
    }


def retrieve(question, repo_path):
    results = search_code(question, repo_path=repo_path, limit=50)

    filtered_results = []
    paths = []

    for result in results:
        file_path = result["file_path"]

        if file_path.startswith("evaluation/"):
            continue

        if file_path in paths:
            continue

        paths.append(file_path)
        filtered_results.append(result)

    return paths[:TOP_K], filtered_results[:TOP_K]


def build_prompt(question, results, variant="baseline"):
    instruction = PROMPT_VARIANTS[variant]

    context = "\n\n".join(
        f"SOURCE {i}\n"
        f"FILE: {item['file_path']}\n"
        f"SYMBOL: {item.get('symbol', '')}\n"
        f"CODE:\n{item['content'][:1800]}"
        for i, item in enumerate(results[:TOP_K], start=1)
    )

    return f"""{instruction}

Repository evidence:
{context}

Developer question:
{question}

Answer:
"""


def generate_answer(
    prompt, seed, temperature=0.2, max_new_tokens=160
):
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": CHAT_MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "seed": seed,
                "temperature": temperature,
                "num_predict": max_new_tokens,
            },
        },
        timeout=600,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def answer_metrics(answer, expected_terms):
    normalized = answer.casefold()
    expected = [term.casefold() for term in expected_terms]

    matched = [term for term in expected if term in normalized]

    return {
        "term_recall": len(matched) / len(expected) if expected else 0.0,
        "matched_terms": matched,
        "missing_terms": [term for term in expected if term not in matched],
    }


def mean(values):
    return statistics.mean(values) if values else 0.0


def stddev(values):
    return statistics.stdev(values) if len(values) > 1 else 0.0


def bootstrap_sample(items, seed, fraction=1.0):
    """Sample benchmark questions with replacement."""
    rng = random.Random(seed)
    count = max(1, math.ceil(len(items) * fraction))
    return rng.choices(items, k=count)


def evaluate_retrieval(questions, repo_path, seeds, sample_fraction):
    runs = []

    for seed in seeds:
        sample = bootstrap_sample(questions, seed, sample_fraction)
        scores = defaultdict(list)

        for item in sample:
            retrieved, _ = retrieve(item["question"], repo_path)
            metrics = retrieval_metrics(
                retrieved, item["expected_files"]
            )

            for name, value in metrics.items():
                scores[name].append(value)

        runs.append({
            "seed": seed,
            "sample_size": len(sample),
            "metrics": {
                name: mean(values)
                for name, values in scores.items()
            },
        })

    metric_names = runs[0]["metrics"].keys()

    summary = {
        name: {
            "mean": mean([r["metrics"][name] for r in runs]),
            "stddev": stddev([r["metrics"][name] for r in runs]),
            "min": min(r["metrics"][name] for r in runs),
            "max": max(r["metrics"][name] for r in runs),
        }
        for name in metric_names
    }

    return {"runs": runs, "summary": summary}


def evaluate_prompt_sensitivity(
    questions,
    repo_path,
    seeds,
    variants=None,
    max_new_tokens=160,
):
    results = []
    variants = variants or list(PROMPT_VARIANTS)
    total = len(questions) * len(variants) * len(seeds)
    completed = 0

    for item in questions:
        _, retrieved = retrieve(item["question"], repo_path)

        if not retrieved:
            print(
                f"Skipping question with no retrieved evidence: "
                f"{item['question'][:70]}",
                flush=True,
            )
            continue

        for variant in variants:
            for seed in seeds:
                completed += 1
                print(
                    f"[{completed}/{total}] "
                    f"variant={variant} seed={seed} "
                    f"question={item['question'][:65]}",
                    flush=True,
                )

                prompt = build_prompt(
                    item["question"], retrieved, variant
                )
                answer = generate_answer(
                    prompt, seed, max_new_tokens=max_new_tokens
                )

                results.append({
                    "question": item["question"],
                    "prompt_variant": variant,
                    "seed": seed,
                    "max_new_tokens": max_new_tokens,
                    "answer": answer,
                    "metrics": answer_metrics(
                        answer, item.get("expected_terms", [])
                    ),
                })

    grouped = defaultdict(list)

    for result in results:
        grouped[result["prompt_variant"]].append(
            result["metrics"]["term_recall"]
        )

    summary = {
        variant: {
            "mean_term_recall": mean(scores),
            "stddev": stddev(scores),
            "runs": len(scores),
        }
        for variant, scores in grouped.items()
    }

    return {"results": results, "summary": summary}


def load_questions(path):
    questions = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(questions, list) or not questions:
        raise ValueError("Benchmark dataset must be a non-empty JSON list.")

    for item in questions:
        if not item.get("question") or not item.get("expected_files"):
            raise ValueError(
                "Every retrieval question needs question and expected_files."
            )

    return questions


def main():
    parser = argparse.ArgumentParser(
        description="DevMind reusable LLM evaluation harness"
    )

    parser.add_argument("--repo", default=os.getenv("DEVMIND_REPO_PATH"))
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "evaluation/questions.json",
    )
    parser.add_argument(
        "--llm-dataset",
        type=Path,
        default=ROOT / "evaluation/llm_questions.json",
    )
    parser.add_argument("--seeds", nargs="+", type=int,
                        default=[11, 22, 33, 44, 55])
    parser.add_argument("--sample-fraction", type=float, default=1.0)
    parser.add_argument(
        "--llm-limit",
        type=int,
        default=None,
        help="Maximum number of LLM evaluation questions to run.",
    )
    parser.add_argument(
        "--prompt-variants",
        nargs="+",
        choices=list(PROMPT_VARIANTS),
        default=list(PROMPT_VARIANTS),
        help="Prompt variants to evaluate.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=160,
        help="Maximum generated tokens per answer.",
    )
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "evaluation-results/report.json")

    args = parser.parse_args()

    if not args.repo:
        parser.error("Provide --repo or set DEVMIND_REPO_PATH.")

    if not 0 < args.sample_fraction <= 1:
        parser.error("--sample-fraction must be in (0, 1].")

    repo_path = str(Path(args.repo).expanduser().resolve())
    questions = load_questions(args.dataset)

    report = {
        "metadata": {
            "model": CHAT_MODEL,
            "seeds": args.seeds,
            "sample_fraction": args.sample_fraction,
            "top_k": TOP_K,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "retrieval": evaluate_retrieval(
            questions, repo_path, args.seeds, args.sample_fraction
        ),
    }

    if not args.retrieval_only:
        llm_questions = load_questions(args.llm_dataset)
        if args.llm_limit is not None:
            if args.llm_limit < 1:
                parser.error("--llm-limit must be at least 1.")
            llm_questions = llm_questions[:args.llm_limit]

        if args.max_new_tokens < 1:
            parser.error("--max-new-tokens must be at least 1.")

        report["metadata"]["prompt_variants"] = args.prompt_variants
        report["metadata"]["max_new_tokens"] = args.max_new_tokens
        report["metadata"]["llm_question_count"] = len(llm_questions)
        report["prompt_sensitivity"] = evaluate_prompt_sensitivity(
            llm_questions,
            repo_path,
            args.seeds,
            variants=args.prompt_variants,
            max_new_tokens=args.max_new_tokens,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["retrieval"]["summary"], indent=2))

    if "prompt_sensitivity" in report:
        print("\nPrompt sensitivity:")
        print(json.dumps(
            report["prompt_sensitivity"]["summary"], indent=2
        ))

    print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
