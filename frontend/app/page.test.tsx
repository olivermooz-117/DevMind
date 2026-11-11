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

describe("Home page API interactions", () => {
  it("loads with empty conversations", async () => {
    mockConversations();

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText(/No conversations yet/)).toBeInTheDocument();
    });
  });

  it("handles successful ingestion response", async () => {
    mockConversations();
    mockApiResponse({
      repository: "/tmp/repo",
      files_discovered: 3,
      chunks_indexed: 10,
    });

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project");
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
    mockApiError("Repository path is outside the allowed directory", 400);

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project");
    fireEvent.change(input, { target: { value: "/tmp/outside" } });

    const button = screen.getByText(/Index repository/);
    fireEvent.click(button);

    await waitFor(() => {
      expect(
        screen.getByText(/Repository path is outside the allowed directory/)
      ).toBeInTheDocument();
    });
  });

  it("handles non-JSON API error response", async () => {
    mockConversations();
    mockNonJsonError();

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project");
    fireEvent.change(input, { target: { value: "/tmp/repo" } });

    const button = screen.getByText(/Index repository/);
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/Server returned/)).toBeInTheDocument();
    });
  });

  it("shows loading state during ingestion", async () => {
    mockConversations();
    let resolveFetch: (value: Response) => void = () => {};
    mockFetch.mockImplementation(() => {
      return new Promise((resolve) => {
        resolveFetch = resolve;
      });
    });

    render(<Home />);

    const input = screen.getByPlaceholderText("/home/username/project");
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

    render(<Home />);

    const button = screen.getByText(/Send/);
    expect(button).toBeDisabled();
  });

  it("requires a repository path before ingesting", async () => {
    mockConversations();

    render(<Home />);

    const button = screen.getByText(/Index repository/);
    expect(button).toBeDisabled();
  });
});
