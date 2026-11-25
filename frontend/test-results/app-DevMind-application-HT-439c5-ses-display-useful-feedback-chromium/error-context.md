# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app.test.ts >> DevMind application >> HTTP 429 rate-limit responses display useful feedback
- Location: tests/e2e/app.test.ts:204:3

# Error details

```
Error: toBeVisible can be only used with Locator object, was called with undefined
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - main [ref=e2]:
    - complementary [ref=e3]:
      - generic [ref=e4]:
        - generic [ref=e5]: D
        - generic [ref=e6]:
          - generic [ref=e7]: DevMind.
          - generic [ref=e8]: ENGINEERING INTELLIGENCE
      - generic [ref=e9]: CONVERSATIONS
      - button "New conversation" [ref=e11] [cursor=pointer]: ➕ New conversation
      - generic [ref=e12]:
        - text: "Import conversation:"
        - button "Import conversation:" [ref=e13]
      - navigation [ref=e14]:
        - generic [ref=e15]: No conversations yet. Start one by asking a question.
      - generic [ref=e16]: REPOSITORIES
      - generic [ref=e17]: No indexed repositories yet.
      - generic [ref=e19]:
        - textbox "Repository paths (comma-separated)" [ref=e20]:
          - /placeholder: /home/username/project, /home/username/other
          - text: /tmp/repo
        - button "Index repository" [ref=e21] [cursor=pointer]: Index repository &#10141;
      - paragraph [ref=e22]: Enter absolute directory paths (comma-separated) accessible to the backend. These are local folders, not GitHub URLs.
      - generic [ref=e24]:
        - generic [ref=e25]: ✠
        - strong [ref=e26]: Private by design
        - paragraph [ref=e27]: Your code and AI inference stay on your machine.
        - generic [ref=e28]: LOCAL INFERENCE
    - generic [ref=e30]:
      - generic [ref=e31]:
        - generic [ref=e32]: Workspace / Chat
        - generic [ref=e33]:
          - generic [ref=e34]: LOCAL WORKSPACE
          - generic [ref=e37]: D
      - generic [ref=e38]:
        - generic [ref=e39]:
          - generic [ref=e40]:
            - generic [ref=e41]:
              - generic [ref=e42]:
                - generic [ref=e43]: CODE ASSISTANT
                - heading "Conversational Assistant" [level=2] [ref=e44]
              - generic [ref=e45]: READY
            - generic [ref=e47]:
              - generic [ref=e48]:
                - generic [ref=e49]: ✠
                - generic [ref=e50]:
                  - heading "AI Code Assistant" [level=3] [ref=e51]
                  - paragraph [ref=e52]: Ask questions about your repository with source citations
              - generic [ref=e53]:
                - button "Conversational chat mode" [pressed] [ref=e54] [cursor=pointer]: ✠ Chat
                - button "Semantic search mode" [ref=e55] [cursor=pointer]: ⟁ Search
              - generic [ref=e56]: WHAT WOULD YOU LIKE TO ASK?
              - textbox "Question about your code" [ref=e57]:
                - /placeholder: Explain how authentication works in this project...
              - generic [ref=e58]:
                - generic [ref=e59]: → Powered by your local code index
                - generic [ref=e60]:
                  - button "Retry" [ref=e61] [cursor=pointer]: ↺ Retry
                  - button "Cancel request" [disabled] [ref=e62] [cursor=pointer]: ✗ Cancel
                  - button "Send message" [disabled] [ref=e63]: Send &#10141;
            - generic [ref=e64]:
              - generic [ref=e65]: ✠
              - heading "Start a conversation" [level=3] [ref=e66]
              - paragraph [ref=e67]: Ask a question about your indexed repository to get started. DevMind will search your code index and provide answers with source citations.
            - generic [ref=e68]:
              - text: ✗
              - strong [ref=e69]: "Error:"
              - text: Too many requests. Please slow down and try again later.
              - button "Dismiss error" [ref=e70] [cursor=pointer]: Dismiss
          - complementary [ref=e71]:
            - generic [ref=e72]:
              - generic [ref=e73]:
                - heading "System environment" [level=3] [ref=e74]
                - generic [ref=e75]: ✠
              - generic [ref=e76]:
                - generic [ref=e77]: Inference provider
                - strong [ref=e78]: Ollama
              - generic [ref=e79]:
                - generic [ref=e80]: Chat model
                - strong [ref=e81]: llama3.2:1b
              - generic [ref=e82]:
                - generic [ref=e83]: Embedding model
                - strong [ref=e84]: nomic-embed-text
              - generic [ref=e85]:
                - generic [ref=e86]: Vector storage
                - strong [ref=e87]: SQLite
              - generic [ref=e88]:
                - generic [ref=e89]: Inference mode
                - strong [ref=e90]: Local
              - generic [ref=e91]:
                - generic [ref=e92]: Streaming
                - strong [ref=e93]: SSE
              - generic [ref=e94]: ✓All model inference is performed locally.
            - generic [ref=e95]:
              - generic [ref=e96]:
                - heading "Quick actions" [level=3] [ref=e97]
                - generic [ref=e98]: ✠
              - button "➕ New conversation" [ref=e99] [cursor=pointer]
            - generic [ref=e100]:
              - heading "Workspace status" [level=3] [ref=e102]
              - strong [ref=e104]: Too many requests. Please slow down and try again later.
              - paragraph [ref=e105]: DevMind is ready for your next engineering task.
              - generic [ref=e106]:
                - text: Repositories selected
                - strong [ref=e107]: "1"
        - generic [ref=e108]:
          - generic [ref=e109]: DEVMIND © 2026
          - generic [ref=e110]: LOCAL AI · PRIVATE ENGINEERING · BUILT FOR DEVELOPERS
  - alert [ref=e111]
```

