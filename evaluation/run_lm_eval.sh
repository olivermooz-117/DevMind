#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODEL="${CHAT_MODEL:-llama3.2:1b}"
TOKENIZER="${LM_EVAL_TOKENIZER:-unsloth/Llama-3.2-1B-Instruct}"
BASE_URL="${LM_EVAL_BASE_URL:-http://127.0.0.1:11434/v1/completions}"
LIMIT="${LM_EVAL_LIMIT:-20}"
SEED="${LM_EVAL_SEED:-42}"

mkdir -p evaluation-results/lm-eval

python -m lm_eval \
  --model local-completions \
  --model_args "model=${MODEL},tokenizer=${TOKENIZER},base_url=${BASE_URL},tokenized_requests=False" \
  --tasks gsm8k \
  --num_fewshot 0 \
  --limit "$LIMIT" \
  --batch_size 1 \
  --seed "$SEED" \
  --output_path "evaluation-results/lm-eval/gsm8k-${SEED}"

echo "Benchmark completed."
echo "Model: $MODEL"
echo "Tokenizer: $TOKENIZER"
echo "Task: GSM8K"
echo "Samples: $LIMIT"
echo "Seed: $SEED"
echo "Results: evaluation-results/lm-eval/"
