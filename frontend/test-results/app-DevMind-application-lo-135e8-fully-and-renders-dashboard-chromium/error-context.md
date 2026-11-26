# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app.test.ts >> DevMind application >> loads successfully and renders dashboard
- Location: tests/e2e/app.test.ts:104:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.brand-name')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" locator('.brand-name') with timeout 5000ms
  - waiting for locator('.brand-name')

```

```yaml
- text: "{ \"cast-web-api\" : \"v1.0.2\" }"
```

# Test source

```ts
  8   |     await route.fulfill({
  9   |       status: 200,
  10  |       contentType: "application/json",
  11  |       body: JSON.stringify({
  12  |         repository: "/tmp/repo",
  13  |         files_discovered: 3,
  14  |         chunks_indexed: 10,
  15  |         embedding_model: "nomic-embed-text",
  16  |         embedding_dimensions: 768,
  17  |       }),
  18  |     });
  19  |   });
  20  | }
  21  | 
  22  | async function mockConversations(page: Page) {
  23  |   await page.route("**/api/conversations", async (route) => {
  24  |     await route.fulfill({
  25  |       status: 200,
  26  |       contentType: "application/json",
  27  |       body: JSON.stringify({ conversations: [] }),
  28  |     });
  29  |   });
  30  | }
  31  | 
  32  | async function mockRepositories(page: Page) {
  33  |   await page.route("**/api/repositories", async (route) => {
  34  |     await route.fulfill({
  35  |       status: 200,
  36  |       contentType: "application/json",
  37  |       body: JSON.stringify({ repositories: [] }),
  38  |     });
  39  |   });
  40  | }
  41  | 
  42  | async function mockIngestError(page: Page) {
  43  |   await page.route("**/api/ingest", async (route) => {
  44  |     await route.fulfill({
  45  |       status: 400,
  46  |       contentType: "application/json",
  47  |       body: JSON.stringify({
  48  |         error: "Repository path is outside the allowed directory",
  49  |       }),
  50  |     });
  51  |   });
  52  | }
  53  | 
  54  | async function mockSuccessfulStreamingChat(page: Page) {
  55  |   await page.route("**/api/chat/stream", async (route) => {
  56  |     await new Promise((resolve) => setTimeout(resolve, 200));
  57  |     const body = JSON.stringify({
  58  |       text: "This function is defined in src/main.py.",
  59  |       done: true,
  60  |       sources: [
  61  |         {
  62  |           file_path: "src/main.py",
  63  |           symbol: "main",
  64  |           start_line: 1,
  65  |           end_line: 5,
  66  |           score: 0.95,
  67  |         },
  68  |       ],
  69  |       conversation_id: "conv-1",
  70  |       citation_keys: ["[FILE:src/main.py:1]"],
  71  |     });
  72  |     await route.fulfill({
  73  |       status: 200,
  74  |       contentType: "text/event-stream",
  75  |       body: `data: ${body}\n\n`,
  76  |       headers: { "content-type": "text/event-stream" },
  77  |     });
  78  |   });
  79  | }
  80  | 
  81  | async function mockApiFailure(page: Page) {
  82  |   await page.route("**/api/*", async (route) => {
  83  |     await route.fulfill({
  84  |       status: 500,
  85  |       contentType: "application/json",
  86  |       body: JSON.stringify({ error: "Internal server error" }),
  87  |     });
  88  |   });
  89  | }
  90  | 
  91  | async function mockRateLimit(page: Page) {
  92  |   await page.route("**/api/ingest", async (route) => {
  93  |     await route.fulfill({
  94  |       status: 429,
  95  |       contentType: "application/json",
  96  |       body: JSON.stringify({
  97  |         error: "Too many requests. Please slow down and try again later.",
  98  |       }),
  99  |     });
  100 |   });
  101 | }
  102 | 
  103 | test.describe("DevMind application", () => {
  104 |   test("loads successfully and renders dashboard", async ({ page }) => {
  105 |     mockConversations(page);
  106 |     mockRepositories(page);
  107 |     await page.goto("/");
> 108 |     await expect(page.locator(".brand-name")).toBeVisible();
      |                                               ^ Error: expect(locator).toBeVisible() failed
  109 |     await expect(page.getByText(/No conversations yet/)).toBeVisible();
  110 |   });
  111 | 
  112 |   test("shows empty repositories state", async ({ page }) => {
  113 |     mockConversations(page);
  114 |     mockRepositories(page);
  115 |     await page.goto("/");
  116 |     await expect(page.getByText(/No indexed repositories yet/)).toBeVisible();
  117 |   });
  118 | 
  119 |   test("navigation works", async ({ page }) => {
  120 |     mockConversations(page);
  121 |     mockRepositories(page);
  122 |     await page.goto("/");
  123 | 
  124 |     await page.getByRole("button", { name: /Semantic search mode/ }).click();
  125 |     await expect(
  126 |       page.locator("[placeholder*='Find functions']")
  127 |     ).toBeVisible();
  128 | 
  129 |     await page.getByRole("button", { name: /Conversational chat mode/ }).click();
  130 |     await expect(
  131 |       page.locator("[placeholder*='Explain how authentication']")
  132 |     ).toBeVisible();
  133 |   });
  134 | 
  135 |   test("repository path input accepts valid input", async ({ page }) => {
  136 |     mockConversations(page);
  137 |     mockRepositories(page);
  138 |     await page.goto("/");
  139 | 
  140 |     const input = page.locator("input[aria-label='Repository paths (comma-separated)']");
  141 |     await input.fill("/home/user/my-project");
  142 |     await expect(input).toHaveValue("/home/user/my-project");
  143 |   });
  144 | 
  145 |   test("invalid repository path displays useful error", async ({ page }) => {
  146 |     mockConversations(page);
  147 |     mockRepositories(page);
  148 |     mockIngestError(page);
  149 |     await page.goto("/");
  150 | 
  151 |     const input = page.locator("input[aria-label='Repository paths (comma-separated)']");
  152 |     await input.fill("/tmp/outside");
  153 |     await page.getByRole("button", { name: /Index repository/ }).click();
  154 | 
  155 |     const errorElements = await page.getByText(/Repository path is outside the allowed directory/).all();
  156 |     await expect(errorElements[0]).toBeVisible();
  157 |   });
  158 | 
  159 |   test("ingestion displays loading state", async ({ page }) => {
  160 |     mockConversations(page);
  161 |     mockRepositories(page);
  162 |     mockSuccessfulIngest(page);
  163 |     await page.goto("/");
  164 | 
  165 |     const input = page.locator("input[aria-label='Repository paths (comma-separated)']");
  166 |     await input.fill("/tmp/repo");
  167 |     await page.getByRole("button", { name: /Index repository/ }).click();
  168 | 
  169 |     await expect(page.getByText(/Working/)).toBeVisible();
  170 |     await expect(
  171 |       page.getByText(/Repository indexed successfully/)
  172 |     ).toBeVisible();
  173 |   });
  174 | 
  175 |   test("streaming chat message displays with sources", async ({ page }) => {
  176 |     mockConversations(page);
  177 |     mockRepositories(page);
  178 |     mockSuccessfulStreamingChat(page);
  179 |     await page.goto("/");
  180 | 
  181 |     const input = page.locator("textarea[placeholder*='Explain how authentication']");
  182 |     await input.fill("How does authentication work?");
  183 |     await page.getByRole("button", { name: /Send/ }).click();
  184 | 
  185 |     await expect(page.getByText(/This function is defined/)).toBeVisible();
  186 |     const sourceElements = await page.getByText(/src\/main\.py/).all();
  187 |     await expect(sourceElements[0]).toBeVisible();
  188 |   });
  189 | 
  190 |   test("API failures do not crash the interface", async ({ page }) => {
  191 |     mockConversations(page);
  192 |     mockRepositories(page);
  193 |     mockApiFailure(page);
  194 |     await page.goto("/");
  195 | 
  196 |     const input = page.locator("input[aria-label='Repository paths (comma-separated)']");
  197 |     await input.fill("/tmp/repo");
  198 |     await page.getByRole("button", { name: /Index repository/ }).click();
  199 | 
  200 |     const errorElements = await page.getByText(/Internal server error/).all();
  201 |     await expect(errorElements[0]).toBeVisible();
  202 |   });
  203 | 
  204 |   test("HTTP 429 rate-limit responses display useful feedback", async ({
  205 |     page,
  206 |   }) => {
  207 |     mockConversations(page);
  208 |     mockRepositories(page);
```