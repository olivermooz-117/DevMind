"use client";

import {
  useState,
  useEffect,
  useRef,
  useCallback,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Source = {
  file_path: string;
  symbol: string;
  start_line?: number | null;
  end_line?: number | null;
  score: number;
  repo_path?: string;
};

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  created_at: string;
  streaming?: boolean;
};

type Conversation = {
  id: string;
  repo_path: string | null;
  title: string;
  created_at: string;
  updated_at: string;
};

type RepositoryInfo = {
  repo_path: string;
  chunk_count: number;
  file_count: number;
  embedding_model?: string | null;
  embedding_dimensions?: number | null;
  updated_at?: string | null;
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

function shortRepoLabel(repo_path: string | null): string {
  if (!repo_path) return "No repository";
  const parts = repo_path.split("/").filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : repo_path;
}

export default function Home() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [repoPaths, setRepoPaths] = useState<string[]>([]);
  const [availableRepos, setAvailableRepos] = useState<RepositoryInfo[]>([]);
  const [question, setQuestion] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [status, setStatus] = useState("Ready to work");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [mode, setMode] = useState<Mode>("chat");
  const [indexed, setIndexed] = useState(false);
  const [filesIndexed, setFilesIndexed] = useState(0);
  const [chunksIndexed, setChunksIndexed] = useState(0);
  const [activeNav, setActiveNav] = useState("Chat");
  const [lastError, setLastError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamControllerRef = useRef<ReadableStreamDefaultReader | null>(null);

  // Load conversations and repositories on mount
  useEffect(() => {
    Promise.all([
      fetch(`${BACKEND_BASE}/conversations`)
        .then((r) => r.json())
        .then((data) => setConversations(data.conversations || []))
        .catch(() => {}),
      fetch(`${BACKEND_BASE}/repositories`)
        .then((r) => r.json())
        .then((data) => setAvailableRepos(data.repositories || []))
        .catch(() => {}),
    ]).then(() => {
      if (conversations.length > 0 && !activeConversationId) {
        setActiveConversationId(conversations[0].id);
      }
    });
  }, [activeConversationId, conversations.length]);

  async function createNewConversation() {
    try {
      const response = await fetch(`${BACKEND_BASE}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_path: repoPaths.length > 0 ? repoPaths[0] : undefined,
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
      setLastError(null);
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
        setRepoPaths(data.conversation.repo_path ? [data.conversation.repo_path] : []);
      }

      setStatus("Conversation loaded");
      setLastError(null);
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

  async function exportConversation(format: "json" | "markdown") {
    if (!activeConversationId) return;

    try {
      const response = await fetch(
        `${BACKEND_BASE}/conversations/${encodeURIComponent(activeConversationId)}/export?format=${format}`
      );

      if (!response.ok) throw new Error("Failed to export conversation");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const extension = format === "json" ? "json" : "md";
      const a = document.createElement("a");
      a.href = url;
      a.download = `conversation-${activeConversationId}.${extension}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setStatus(`Conversation exported as ${format.toUpperCase()}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Export failed");
    }
  }

  async function importConversation(file: File) {
    if (file.size > 10 * 1024 * 1024) {
      setStatus("Import file too large (max 10 MB)");
      return;
    }

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      const response = await fetch(`${BACKEND_BASE}/conversations/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Import failed");
      }

      const result = await response.json();
      setConversations([result.conversation, ...conversations]);
      setActiveConversationId(result.conversation_id);
      setMessages(result.conversation.messages || []);
      setStatus("Conversation imported");
      setLastError(null);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Import failed");
    }
  }

  async function ingestRepository() {
    if (repoPaths.length === 0) return;

    setBusy(true);
    setStatus("Indexing repository...");
    setIndexed(false);
    setLastError(null);

    try {
      const data = await fetch(`${BACKEND_BASE}/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_path: repoPaths[0],
          repo_paths: repoPaths,
        }),
      });

      if (!data.ok) {
        const errorData = await data.json();
        throw new Error(errorData.error || "Indexing failed");
      }

      const result = await data.json();
      setIndexed(true);
      setFilesIndexed(result.files_discovered || 0);
      setChunksIndexed(result.chunks_indexed || 0);
      setStatus("Repository indexed successfully");
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setStatus("Request cancelled");
      } else {
        setIndexed(false);
        setStatus(error instanceof Error ? error.message : "Indexing failed");
        setLastError(error instanceof Error ? error.message : "Indexing failed");
      }
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage() {
    const text = mode === "chat" ? question.trim() : searchQuery.trim();
    if (!text) return;

    const userMessage: Message = {
      id: Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setBusy(true);
    setStreaming(true);
    setStatus("Processing...");
    setLastError(null);

    if (mode === "chat") {
      setQuestion("");
    } else {
      setSearchQuery("");
    }

    try {
      const response = await fetch(`${BACKEND_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: text,
          repo_path: repoPaths.length > 0 ? repoPaths[0] : undefined,
          repo_paths: repoPaths.length > 0 ? repoPaths : undefined,
          conversation_id: activeConversationId || undefined,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Request failed");
      }

      const reader = response.body?.getReader();
      streamControllerRef.current = reader || null;

      if (!reader) {
        throw new Error("No response body");
      }

      let fullContent = "";
      let finalSources: Source[] = [];
      let finalConversationId = activeConversationId || undefined;
      let finalCitationKeys: string[] = [];

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunkText = decoder.decode(value, { stream: true });
        const lines = chunkText.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const payload = JSON.parse(line.slice(6));
              fullContent += payload.text || "";

              if (payload.done) {
                finalSources = payload.sources || [];
                finalConversationId = payload.conversation_id || activeConversationId;
                finalCitationKeys = payload.citation_keys || [];
              }
            } catch {
              // Skip malformed SSE data
            }
          }
        }

        // Update the assistant message optimistically with streaming content
        setMessages((prev) => {
          // Remove any existing temporary assistant message
          const filtered = prev.filter(
            (m) => !(m.role === "assistant" && m.streaming)
          );
          return [
            ...filtered,
            {
              id: Date.now(),
              role: "assistant",
              content: fullContent,
              sources: finalSources,
              created_at: new Date().toISOString(),
              streaming: !done,
            },
          ];
        });

        if (done) {
          setActiveConversationId(finalConversationId ?? null);
          setStatus("Response received");
        }
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setStatus("Request cancelled");
      } else {
        const msg = error instanceof Error ? error.message : "Request failed";
        setStatus(msg);
        setLastError(msg);

        // Add an error assistant message
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            role: "assistant",
            content: `Error: ${msg}`,
            created_at: new Date().toISOString(),
          },
        ]);
      }
    } finally {
      setBusy(false);
      setStreaming(false);
      streamControllerRef.current = null;
    }
  }

  function cancelRequest() {
    if (streamControllerRef.current) {
      streamControllerRef.current.cancel().catch(() => {});
      streamControllerRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setBusy(false);
    setStreaming(false);
    setStatus("Request cancelled");
  }

  async function runSearch() {
    const text = searchQuery.trim();
    if (!text) return;

    setBusy(true);
    setStatus("Searching indexed code...");
    setLastError(null);

    try {
      const response = await fetch(`${BACKEND_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: text,
          repo_paths: repoPaths.length > 0 ? repoPaths : undefined,
          limit: 10,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Search failed");
      }

      const data = await response.json();
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
          repo_path: r.repo_path,
        })),
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setStatus(`Found ${results.length} match${results.length !== 1 ? "es" : ""}`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Search failed";
      setStatus(msg);
      setLastError(msg);
    } finally {
      setBusy(false);
    }
  }

  function retryLastAction() {
    if (mode === "chat" && question.trim()) {
      sendMessage();
    } else if (mode === "search" && searchQuery.trim()) {
      runSearch();
    }
  }

  function selectMode(nextMode: Mode) {
    setMode(nextMode);
    setStatus("Ready to work");
    setLastError(null);
  }

  function selectNav(name: string) {
    setActiveNav(name);
    if (name === "Semantic Search") setMode("search");
    if (name === "Chat") setMode("chat");
  }

  function toggleRepoSelection(repoPath: string) {
    setRepoPaths((prev) =>
      prev.includes(repoPath)
        ? prev.filter((p) => p !== repoPath)
        : [...prev, repoPath]
    );
  }

  function clearError() {
    setLastError(null);
  }

  const isMultiRepo = repoPaths.length > 1;

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
            disabled={busy || streaming}
            aria-label="New conversation"
          >
            <span>&#10133;</span> New conversation
          </button>
          {activeConversationId && (
            <>
              <button
                className="ghost-button"
                onClick={() => exportConversation("json")}
                disabled={busy || streaming}
                aria-label="Export conversation as JSON"
                title="Export as JSON"
              >
                &#10063;
              </button>
              <button
                className="ghost-button"
                onClick={() => exportConversation("markdown")}
                disabled={busy || streaming}
                aria-label="Export conversation as Markdown"
                title="Export as Markdown"
              >
                &#10003;
              </button>
              <button
                className="ghost-button"
                onClick={deleteCurrentConversation}
                disabled={busy || streaming}
                aria-label="Delete conversation"
              >
                <span>&#10007;</span>
              </button>
            </>
          )}
        </div>

        <div className="import-export-row" style={{ margin: "0 1rem 1rem 1rem" }}>
          <label htmlFor="import-file" className="import-label">
            Import conversation:
          </label>
          <input
            id="import-file"
            type="file"
            accept=".json"
            onChange={(e) => {
              if (e.target.files?.[0]) {
                importConversation(e.target.files[0]);
                e.target.value = "";
              }
            }}
            disabled={busy || streaming}
            className="import-input"
          />
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

        <div className="sidebar-label repository-label">REPOSITORIES</div>

        <div className="repo-list">
          {availableRepos.map((repo) => {
            const isSelected = repoPaths.includes(repo.repo_path);
            return (
              <button
                key={repo.repo_path}
                className={`repo-item ${isSelected ? "selected" : ""}`}
                onClick={() => toggleRepoSelection(repo.repo_path)}
                aria-label={repo.repo_path}
                aria-pressed={isSelected}
              >
                <span
                  className={`repo-checkbox ${isSelected ? "checked" : ""}`}
                />
                <span className="repo-name">
                  {shortRepoLabel(repo.repo_path)}
                </span>
                <span className="repo-stats">
                  {repo.file_count} files &#183; {repo.chunk_count} chunks
                </span>
              </button>
            );
          })}
          {availableRepos.length === 0 && (
            <div className="empty-repos">
              No indexed repositories yet.
            </div>
          )}
        </div>

        <div className="repo-input-row">
          <input
            id="repo"
            value={repoPaths.join(", ")}
            onChange={(event) => {
              const paths = event.target.value
                .split(",")
                .map((p) => p.trim())
                .filter(Boolean);
              setRepoPaths(paths);
            }}
            placeholder="/home/username/project, /home/username/other"
            aria-label="Repository paths (comma-separated)"
            aria-describedby="repo-hint"
          />
          <button
            className="primary-button"
            onClick={ingestRepository}
            disabled={busy || streaming || repoPaths.length === 0}
            aria-label="Index repository"
          >
            {busy || streaming ? "Working..." : "Index repository &#10141;"}
          </button>
        </div>

        <p className="field-hint" id="repo-hint">
          Enter absolute directory paths (comma-separated) accessible to the
          backend. These are local folders, not GitHub URLs.
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
            {isMultiRepo && (
              <span> &#183; {repoPaths.length} repositories selected</span>
            )}
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
                    {lastError && (
                      <button
                        className="retry-button"
                        onClick={retryLastAction}
                        disabled={busy || streaming}
                        aria-label="Retry"
                      >
                        &#8634; Retry
                      </button>
                    )}
                    <button
                      className="cancel-button"
                      onClick={cancelRequest}
                      disabled={!busy && !streaming}
                      aria-label="Cancel request"
                    >
                      &#10007; Cancel
                    </button>
                    <button
                      className="primary-button"
                      onClick={mode === "chat" ? sendMessage : runSearch}
                      disabled={
                        busy ||
                        streaming ||
                        !(mode === "chat" ? question.trim() : searchQuery.trim())
                      }
                      aria-label={
                        mode === "chat" ? "Send message" : "Search repository"
                      }
                    >
                      {streaming
                        ? "Streaming..."
                        : busy
                          ? "Processing..."
                          : mode === "chat"
                            ? "Send &#10141;"
                            : "Search &#10141;"}
                    </button>
                  </div>
                </div>
              </div>

              {messages.length > 0 && (
                <div className="chat-messages-panel" role="log" aria-label="Conversation">
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`message ${msg.role} ${msg.streaming ? "streaming" : ""}`}
                    >
                      <div className="message-header">
                        <span className="message-role">
                          {msg.role === "user" ? "You" : "DevMind"}
                        </span>
                        {msg.streaming && (
                          <span className="streaming-badge">Streaming</span>
                        )}
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
                                  {isMultiRepo && source.repo_path && (
                                    <span className="repo-tag">
                                      {shortRepoLabel(source.repo_path)}
                                    </span>
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
                  {streaming && (
                    <div className="message streaming-indicator">
                      <span className="message-role">DevMind</span>
                      <span className="streaming-badge">Streaming</span>
                      <div className="streaming-dots">Generating response<span className="dot">.</span><span className="dot">.</span><span className="dot">.</span></div>
                    </div>
                  )}
                </div>
              )}

              {messages.length === 0 && !busy && !streaming && (
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

              {lastError && !busy && !streaming && (
                <div className="error-state">
                  <span>&#10007;</span>
                  <strong>Error:</strong> {lastError}
                  <button
                    className="retry-button"
                    onClick={clearError}
                    aria-label="Dismiss error"
                  >
                    Dismiss
                  </button>
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
                <div className="system-row">
                  <span>Streaming</span>
                  <strong className="positive">SSE</strong>
                </div>

                <div className="system-note">
                  <span>&#10003;</span>
                  All model inference is performed locally.
                </div>
              </div>

              <div className="panel quick-panel">
                <div className="side-heading">
                  <h3>Quick actions</h3>
                  <span className="sparkle">&#10016;</span>
                </div>
                <button
                  className="prompt-button"
                  onClick={createNewConversation}
                  disabled={busy || streaming}
                >
                  <span>&#10133;</span> New conversation
                </button>
                {activeConversationId && (
                  <>
                    <button
                      className="prompt-button"
                      onClick={() => exportConversation("json")}
                      disabled={busy || streaming}
                    >
                      &#10063; Export JSON
                    </button>
                    <button
                      className="prompt-button"
                      onClick={() => exportConversation("markdown")}
                      disabled={busy || streaming}
                    >
                      &#10003; Export MD
                    </button>
                    <button
                      className="prompt-button"
                      onClick={deleteCurrentConversation}
                      disabled={busy || streaming}
                    >
                      <span>&#10007;</span> Delete
                    </button>
                  </>
                )}
              </div>

              <div className="panel status-panel">
                <div className="side-heading">
                  <h3>Workspace status</h3>
                  <span className="status-pulse" />
                </div>
                <strong aria-live="polite">
                  {streaming ? "Streaming response" : busy ? "Processing request" : status}
                </strong>
                <p>
                  {streaming
                    ? "Your local AI engine is generating a response."
                    : busy
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
                <div className="stat-row">
                  <span>Repositories selected</span>
                  <strong>{repoPaths.length}</strong>
                </div>
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