# Test source

```ts
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
  155 |     const errorElements = page.getByText(/Repository path is outside the allowed directory/).all();
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
  186 |     const sourceElements = page.getByText(/src\/main\.py/).all();
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
  200 |     const errorElements = page.getByText(/Internal server error/).all();
  201 |     await expect(errorElements[0]).toBeVisible();
  202 |   });
  203 | 
  204 |   test("HTTP 429 rate-limit responses display useful feedback", async ({
  205 |     page,
  206 |   }) => {
  207 |     mockConversations(page);
  208 |     mockRepositories(page);
  209 |     mockRateLimit(page);
  210 |     await page.goto("/");
  211 | 
  212 |     const input = page.locator("input[aria-label='Repository paths (comma-separated)']");
  213 |     await input.fill("/tmp/repo");
  214 |     await page.getByRole("button", { name: /Index repository/ }).click();
  215 | 
  216 |     const errorElements = page.getByText(/Too many requests/).all();
> 217 |     await expect(errorElements[0]).toBeVisible();
      |                                    ^ Error: toBeVisible can be only used with Locator object, was called with undefined
  218 |   });
  219 | 
  220 |   test("request cancellation does not leave interface in broken state", async ({
  221 |     page,
  222 |   }) => {
  223 |     mockConversations(page);
  224 |     mockRepositories(page);
  225 |     // Route that never resolves (simulating a hung request)
  226 |     await page.route("**/api/ingest", async (route) => {
  227 |       // Never fulfill - simulates a hanging request
  228 |     });
  229 | 
  230 |     await page.goto("/");
  231 | 
  232 |     const input = page.locator("input[aria-label='Repository paths (comma-separated)']");
  233 |     await input.fill("/tmp/repo");
  234 |     await page.getByRole("button", { name: /Index repository/ }).click();
  235 | 
  236 |     await expect(page.getByText(/Working/)).toBeVisible();
  237 | 
  238 |     // Cancel the request
  239 |     await page.getByRole("button", { name: /Cancel/ }).click();
  240 | 
  241 |     // Interface should still be functional
  242 |     await expect(page.getByText(/Request cancelled/)).toBeVisible();
  243 |   });
  244 | });
  245 | 
```