---
name: attack-surface
description: Map the application attack surface — endpoints, auth, inputs, data flows
---

## Workflow

1. **Discover all entry points:**
   - HTTP endpoints: FastAPI/Flask/Django routes, REST APIs, GraphQL
   - WebSocket connections
   - CLI commands that accept user input
   - Message queue consumers (Kafka, RabbitMQ, SQS)
   - Cron jobs and scheduled tasks

2. **Classify each endpoint:**
   - **Public** — no authentication required
   - **Authenticated** — requires valid session/token
   - **Admin** — requires elevated privileges
   - **Internal** — only accessible from within the network

3. **Check authentication and authorization:**
   - Every endpoint has appropriate auth middleware
   - Role-based access control is enforced consistently
   - No authentication bypass paths (e.g., debug endpoints left open)
   - Session management: secure cookies, token rotation, expiry

4. **Map input validation:**
   - All user inputs are validated (type, length, format)
   - File uploads: type validation, size limits, no path traversal
   - Query parameters: sanitized before use in DB queries
   - Headers: validated before trust decisions

5. **Data flow analysis:**
   - Where does sensitive data enter the system?
   - Where is it stored? (encrypted at rest?)
   - Where does it leave? (encrypted in transit?)
   - Who has access? (principle of least privilege?)

6. **Report:** Table of endpoints with auth level, input validation status, and risk rating.
