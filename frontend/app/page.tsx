"use client";

import { useState } from "react";

type Source = {
  file_path: string;
  symbol: string;
  score: number;
};

type SearchResult = Source & {
  language: string;
  content: string;
};

export default function Home() {
  const [repoPath, setRepoPath] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState("Ready");
  const [busy, setBusy] = useState(false);

  async function callApi(path: string, body: object) {
    const response = await fetch(`/api/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Request failed");
    }

    return data;
  }

  async function ingestRepository() {
    setBusy(true);
    setStatus("Indexing repository...");
    setAnswer("");
    setSources([]);

    try {
      const data = await callApi("ingest", { repo_path: repoPath });
      setStatus(
        `Indexed ${data.chunks_indexed} code chunks from ${data.files_discovered} files.`
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Indexing failed");
    } finally {
      setBusy(false);
    }
  }

  async function askQuestion() {
    if (!question.trim()) return;

    setBusy(true);
    setStatus("Searching code and generating answer...");
    setAnswer("");
    setSources([]);

    try {
      const data = await callApi("explain", {
        question,
        repo_path: repoPath || undefined
      });
      setAnswer(data.answer);
      setSources(data.sources || []);
      setStatus("Answer ready");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  async function searchCode() {
    if (!question.trim()) return;

    setBusy(true);
    setStatus("Searching repository...");

    try {
      const data = await callApi("search", {
        query: question,
        repo_path: repoPath || undefined,
        limit: 8
      });
      setResults(data.results || []);
      setStatus(`Found ${data.results?.length || 0} matching code chunks.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="brand">DEVMIND<span>.</span></div>
          <p>LOCAL AI ENGINEERING WORKBENCH</p>
        </div>
        <div className="local-badge"><i /> LOCAL WORKSPACE</div>
      </header>

      <section className="hero">
        <div className="eyebrow">PRIVATE BY DESIGN · POWERED BY OLLAMA</div>
        <h1>Understand your codebase.</h1>
        <p>
          Index a local repository, search code by meaning, and ask questions
          about how your software works.
        </p>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="number">01</span>
            <h2>Repository workspace</h2>
          </div>
          <span className="tag">INGESTION</span>
        </div>

        <label htmlFor="repo">Absolute repository folder path</label>
        <div className="input-row">
          <input
            id="repo"
            value={repoPath}
            onChange={(event) => setRepoPath(event.target.value)}
            placeholder="/home/username/my-project"
          />
          <button disabled={busy || !repoPath.trim()} onClick={ingestRepository}>
            {busy ? "Working..." : "Index repository"}
          </button>
        </div>
        <p className="hint">
          Enter a folder path accessible to the backend process, not a GitHub URL.
        </p>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="number">02</span>
            <h2>Ask your codebase</h2>
          </div>
          <span className="tag">RAG ASSISTANT</span>
        </div>

        <label htmlFor="question">Question or semantic search query</label>
        <textarea
          id="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Where is authentication handled? How does the API validate input?"
          rows={4}
        />
        <div className="actions">
          <button disabled={busy || !question.trim()} onClick={askQuestion}>
            Explain code
          </button>
          <button
            className="secondary"
            disabled={busy || !question.trim()}
            onClick={searchCode}
          >
            Search code
          </button>
        </div>
      </section>

      <section className="status-line">
        <span className="status-dot" />
        <span>{status}</span>
      </section>

      {answer && (
        <section className="panel output">
          <div className="section-heading">
            <h2>AI explanation</h2>
            <span className="tag">LOCAL MODEL</span>
          </div>
          <pre className="answer">{answer}</pre>
          {sources.length > 0 && (
            <>
              <h3>Retrieved source files</h3>
              {sources.map((source, index) => (
                <div className="source" key={`${source.file_path}-${index}`}>
                  <strong>{source.file_path}</strong>
                  <span>{source.symbol} · similarity {source.score}</span>
                </div>
              ))}
            </>
          )}
        </section>
      )}

      {results.length > 0 && (
        <section className="panel output">
          <div className="section-heading">
            <h2>Semantic search results</h2>
            <span className="tag">{results.length} MATCHES</span>
          </div>
          {results.map((result, index) => (
            <article className="result" key={`${result.file_path}-${index}`}>
              <div className="result-meta">
                <strong>{result.file_path}</strong>
                <span>{result.language} · {result.score}</span>
              </div>
              <pre>{result.content}</pre>
            </article>
          ))}
        </section>
      )}

      <footer>
        DEVMIND · LOCAL INFERENCE · LOCAL STORAGE · YOUR CODE STAYS ON YOUR MACHINE
      </footer>
    </main>
  );
}
