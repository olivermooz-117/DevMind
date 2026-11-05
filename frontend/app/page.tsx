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

type Mode = "explain" | "search";

export default function Home() {
  const [repoPath, setRepoPath] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState("Ready to work");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<Mode>("explain");
  const [indexed, setIndexed] = useState(false);
  const [filesIndexed, setFilesIndexed] = useState(0);
  const [chunksIndexed, setChunksIndexed] = useState(0);
  const [activeNav, setActiveNav] = useState("Overview");

  async function callApi(path: string, body: object) {
    const response = await fetch(`/api/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Request failed");
    }

    return data;
  }

  async function ingestRepository() {
    if (!repoPath.trim()) return;

    setBusy(true);
    setStatus("Indexing repository...");
    setAnswer("");
    setSources([]);
    setResults([]);

    try {
      const data = await callApi("ingest", {
        repo_path: repoPath.trim(),
      });

      setIndexed(true);
      setFilesIndexed(data.files_discovered || 0);
      setChunksIndexed(data.chunks_indexed || 0);
      setStatus("Repository indexed successfully");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Indexing failed");
    } finally {
      setBusy(false);
    }
  }

  async function runAssistant() {
    if (!question.trim()) return;

    setBusy(true);
    setAnswer("");
    setSources([]);
    setResults([]);

    try {
      if (mode === "explain") {
        setStatus("Understanding your codebase...");

        const data = await callApi("explain", {
          question: question.trim(),
          repo_path: repoPath || undefined,
        });

        setAnswer(data.answer || "No explanation was returned.");
        setSources(data.sources || []);
        setStatus("Explanation generated");
      } else {
        setStatus("Searching indexed code...");

        const data = await callApi("search", {
          query: question.trim(),
          repo_path: repoPath || undefined,
          limit: 8,
        });

        setResults(data.results || []);
        setStatus(`Found ${data.results?.length || 0} matching code chunks`);
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  function selectMode(nextMode: Mode) {
    setMode(nextMode);
    setAnswer("");
    setSources([]);
    setResults([]);
    setStatus("Ready to work");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div>
            <div className="brand-name">DevMind<span>.</span></div>
            <div className="brand-caption">ENGINEERING INTELLIGENCE</div>
          </div>
        </div>

        <div className="sidebar-label">WORKSPACE</div>

        <nav className="nav-list">
          {[
            { name: "Overview", icon: "◫" },
            { name: "Code Assistant", icon: "✳" },
            { name: "Semantic Search", icon: "⌕" },
            { name: "Repository", icon: "⌘" },
          ].map((item) => (
            <button
              key={item.name}
              className={`nav-item ${activeNav === item.name ? "active" : ""}`}
              onClick={() => {
                setActiveNav(item.name);
                if (item.name === "Semantic Search") selectMode("search");
                if (item.name === "Code Assistant") selectMode("explain");
              }}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.name}
              {activeNav === item.name && <span className="nav-indicator" />}
            </button>
          ))}
        </nav>

        <div className="sidebar-label repository-label">CURRENT REPOSITORY</div>

        <div className="repo-card">
          <div className="repo-icon">⌘</div>
          <div className="repo-details">
            <strong>Local workspace</strong>
            <span>{repoPath.split("/").filter(Boolean).pop() || "No repository"}</span>
          </div>
          <span className="repo-status" />
        </div>

        <div className="sidebar-bottom">
          <div className="privacy-card">
            <div className="privacy-icon">◈</div>
            <strong>Private by design</strong>
            <p>Your code and AI inference stay on your machine.</p>
            <div className="privacy-status">
              <span /> LOCAL INFERENCE
            </div>
          </div>

          <div className="profile">
            <div className="avatar">DM</div>
            <div>
              <strong>DevMind</strong>
              <span>Local environment</span>
            </div>
            <span className="profile-menu">···</span>
          </div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span> {activeNav}
          </div>
          <div className="topbar-right">
            <div className="connection">
              <span className="connection-dot" />
              LOCAL WORKSPACE
            </div>
            <div className="topbar-divider" />
            <div className="topbar-avatar">D</div>
          </div>
        </header>

        <div className="content">
          <section className="welcome">
            <div>
              <div className="eyebrow"><span /> YOUR LOCAL AI ENGINEERING WORKSPACE</div>
              <h1>Build with <span>understanding.</span></h1>
              <p>
                Explore your codebase, discover connections, and understand
                your software with private local AI.
              </p>
            </div>
            <div className="welcome-decoration">
              <div className="decoration-ring ring-one" />
              <div className="decoration-ring ring-two" />
              <div className="decoration-center">D</div>
            </div>
          </section>

          <section className="stats-grid">
            <article className="stat-card">
              <div className="stat-top">
                <span>Repository status</span>
                <span className="stat-icon">⌘</span>
              </div>
              <div className="stat-value">
                {indexed ? "Indexed" : "Not indexed"}
              </div>
              <div className="stat-foot">
                <span className={indexed ? "positive" : "neutral"}>
                  {indexed ? "● Ready" : "● Awaiting ingestion"}
                </span>
              </div>
            </article>

            <article className="stat-card">
              <div className="stat-top">
                <span>Files discovered</span>
                <span className="stat-icon">▤</span>
              </div>
              <div className="stat-value">{filesIndexed}</div>
              <div className="stat-foot">Repository source files</div>
            </article>

            <article className="stat-card">
              <div className="stat-top">
                <span>Code chunks</span>
                <span className="stat-icon">⌗</span>
              </div>
              <div className="stat-value">{chunksIndexed}</div>
              <div className="stat-foot">Stored for semantic retrieval</div>
            </article>

            <article className="stat-card">
              <div className="stat-top">
                <span>AI engine</span>
                <span className="stat-icon">✳</span>
              </div>
              <div className="stat-value engine-value">Ollama</div>
              <div className="stat-foot"><span className="positive">● Local inference</span></div>
            </article>
          </section>

          <section className="workspace-grid">
            <div className="workspace-main">
              <div className="section-title">
                <div>
                  <div className="section-kicker">INTERACTIVE WORKSPACE</div>
                  <h2>Code intelligence</h2>
                </div>
                <span className="live-label"><span /> READY</span>
              </div>

              <div className="panel assistant-panel">
                <div className="panel-heading">
                  <div className="assistant-icon">✳</div>
                  <div>
                    <h3>AI Code Assistant</h3>
                    <p>Ask questions about your repository</p>
                  </div>
                </div>

                <div className="mode-switch">
                  <button
                    className={mode === "explain" ? "mode-active" : ""}
                    onClick={() => selectMode("explain")}
                  >
                    <span>✳</span> Explain code
                  </button>
                  <button
                    className={mode === "search" ? "mode-active" : ""}
                    onClick={() => selectMode("search")}
                  >
                    <span>⌕</span> Semantic search
                  </button>
                </div>

                <label className="field-label" htmlFor="question">
                  {mode === "explain" ? "WHAT WOULD YOU LIKE TO UNDERSTAND?" : "WHAT ARE YOU LOOKING FOR?"}
                </label>

                <textarea
                  id="question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder={
                    mode === "explain"
                      ? "How does authentication work in this application?"
                      : "Find functions responsible for processing API requests..."
                  }
                  rows={5}
                />

                <div className="assistant-footer">
                  <span>↳ Powered by your local code index</span>
                  <button
                    className="primary-button"
                    onClick={runAssistant}
                    disabled={busy || !question.trim()}
                  >
                    {busy ? "Processing..." : mode === "explain" ? "Generate explanation ↗" : "Search repository ↗"}
                  </button>
                </div>
              </div>

              {(answer || results.length > 0) && (
                <div className="panel response-panel">
                  <div className="response-heading">
                    <div>
                      <div className="section-kicker">LOCAL AI OUTPUT</div>
                      <h3>{answer ? "Code explanation" : "Search results"}</h3>
                    </div>
                    <span className="result-count">
                      {answer ? `${sources.length} sources` : `${results.length} matches`}
                    </span>
                  </div>

                  {answer && <pre className="answer-content">{answer}</pre>}

                  {sources.map((source, index) => (
                    <div className="source-row" key={`${source.file_path}-${index}`}>
                      <div className="file-symbol">⌘</div>
                      <div className="source-info">
                        <strong>{source.file_path}</strong>
                        <span>{source.symbol}</span>
                      </div>
                      <span className="score">
                        {(source.score * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}

                  {results.map((result, index) => (
                    <article className="search-result" key={`${result.file_path}-${index}`}>
                      <div className="result-meta">
                        <strong>{result.file_path}</strong>
                        <span>{result.language} · {result.symbol}</span>
                      </div>
                      <pre>{result.content}</pre>
                      <div className="result-score">
                        Similarity: {(result.score * 100).toFixed(1)}%
                      </div>
                    </article>
                  ))}
                </div>
              )}

              <div className="panel repository-panel">
                <div className="panel-heading">
                  <div className="repository-icon">⌘</div>
                  <div>
                    <h3>Repository indexing</h3>
                    <p>Connect your local project to DevMind</p>
                  </div>
                </div>

                <label className="field-label" htmlFor="repo">
                  LOCAL REPOSITORY PATH
                </label>

                <div className="repo-input-row">
                  <input
                    id="repo"
                    value={repoPath}
                    onChange={(event) => setRepoPath(event.target.value)}
                    placeholder="/home/username/project"
                  />
                  <button
                    className="primary-button"
                    onClick={ingestRepository}
                    disabled={busy || !repoPath.trim()}
                  >
                    {busy ? "Working..." : "Index repository ↗"}
                  </button>
                </div>

                <p className="field-hint">
                  Enter an absolute directory path accessible to the backend.
                  This is a local folder, not a GitHub URL.
                </p>
              </div>
            </div>

            <aside className="workspace-side">
              <div className="panel side-panel">
                <div className="side-heading">
                  <h3>System environment</h3>
                  <span className="system-icon">◈</span>
                </div>

                <div className="system-row">
                  <span>Inference provider</span>
                  <strong>Ollama</strong>
                </div>
                <div className="system-row">
                  <span>Chat model</span>
                  <strong>llama3.2:1b</strong>
                </div>
                <div className="system-row">
                  <span>Embedding model</span>
                  <strong>nomic-embed-text</strong>
                </div>
                <div className="system-row">
                  <span>Vector storage</span>
                  <strong>SQLite</strong>
                </div>
                <div className="system-row">
                  <span>Inference mode</span>
                  <strong className="positive">Local</strong>
                </div>

                <div className="system-note">
                  <span>✓</span>
                  All model inference is performed locally.
                </div>
              </div>

              <div className="panel quick-panel">
                <div className="side-heading">
                  <h3>Suggested prompts</h3>
                  <span className="sparkle">✳</span>
                </div>

                {[
                  "Explain the overall architecture",
                  "Find API endpoints",
                  "Where are errors handled?",
                  "Explain the database layer",
                ].map((prompt) => (
                  <button
                    className="prompt-button"
                    key={prompt}
                    onClick={() => {
                      setQuestion(prompt);
                      setMode("explain");
                      setActiveNav("Code Assistant");
                    }}
                  >
                    <span>↗</span>{prompt}
                  </button>
                ))}
              </div>

              <div className="status-card">
                <div className="status-card-top">
                  <span className="status-pulse" />
                  WORKSPACE STATUS
                </div>
                <strong>{busy ? "Processing request" : status}</strong>
                <p>
                  {busy
                    ? "Your local AI engine is working."
                    : "DevMind is ready for your next engineering task."}
                </p>
              </div>
            </aside>
          </section>

          <footer className="footer">
            <span>DEVMIND © 2026</span>
            <span>LOCAL AI · PRIVATE ENGINEERING · BUILT FOR DEVELOPERS</span>
          </footer>
        </div>
      </section>
    </main>
  );
}
