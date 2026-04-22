---
name: read-wiki
description: Fetch Confluence page by ID or search by space+title, extract content
---

## Workflow

### Option A: Fetch by Page ID (when user provides the ID)

1. **Fetch the Confluence page** by ID.
   ```bash
   curl -sS "BASE_URL/jira/confluence/PAGE_ID"
   ```

2. **Parse the response.** Extract:
   - `title` — page title
   - `body` — HTML/storage format content
   - `status` — current or archived

3. **Convert the body** from Confluence storage format (HTML-like) to readable text. Strip tags and present the content clearly.

### Option B: Search by Space + Title (when user describes the page)

1. **Search Confluence** using CQL.
   ```bash
   curl -sS -X POST BASE_URL/jira/confluence/search \
     -H "Content-Type: application/json" \
     -d '{"cql": "space = '\''SPACE_KEY'\'' and title ~ '\''search terms'\''"}'
   ```

2. **Parse the search results.** Each result contains:
   - `id` — page ID (use to fetch full content)
   - `title` — page title
   - `type` — page or blogpost
   - `space` — space key

3. **If multiple results**, present them as a numbered list and ask user which to fetch.

4. **Fetch the selected page** using Option A workflow.

### Post-Processing

5. **Extract key information** from the page:
   - Requirements and specifications
   - Architecture decisions
   - API contracts and schemas
   - Implementation notes and constraints

6. **Present a structured summary** with the most relevant content highlighted.
