# Evaluation Plan

DevMind should be evaluated on:

- Repository ingestion coverage: supported files discovered and chunks indexed.
- Retrieval availability: whether relevant chunks are returned.
- Retrieval precision: whether returned chunks are relevant.
- MRR: rank of the first relevant result.
- Answer correctness: whether explanations match repository behavior.
- Citation accuracy: whether cited paths actually support the answer.
- Unsupported-answer rate: how often the assistant invents unsupported details.
- Latency: ingestion, embedding, retrieval, and generation time.

The initial `evaluation/evaluate.py` script is a retrieval smoke test only.
A proper benchmark requires manually reviewed expected files and expected answers.
