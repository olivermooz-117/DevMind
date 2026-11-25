import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import Home from "./page";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  mockFetch.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const mockApiResponse = (data: object, status = 200) => {
  mockFetch.mockResolvedValueOnce({
    ok: status === 200,
    status,
    json: vi.fn().mockResolvedValue(data),
  } as unknown as Response);
};

const mockApiError = (errorMessage: string, status = 500) => {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    json: vi.fn().mockResolvedValue({ error: errorMessage }),
  } as unknown as Response);
};

const mockNonJsonError = () => {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status: 500,
    json: vi.fn().mockRejectedValue(new Error("Invalid JSON")),
  } as unknown as Response);
};

const mockConversations = () => {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status: 200,
    json: vi.fn().mockResolvedValue({ conversations: [] }),
  } as unknown as Response);
};

const mockRepositories = () => {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status: 200,
    json: vi.fn().mockResolvedValue({ repositories: [] }),
  } as unknown as Response);
};

describe("Home page API interactions", () => {
  it("loads with empty conversations", async () => {
    mockConversations();
    mockRepositories();

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText(/No conversations yet/)).toBeInTheDocument();
    });
  });

  it("shows empty repositories state", async () => {
    mockConversations();
    mockRepositories();

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText(/No indexed repositories yet/)).toBeInTheDocument();
    });
  });

  it("handles successful ingestion response", async () => {
    mockConversations();
    mockRepositories();
    mockApiResponse({
      repository: "/tmp/repo",
      files_discovered: 3,
      chunks_indexed: 10,
    });

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project, /home/username/other");
    fireEvent.change(input, { target: { value: "/tmp/repo" } });

    const button = screen.getByText(/Index repository/);
    fireEvent.click(button);

    await waitFor(() => {
      expect(
        screen.getByText(/Repository indexed successfully/)
      ).toBeInTheDocument();
    });
  });

  it("handles ingestion API error", async () => {
    mockConversations();
    mockRepositories();
    mockApiError("Repository path is outside the allowed directory", 400);

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project, /home/username/other");
    fireEvent.change(input, { target: { value: "/tmp/outside" } });

    const button = screen.getByText(/Index repository/);
    fireEvent.click(button);

    await waitFor(() => {
      const elements = screen.getAllByText(/Repository path is outside the allowed directory/);
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("handles non-JSON API error response", async () => {
    mockConversations();
    mockRepositories();
    mockNonJsonError();

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project, /home/username/other");
    fireEvent.change(input, { target: { value: "/tmp/repo" } });

    const button = screen.getByText(/Index repository/);
    fireEvent.click(button);

    await waitFor(() => {
      expect(
        screen.getByText(/Server returned|Error:/)
      ).toBeInTheDocument();
    });
  });

  it("shows loading state during ingestion", async () => {
    mockConversations();
    mockRepositories();
    let resolveFetch: (value: Response) => void = () => {};
    mockFetch.mockImplementation(() => {
      return new Promise((resolve) => {
        resolveFetch = resolve;
      });
    });

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project, /home/username/other");
    fireEvent.change(input, { target: { value: "/tmp/repo" } });

    const button = screen.getByText(/Index repository/);
    fireEvent.click(button);

    expect(screen.getByText(/Working/)).toBeInTheDocument();

    resolveFetch({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({
        repository: "/tmp/repo",
        files_discovered: 1,
        chunks_indexed: 2,
      }),
    } as unknown as Response);

    await waitFor(() => {
      expect(screen.getByText(/Repository indexed successfully/)).toBeInTheDocument();
    });
  });

  it("requires a question before sending", async () => {
    mockConversations();
    mockRepositories();

    render(<Home />);

    const button = screen.getByText(/Send/);
    expect(button).toBeDisabled();
  });

  it("requires a repository path before ingesting", async () => {
    mockConversations();
    mockRepositories();

    render(<Home />);

    const button = screen.getByText(/Index repository/);
    expect(button).toBeDisabled();
  });

  it("handles streaming chat response", async () => {
    mockConversations();
    mockRepositories();

    // Mock SSE streaming response
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"text":"Hello ","done":false}\n\n'));
        controller.enqueue(encoder.encode('data: {"text":"world","done":true,"sources":[{"file_path":"src/main.py","symbol":"main","start_line":1,"end_line":5,"score":0.95}],"conversation_id":"conv-1","citation_keys":["[FILE:src/main.py:1]"]}\n\n'));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
      headers: { get: () => "text/event-stream" },
    } as unknown as Response);

    render(<Home />);

    const input = screen.getByPlaceholderText(/Explain how authentication/);
    fireEvent.change(input, { target: { value: "How does auth work?" } });

    const button = screen.getByText(/Send/);
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/Hello world/)).toBeInTheDocument();
    });
  });

  it("displays error state after failed request", async () => {
    mockConversations();
    mockRepositories();
    mockApiError("Connection failed", 503);

    render(<Home />);

    const input = screen.getByPlaceholderText(/Explain how authentication/);
    fireEvent.change(input, { target: { value: "test" } });

    const button = screen.getByText(/Send/);
    fireEvent.click(button);

    await waitFor(() => {
      const elements = screen.getAllByText(/Error:/);
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });
  });
});
