---
name: mock-build
description: Mock builder — generate mock implementations for external services
tags: [testing, mocks, stubs, isolation]
---

# Mock Builder

## Workflow

1. **Identify dependencies** — Find external calls: HTTP APIs, databases, message queues, file systems, third-party SDKs.
2. **Extract interfaces** — Determine the method signatures, request/response shapes, and error modes used.
3. **Generate mocks** — Create mock classes or functions that replicate the interface with configurable responses.
4. **Add failure modes** — Include helpers to simulate: timeouts, 4xx/5xx errors, empty responses, slow responses.
5. **Wire up fixtures** — Produce pytest fixtures (or framework-appropriate setup) that inject the mocks.
6. **Output** — Return ready-to-use mock code with usage examples.

## Notes

- Use the project's existing mock patterns if present (e.g., unittest.mock, Jest mocks, testify).
- For HTTP mocks, prefer responses/httpretty (Python) or nock (Node) style when appropriate.
