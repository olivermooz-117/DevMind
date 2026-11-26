import importlib.util
from pathlib import Path

HARNESS_PATH = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "harness.py"
)

spec = importlib.util.spec_from_file_location(
    "devmind_eval_harness", HARNESS_PATH
)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_hit_at_five_and_mrr():
    scores = harness.retrieval_metrics(
        ["a.py", "b.py", "c.py", "d.py", "e.py"],
        {"c.py"},
    )

    assert scores["hit@5"] == 1.0
    assert scores["mrr"] == 1 / 3
    assert scores["recall@5"] == 1.0


def test_missing_relevant_file_returns_zero():
    scores = harness.retrieval_metrics(
        ["a.py", "b.py"],
        {"missing.py"},
    )

    assert scores["hit@5"] == 0.0
    assert scores["mrr"] == 0.0
    assert scores["recall@5"] == 0.0


def test_retrieval_metrics_support_multiple_relevant_files():
    scores = harness.retrieval_metrics(
        ["a.py", "b.py", "c.py"],
        {"b.py", "c.py"},
    )

    assert scores["hit@5"] == 1.0
    assert scores["recall@5"] == 1.0
    assert scores["mrr"] == 0.5


def test_retrieval_metrics_respect_top_k():
    scores = harness.retrieval_metrics(
        ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
        {"f.py"},
        k=5,
    )

    assert scores["hit@5"] == 0.0


def test_bootstrap_is_reproducible():
    questions = [{"question": str(i)} for i in range(20)]

    first = harness.bootstrap_sample(questions, seed=42)
    second = harness.bootstrap_sample(questions, seed=42)

    assert first == second


def test_different_seeds_can_change_bootstrap_sample():
    questions = [{"question": str(i)} for i in range(100)]

    first = harness.bootstrap_sample(questions, seed=11)
    second = harness.bootstrap_sample(questions, seed=99)

    assert first != second


def test_answer_metrics_measure_expected_term_coverage():
    scores = harness.answer_metrics(
        "The application uses Ollama and SQLite.",
        ["Ollama", "SQLite", "PostgreSQL"],
    )

    assert scores["term_recall"] == 2 / 3
    assert scores["matched_terms"] == ["ollama", "sqlite"]
    assert scores["missing_terms"] == ["postgresql"]


def test_prompt_variants_are_available():
    assert {
        "baseline",
        "concise",
        "step_by_step",
        "strict_grounding",
    } == set(harness.PROMPT_VARIANTS)


def test_prompt_contains_question_and_evidence():
    results = [{
        "file_path": "backend/app.py",
        "symbol": "health",
        "content": "def health(): return {'status': 'healthy'}",
    }]

    prompt = harness.build_prompt(
        "Where is health implemented?",
        results,
        "baseline",
    )

    assert "Where is health implemented?" in prompt
    assert "backend/app.py" in prompt
    assert "healthy" in prompt


def test_seed_statistics():
    assert harness.stddev([1.0, 1.0, 1.0]) == 0.0
    assert harness.mean([0.0, 1.0]) == 0.5
