"use client";

import {
  useState,
  useEffect,
  useRef,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Source = {
  file_path: string;
  symbol: string;
  start_line?: number | null;
  end_line?: number | null;
  score: number;
};

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  created_at: string;
};

type Conversation = {
  id: string;
  repo_path: string | null;
  title: string;
  created_at: string;
  updated_at: string;
};

type Mode = "chat" | "search";

const BACKEND_BASE = "/api";

function citationKey(source: Source): string {
  if (source.start_line != null) {
    return `[FILE:${source.file_path}:${source.start_line}]`;
  }
  return `[FILE:${source.file_path}]`;
}

function citationHref(source: Source): string {
  const encodedPath = encodeURIComponent(source.file_path);
  const line = source.start_line != null ? source.start_line : "";
  return `/source?file=${encodedPath}&line=${line}`;
}

function copyToClipboard(text: string) {
  if (typeof navigator !== "undefined" && navigator.clipboard) {
    return navigator.clipboard.writeText(text);
  }
  return Promise.reject(new Error("Clipboard not available"));
}

export default function Home() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [repoPath, setRepoPath] = useState("");
  const [question, setQuestion] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [status, setStatus] = useState("Ready to work");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<Mode>("chat");
  const [indexed, setIndexed] = useState(false);
  const [filesIndexed, setFilesIndexed] = useState(0);
  const [chunksIndexed, setChunksIndexed] = useState(0);
  const [activeNav, setActiveNav] = useState("Chat");
