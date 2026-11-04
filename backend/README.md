# DevMind — Local AI Engineering Workbench

DevMind is a privacy-focused AI engineering workbench designed to run locally using open-source tools and local language models.

The goal is to build an AI-powered developer assistant that can understand codebases, retrieve relevant technical information, explain code, and support software engineering workflows without relying on paid cloud AI APIs.

## Project Vision

DevMind aims to provide:

- Local AI inference using Ollama.
- AI-powered developer conversations.
- Codebase understanding and repository intelligence.
- Retrieval-Augmented Generation (RAG).
- Semantic search across project documentation and source code.
- Code explanation and developer productivity tools.
- Automated testing and reproducible development workflows.

## Technology Stack

| Component | Technology |
|---|---|
| AI inference | Ollama |
| Language model | Llama 3.2 1B |
| Backend | Python, Flask |
| HTTP client | Requests |
| Backend testing | pytest |
| Frontend | Next.js, TypeScript (planned) |
| Code parsing | Tree-sitter (planned) |
| Vector storage | PostgreSQL, pgvector (planned) |

## Current Implementation

The initial backend is operational.

Implemented:
- Flask health endpoint.
- Chat endpoint connected to local Ollama.
- Prompt validation.
- Timeout handling.
- Ollama connection error handling.
- HTTP request error handling.
- Automated backend tests.

Current automated test result: **8 passed**.

## Running Locally

### Prerequisites

- Python 3
- Ollama
- Llama 3.2 1B model

Pull the model:

```bash
ollama pull llama3.2:1b