import { test, expect, type Page } from "@playwright/test";

test.use({ baseURL: "http://localhost:3000" });

async function mockSuccessfulIngest(page: Page) {
  await page.route("**/api/ingest", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 200));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        repository: "/tmp/repo",
        files_discovered: 3,
        chunks_indexed: 10,
        embedding_model: "nomic-embed-text",
        embedding_dimensions: 768,
      }),
    });
  });
}

async function mockConversations(page: Page) {
  await page.route("**/api/conversations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ conversations: [] }),
    });
  });
}

async function mockIngestError(page: Page) {
  await page.route("**/api/ingest", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        error: "Repository path is outside the allowed directory",
      }),
    });
  });
}

async function mockSuccessfulChat(page: Page) {
  await page.route("**/api/chat", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 200));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "This function is defined in src/main.py at line 1.",
        sources: [
          {
            file_path: "src/main.py",
            symbol: "main",
            start_line: 1,
            end_line: 5,
            score: 0.95,
          },
        ],
        conversation_id: "test-conversation-1",
        citation_keys: ["[FILE:src/main.py:1]"],
      }),
    });
  });
}

async function mockApiFailure(page: Page) {
  await page.route("**/api/*", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "Internal server error" }),
    });
  });
}

async function mockRateLimit(page: Page) {
  await page.route("**/api/ingest", async (route) => {
    await route.fulfill({
      status: 429,
      contentType: "application/json",
      body: JSON.stringify({
        error: "Too many requests. Please slow down and try again later.",
      }),
    });
  });
}

test.describe("DevMind application", () => {
  test("loads successfully and renders dashboard", async ({ page }) => {
    mockConversations(page);
    await page.goto("/");
    await expect(page.locator(".brand-name")).toBeVisible();
    await expect(page.getByText(/No conversations yet/)).toBeVisible();
  });

  test("shows empty conversations state", async ({ page }) => {
    mockConversations(page);
    await page.goto("/");
    await expect(page.getByText(/No conversations yet/)).toBeVisible();
  });

  test("navigation works", async ({ page }) => {
    mockConversations(page);
    await page.goto("/");

    await page.getByRole("button", { name: /Semantic search mode/ }).click();
    await expect(
      page.locator("[placeholder*='Find functions']")
    ).toBeVisible();

    await page.getByRole("button", { name: /Conversational chat mode/ }).click();
    await expect(
      page.locator("[placeholder*='Explain how authentication']")
    ).toBeVisible();
  });

  test("repository path input accepts valid input", async ({ page }) => {
    mockConversations(page);
    await page.goto("/");

    const input = page.locator("[placeholder='/home/username/project']");
    await input.fill("/home/user/my-project");
    await expect(input).toHaveValue("/home/user/my-project");
  });

  test("invalid repository path displays useful error", async ({ page }) => {
    mockConversations(page);
    mockIngestError(page);
    await page.goto("/");

    const input = page.locator("[placeholder='/home/username/project']");
    await input.fill("/tmp/outside");
    await page.getByRole("button", { name: /Index repository/ }).click();

    await expect(
      page.getByText(/Repository path is outside the allowed directory/)
    ).toBeVisible();
  });

  test("ingestion displays loading state", async ({ page }) => {
    mockConversations(page);
    mockSuccessfulIngest(page);
    await page.goto("/");

    const input = page.locator("[placeholder='/home/username/project']");
    await input.fill("/tmp/repo");
    await page.getByRole("button", { name: /Index repository/ }).click();

    await expect(page.getByText(/Working/)).toBeVisible();
    await expect(
      page.getByText(/Repository indexed successfully/)
    ).toBeVisible();
  });

  test("chat message displays with sources", async ({ page }) => {
    mockConversations(page);
    mockSuccessfulChat(page);
    await page.goto("/");

    const input = page.locator("[placeholder*='Explain how authentication']");
    await input.fill("How does authentication work?");
    await page.getByRole("button", { name: /Send/ }).click();

    await expect(page.getByText(/This function is defined/)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Open src\/main\.py at line/ })
    ).toBeVisible();
  });

  test("API failures do not crash the interface", async ({ page }) => {
    mockConversations(page);
    mockApiFailure(page);
    await page.goto("/");

    const input = page.locator("[placeholder='/home/username/project']");
    await input.fill("/tmp/repo");
    await page.getByRole("button", { name: /Index repository/ }).click();

    await expect(page.getByText(/Internal server error/)).toBeVisible();
  });

  test("HTTP 429 rate-limit responses display useful feedback", async ({
    page,
  }) => {
    mockConversations(page);
    mockRateLimit(page);
    await page.goto("/");

    const input = page.locator("[placeholder='/home/username/project']");
    await input.fill("/tmp/repo");
    await page.getByRole("button", { name: /Index repository/ }).click();

    await expect(page.getByText(/Too many requests/)).toBeVisible();
  });

  test("request cancellation does not leave interface in broken state", async ({
    page,
  }) => {
    mockConversations(page);
    // Route that never resolves (simulating a hung request)
    await page.route("**/api/ingest", async (route) => {
      // Never fulfill - simulates a hanging request
    });

    await page.goto("/");

    const input = page.locator("[placeholder='/home/username/project']");
    await input.fill("/tmp/repo");
    await page.getByRole("button", { name: /Index repository/ }).click();

    await expect(page.getByText(/Working/)).toBeVisible();

    // Cancel the request
    await page.getByRole("button", { name: /Cancel/ }).click();

    // Interface should still be functional
    await expect(page.getByText(/Request cancelled/)).toBeVisible();
  });
});
