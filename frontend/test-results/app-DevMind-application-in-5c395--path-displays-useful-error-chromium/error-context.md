# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app.test.ts >> DevMind application >> invalid repository path displays useful error
- Location: tests/e2e/app.test.ts:145:3

# Error details

```
Error: locator.fill: Target page, context or browser has been closed
Call log:
  - waiting for locator('input[aria-label=\'Repository paths (comma-separated)\']')

```

```
Error: write EPIPE
```