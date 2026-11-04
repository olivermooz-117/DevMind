from .retrieval import search_code
from .ollama_client import generate_response


def answer_about_code(question, repo_path=None):
    matches = search_code(question, repo_path=repo_path, limit=5)

    if not matches:
        return {
            "answer": (
                "I could not find indexed code relevant to that question. "
                "Please index a repository first."
            ),
            "sources": [],
        }

    context_parts = []

    for index, item in enumerate(matches, start=1):
        context_parts.append(
            f"SOURCE {index}\n"
            f"FILE: {item['file_path']}\n"
            f"LANGUAGE: {item['language']}\n"
            f"SYMBOL: {item['symbol']}\n"
            f"CODE:\n{item['content']}"
        )

    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""
You are DevMind, a local AI software engineering assistant.

Your task is to answer the developer's question using ONLY the
repository context supplied below.

STRICT RULES:
1. Never invent files, functions, classes, variables, or behavior.
2. Only describe implementation details supported by the supplied code.
3. If information is missing, explicitly say that the available
   repository context does not establish it.
4. Distinguish confirmed implementation details from reasonable
   inferences.
5. Do not claim that a function calls another function unless
   the supplied code demonstrates that relationship.
6. Do not repeat the same explanation unnecessarily.
7. Use clear technical language and properly formatted Markdown.
8. Mention relevant source file paths when explaining implementation.
9. If the question cannot be answered from the supplied context,
   say what additional source code would be needed.

RESPONSE FORMAT:
- Start with a direct answer.
- Use numbered steps when explaining a process.
- Use bullet points for important implementation details.
- Use code formatting for filenames, functions, variables, and
  technical identifiers.
- Finish with a short section titled "Sources" listing the
  relevant repository files.

REPOSITORY CONTEXT:
{context}

DEVELOPER QUESTION:
{question}

TECHNICAL ANSWER:
"""

    answer = generate_response(prompt)

    sources = [
        {
            "file_path": item["file_path"],
            "symbol": item["symbol"],
            "score": item["score"],
        }
        for item in matches
    ]

    return {
        "answer": answer.strip(),
        "sources": sources,
    }