const abortControllerRef = useRef<AbortController | null>(null);

  // Load conversations on mount
  useEffect(() => {
    fetch(`${BACKEND_BASE}/conversations`)
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load conversations");
        return response.json();
      })
      .then((data) => {
        setConversations(data.conversations || []);
        if (data.conversations && data.conversations.length > 0 && !activeConversationId) {
          setActiveConversationId(data.conversations[0].id);
        }
      })
      .catch(() => {
        // Conversations endpoint may not be available on older backends
      });
  }, [activeConversationId]);

  async function createNewConversation() {
    try {
      const response = await fetch(`${BACKEND_BASE}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_path: repoPath.trim() || undefined,
        }),
      });

      if (!response.ok) throw new Error("Failed to create conversation");

      const data = await response.json();
      const newConversation: Conversation = {
        id: data.conversation_id,
        repo_path: data.conversation?.repo_path || null,
        title: data.conversation?.title || "New conversation",
        created_at: data.conversation?.created_at || "",
        updated_at: data.conversation?.updated_at || "",
      };

      setConversations([newConversation, ...conversations]);
      setActiveConversationId(newConversation.id);
      setMessages([]);
      setStatus("New conversation started");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to create conversation");
    }
  }

  async function loadConversation(conversationId: string) {
    try {
      const response = await fetch(
        `${BACKEND_BASE}/conversations/${encodeURIComponent(conversationId)}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          setStatus("Conversation not found");
          setActiveConversationId(null);
          setMessages([]);
          return;
        }
        throw new Error("Failed to load conversation");
      }

      const data = await response.json();
      setMessages(data.messages || []);
      setActiveConversationId(conversationId);

      if (data.conversation?.repo_path) {
        setRepoPath(data.conversation.repo_path);
      }

      setStatus("Conversation loaded");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load conversation");
    }
  }

  async function deleteCurrentConversation() {
    if (!activeConversationId) return;

    if (!window.confirm("Delete this conversation?")) return;

    try {
      const response = await fetch(
        `${BACKEND_BASE}/conversations/${encodeURIComponent(activeConversationId)}`,
        { method: "DELETE" }
      );

      if (!response.ok) throw new Error("Failed to delete conversation");

      setConversations(
        conversations.filter((c) => c.id !== activeConversationId)
      );

      const remaining = conversations.filter((c) => c.id !== activeConversationId);
      if (remaining.length > 0) {
        setActiveConversationId(remaining[0].id);
        loadConversation(remaining[0].id);
      } else {
        setActiveConversationId(null);
        setMessages([]);
        setStatus("Conversation deleted");
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to delete conversation");
    }
  }

  async function callApi(path: string, body: object) {
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const response = await fetch(`${BACKEND_BASE}/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    abortControllerRef.current = null;

    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(`Server returned ${response.status} ${response.statusText}`);
    }

    if (!response.ok) {
      throw new Error(data.error || "Request failed");
    }

    return data;
  }

  function cancelRequest() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setBusy(false);
    setStatus("Request cancelled");
  }

  async function ingestRepository() {
    if (!repoPath.trim()) return;

    setBusy(true);
    setStatus("Indexing repository...");
    setIndexed(false);

    try {
      const data = await callApi("ingest", {
        repo_path: repoPath.trim(),
      });

      setIndexed(true);
      setFilesIndexed(data.files_discovered || 0);
      setChunksIndexed(data.chunks_indexed || 0);
      setStatus("Repository indexed successfully");
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setStatus("Request cancelled");
      } else {
        setIndexed(false);
        setStatus(error instanceof Error ? error.message : "Indexing failed");
      }
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage() {
    const text = mode === "chat" ? question.trim() : searchQuery.trim();
    if (!text) return;

    // Add user message optimistically
    const userMessage: Message = {
      id: Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setBusy(true);
    setStatus("Processing...");

    if (mode === "chat") {
      setQuestion("");
    } else {
      setSearchQuery("");
    }

    try {
      const data = await callApi("chat", {
        prompt: text,
        repo_path: repoPath.trim() || undefined,
        conversation_id: activeConversationId || undefined,
      });

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: "assistant",
        content: data.response || "No response was returned.",
        sources: data.sources || [],
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setActiveConversationId(data.conversation_id || activeConversationId);
      setStatus("Response received");
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setStatus("Request cancelled");
      } else {
        setStatus(error instanceof Error ? error.message : "Request failed");
      }
    } finally {
      setBusy(false);
    }
  }

  async function runSearch() {
    const text = searchQuery.trim();
    if (!text) return;

    setBusy(true);
    setStatus("Searching indexed code...");

    try {
      const data = await callApi("search", {
        query: text,
        repo_path: repoPath.trim() || undefined,
        limit: 10,
      });

      const results = data.results || [];

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: "assistant",
        content: `Found ${results.length} matching code chunk${results.length !== 1 ? "s" : ""}.`,
        sources: results.map((r: any) => ({
          file_path: r.file_path,
          symbol: r.symbol,
          start_line: r.start_line,
          end_line: r.end_line,
          score: r.score,
        })),
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setStatus(`Found ${results.length} match${results.length !== 1 ? "es" : ""}`);
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setStatus("Request cancelled");
      } else {
        setStatus(error instanceof Error ? error.message : "Search failed");
      }
    } finally {
      setBusy(false);
    }
  }

  function selectMode(nextMode: Mode) {
    setMode(nextMode);
    setStatus("Ready to work");
  }

  function selectNav(name: string) {
    setActiveNav(name);
    if (name === "Semantic Search") setMode("search");
    if (name === "Chat") setMode("chat");
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

        <div className="sidebar-label">CONVERSATIONS</div>

        <div className="conversation-toolbar">
          <button
            className="primary-button"
            onClick={createNewConversation}
            disabled={busy}
            aria-label="New conversation"
          >
            <span>&#10133;</span> New conversation
          </button>
          {activeConversationId && (
            <button
              className="ghost-button"
              onClick={deleteCurrentConversation}
              disabled={busy}
              aria-label="Delete conversation"
            >
              <span>&#10007;</span>
            </button>
          )}
        </div>

        <nav className="nav-list">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              className={`conv-item ${activeConversationId === conv.id ? "active" : ""}`}
              onClick={() => loadConversation(conv.id)}
              aria-label={conv.title}
            >
              <span className="conv-icon">&#128196;</span>
              <span className="conv-title">{conv.title}</span>
              <span className="conv-updated">
                {new Date(conv.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
              {activeConversationId === conv.id && <span className="nav-indicator" />}
            </button>
          ))}
          {conversations.length === 0 && (
            <div className="empty-conversations">
              No conversations yet. Start one by asking a question.
            </div>
          )}
        </nav>

        <div className="sidebar-label repository-label">REPOSITORY</div>

        <div className="repo-card">
          <div className="repo-icon">&#128193;</div>
          <div className="repo-details">
            <strong>Local workspace</strong>
            <span>{repoPath.split("/").filter(Boolean).pop() || "No repository"}</span>
          </div>
          <span
            className={`repo-status ${indexed ? "indexed" : "not-indexed"}`}
          />
        </div>

        <div className="repo-input-row">
          <input
            id="repo"
            value={repoPath}
            onChange={(event) => setRepoPath(event.target.value)}
            placeholder="/home/username/project"
            aria-label="Repository path"
            aria-describedby="repo-hint"
          />
          <button
            className="primary-button"
            onClick={ingestRepository}
            disabled={busy || !repoPath.trim()}
            aria-label="Index repository"
          >
            {busy ? "Working..." : "Index repository &#10141;"}
          </button>
        </div>

        <p className="field-hint" id="repo-hint">
          Enter an absolute directory path accessible to the backend.
          This is a local folder, not a GitHub URL.
        </p>

        <div className="sidebar-bottom">
          <div className="privacy-card">
            <div className="privacy-icon">&#10016;</div>
            <strong>Private by design</strong>
            <p>Your code and AI inference stay on your machine.</p>
            <div className="privacy-status">
              <span /> LOCAL INFERENCE
            </div>
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
          <section className="workspace-grid">
            <div className="workspace-main">
              <div className="section-title">
                <div>
                  <div className="section-kicker">CODE ASSISTANT</div>
                  <h2>{mode === "chat" ? "Conversational Assistant" : "Semantic Search"}</h2>
                </div>
                <span className="live-label"><span /> READY</span>
              </div>

              <div className="panel assistant-panel">
                <div className="panel-heading">
                  <div className="assistant-icon">&#10016;</div>
                  <div>
                    <h3>{mode === "chat" ? "AI Code Assistant" : "Code Search"}</h3>
                    <p>
                      {mode === "chat"
                        ? "Ask questions about your repository with source citations"
                        : "Search for code using semantic similarity"}
                    </p>
                  </div>
                </div>

                <div className="mode-switch">
                  <button
                    className={mode === "chat" ? "mode-active" : ""}
                    onClick={() => selectMode("chat")}
                    aria-label="Conversational chat mode"
                    aria-pressed={mode === "chat"}
                  >
                    <span>&#10016;</span> Chat
                  </button>
                  <button
                    className={mode === "search" ? "mode-active" : ""}
                    onClick={() => selectMode("search")}
                    aria-label="Semantic search mode"
                    aria-pressed={mode === "search"}
                  >
                    <span>&#10177;</span> Search
                  </button>
                </div>

                <label className="field-label" htmlFor="assistant-input">
                  {mode === "chat" ? "WHAT WOULD YOU LIKE TO ASK?" : "WHAT ARE YOU LOOKING FOR?"}
                </label>

                <textarea
                  id="assistant-input"
                  value={mode === "chat" ? question : searchQuery}
                  onChange={(event) => {
                    if (mode === "chat") setQuestion(event.target.value);
                    else setSearchQuery(event.target.value);
                  }}
                  placeholder={
                    mode === "chat"
                      ? "Explain how authentication works in this project..."
                      : "Find functions responsible for processing API requests..."
                  }
                  rows={4}
                  aria-label={
                    mode === "chat" ? "Question about your code" : "Search query"
                  }
                />

                <div className="assistant-footer">
                  <span>&#8594; Powered by your local code index</span>
                  <div className="action-buttons">
                    <button
                      className="cancel-button"
                      onClick={cancelRequest}
                      disabled={!busy}
                      aria-label="Cancel request"
                    >
                      &#10007; Cancel
                    </button>
                    <button
                      className="primary-button"
                      onClick={mode === "chat" ? sendMessage : runSearch}
                      disabled={busy || !(mode === "chat" ? question.trim() : searchQuery.trim())}
                      aria-label={
                        mode === "chat" ? "Send message" : "Search repository"
                      }
                    >
                      {busy ? "Processing..." : mode === "chat" ? "Send &#10141;" : "Search &#10141;"}
                    </button>
                  </div>
                </div>
              </div>

              {messages.length > 0 && (
                <div className="chat-messages-panel" role="log" aria-label="Conversation">
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`message ${msg.role}`}
                    >
                      <div className="message-header">
                        <span className="message-role">
                          {msg.role === "user" ? "You" : "DevMind"}
                        </span>
                        <span className="message-time">
                          {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                        {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                          <span className="source-badge">
                            {msg.sources.length} source{msg.sources.length !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                      <div className="message-content">
                        {msg.role === "assistant" ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        ) : (
                          msg.content
                        )}
                      </div>
                      {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                        <div className="message-sources">
                          <strong>Sources:</strong>
                          <ul>
                            {msg.sources.map((source, index) => (
                              <li key={index} className="source-item">
                                <button
                                  className="source-citation"
                                  onClick={() => {
                                    window.open(citationHref(source), "_blank");
                                  }}
                                  aria-label={`Open ${source.file_path} at line ${source.start_line || "start"}`}
                                >
                                  &#10133; {source.file_path}
                                  {source.start_line != null && (
                                    <span>:#{source.start_line}</span>
                                  )}
                                </button>
                                <span className="source-symbol">
                                  {source.symbol}
                                  {source.start_line != null && source.end_line != null && (
                                    <span> (lines {source.start_line}-{source.end_line})</span>
                                  )}
                                </span>
                                <button
                                  className="copy-button"
                                  onClick={() => copyToClipboard(source.file_path)}
                                  aria-label={`Copy ${source.file_path} to clipboard`}
                                >
                                  &#10003;
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {messages.length === 0 && !busy && (
                <div className="empty-state">
                  <div className="empty-icon">&#10016;</div>
                  <h3>Start a conversation</h3>
                  <p>
                    Ask a question about your indexed repository to get
                    started. DevMind will search your code index and provide
                    answers with source citations.
                  </p>
                </div>
              )}
            </div>

            <aside className="workspace-side">
              <div className="panel side-panel">
                <div className="side-heading">
                  <h3>System environment</h3>
                  <span className="system-icon">&#10016;</span>
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
                  <span>&#10003;</span>
                  All model inference is performed locally.
                </div>
              </div>

              {messages.length > 0 && (
                <div className="panel quick-panel">
                  <div className="side-heading">
                    <h3>Quick actions</h3>
                    <span className="sparkle">&#10016;</span>
                  </div>
                  <button
                    className="prompt-button"
                    onClick={createNewConversation}
                    disabled={busy}
                  >
                    <span>&#10133;</span> New conversation
                  </button>
                  {activeConversationId && (
                    <button
                      className="prompt-button"
                      onClick={deleteCurrentConversation}
                      disabled={busy}
                    >
                      <span>&#10007;</span> Delete conversation
                    </button>
                  )}
                </div>
              )}

              <div className="panel status-panel">
                <div className="side-heading">
                  <h3>Workspace status</h3>
                  <span className="status-pulse" />
                </div>
                <strong aria-live="polite">{busy ? "Processing request" : status}</strong>
                <p>
                  {busy
                    ? "Your local AI engine is working."
                    : "DevMind is ready for your next engineering task."}
                </p>
                {indexed && (
                  <div className="stat-row">
                    <span>Files indexed</span>
                    <strong>{filesIndexed}</strong>
                  </div>
                )}
                {indexed && (
                  <div className="stat-row">
                    <span>Code chunks</span>
                    <strong>{chunksIndexed}</strong>
                  </div>
                )}
              </div>
            </aside>
          </section>

          <footer className="footer">
            <span>DEVMIND &#169; 2026</span>
            <span>LOCAL AI &#183; PRIVATE ENGINEERING &#183; BUILT FOR DEVELOPERS</span>
          </footer>
        </div>
      </section>
    </main>
  );
}
