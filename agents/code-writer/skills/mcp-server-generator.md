---
name: mcp-server-generator
description: Reads REST APIs (OpenAPI/Swagger) or gRPC (.proto) definitions and generates a fully functional MCP (Model Context Protocol) server that exposes every endpoint as an MCP tool
version: "1.0"
tags: [mcp, api, rest, grpc, openapi, code-generation]
---

# MCP Server Generator from REST/gRPC APIs

## Purpose
Automatically convert any REST API (from OpenAPI/Swagger spec) or gRPC service (from .proto files) into a fully functional MCP server. Each API endpoint becomes an MCP tool that AI agents can call.

## Input Sources (in priority order)
1. **OpenAPI/Swagger spec file** — `openapi.json`, `openapi.yaml`, `swagger.json`, `swagger.yaml`
2. **Proto files** — `*.proto` with service/rpc definitions
3. **Live API URL** — Fetch spec from `/docs`, `/openapi.json`, `/swagger.json`, or gRPC reflection
4. **Source code** — Parse FastAPI/Express/Spring/Go-Chi route definitions directly from code
5. **Postman/Insomnia collection** — Import from collection export files
6. **HAR file** — Extract API patterns from browser HTTP archive recordings

## Generation Steps

### Step 1: Parse & Discover All Endpoints
```
For REST:
- Parse OpenAPI spec → extract all paths, methods, parameters, request bodies, responses
- Identify authentication schemes (Bearer, API Key, OAuth2, Basic)
- Extract parameter types, constraints, enums, required/optional
- Parse response schemas including error responses
- Detect pagination patterns (offset/limit, cursor, page/size)

For gRPC:
- Parse .proto files → extract all services, RPCs, message types
- Map streaming RPCs (unary, server-stream, client-stream, bidi)
- Extract field types, enums, oneofs, nested messages
- Identify repeated fields and maps
```

### Step 2: Generate MCP Tool Definitions
For each endpoint/RPC, generate an MCP tool with:

```json
{
  "name": "<resource>_<action>",
  "description": "<human-readable description from API docs or inferred from endpoint>",
  "inputSchema": {
    "type": "object",
    "properties": {
      // Map each API parameter to a JSON Schema property
      // path params → required properties
      // query params → optional properties with defaults
      // request body → nested object property
    },
    "required": ["<path_params>", "<required_body_fields>"]
  }
}
```

**Naming Convention:**
- `GET /users/{id}` → `get_user`
- `POST /users` → `create_user`
- `GET /users/{id}/orders` → `list_user_orders`
- `PUT /users/{id}` → `update_user`
- `DELETE /users/{id}` → `delete_user`
- gRPC `UserService.GetUser` → `user_service_get_user`

### Step 3: Generate MCP Server Code

```python
# Generated MCP Server Structure:
#
# mcp_server_<api_name>/
# ├── server.py              # Main MCP server with tool registrations
# ├── tools/
# │   ├── __init__.py
# │   ├── <resource_1>.py    # Tool handlers grouped by resource
# │   ├── <resource_2>.py
# │   └── ...
# ├── client.py              # HTTP/gRPC client wrapper with auth, retries, timeouts
# ├── auth.py                # Authentication handler (Bearer, API Key, OAuth2)
# ├── models.py              # Pydantic models from API schemas
# ├── config.py              # Server config (base URL, auth, timeouts)
# ├── README.md              # Setup & usage instructions
# ├── pyproject.toml         # Dependencies
# └── tests/
#     ├── test_tools.py      # Unit tests for each tool
#     └── test_server.py     # Integration tests
```

### Step 4: Generate Server Implementation

```python
#!/usr/bin/env python3
"""MCP Server generated from {api_name} API spec."""

import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import APIClient
from .config import ServerConfig

server = Server("{api_name}")
config = ServerConfig()
client = APIClient(config)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available API tools."""
    return [
        # Auto-generated tool definitions from API spec
        # One Tool() per endpoint
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to the appropriate API endpoint."""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    
    result = await handler(client, arguments)
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# --- Tool Handlers (one per endpoint) ---

async def get_user(client: APIClient, args: dict):
    """GET /users/{id}"""
    return await client.get(f"/users/{args['id']}")


async def create_user(client: APIClient, args: dict):
    """POST /users"""
    body = {k: v for k, v in args.items() if k in ["name", "email", "role"]}
    return await client.post("/users", json=body)

# ... generated for every endpoint ...


TOOL_HANDLERS = {
    "get_user": get_user,
    "create_user": create_user,
    # ... all handlers mapped ...
}


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 5: Generate Smart Features

**5a. Pagination Handling**
- Detect pagination patterns from API spec
- Generate tools that auto-paginate or accept page params
- Option: `fetch_all=true` to auto-paginate and return all results

**5b. Authentication**
- Read auth schemes from spec
- Generate config for: Bearer token, API Key (header/query), OAuth2 client credentials, Basic auth, mTLS
- Support env var injection: `{API_NAME}_API_KEY`, `{API_NAME}_BASE_URL`

**5c. Error Handling**
- Map HTTP status codes to meaningful MCP error responses
- Include error details from API response body
- Retry on 429/503 with exponential backoff

**5d. Rate Limiting**
- Respect rate limit headers (X-RateLimit-Remaining, Retry-After)
- Queue requests when approaching limits
- Report rate limit status in tool responses

**5e. Caching**
- Cache GET responses with configurable TTL
- Respect Cache-Control headers
- Invalidate on POST/PUT/DELETE to same resource

**5f. Response Transformation**
- Flatten deeply nested responses for LLM readability
- Truncate large arrays with summary ("showing 10 of 1,247 results")
- Convert binary responses to descriptions ("PDF file, 2.3 MB, 15 pages")

**5g. Batch Operations**
- If API supports batch endpoints, generate batch tools
- If not, generate client-side batch tool that calls N endpoints in parallel

### Step 6: Generate MCP Config Snippet

Output ready-to-paste config for claude_desktop_config.json or .mcp.json:

```json
{
  "mcpServers": {
    "<api_name>": {
      "command": "python",
      "args": ["-m", "mcp_server_<api_name>.server"],
      "env": {
        "<API_NAME>_BASE_URL": "https://api.example.com",
        "<API_NAME>_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## Advanced Options

### `--group-by resource`
Group related tools under resource prefixes (users_*, orders_*, products_*)

### `--include <pattern>`
Only generate tools for matching endpoints: `--include "/users/*" --include "/orders/*"`

### `--exclude <pattern>`
Skip endpoints: `--exclude "/internal/*" --exclude "/admin/*"`

### `--read-only`
Only generate tools for GET endpoints (safe for read-only agents)

### `--auth-type <type>`
Override auth detection: `bearer`, `api-key`, `oauth2`, `basic`, `none`

### `--transport stdio|sse`
Generate stdio (default, for local) or SSE (for remote/shared) MCP server

### `--language python|typescript|go`
Generate server in specified language (default: python)

### `--with-resources`
Also generate MCP Resources (not just tools) for read-heavy endpoints that represent data entities

### `--with-prompts`
Generate MCP Prompts for common multi-step workflows detected from API structure (e.g., create-then-configure patterns)

## Example Usage

```bash
# From OpenAPI spec file
code-agents mcp-gen --spec openapi.yaml --output ./mcp-server-myapi/

# From live API
code-agents mcp-gen --url https://api.example.com/openapi.json --output ./mcp-server-example/

# From proto files
code-agents mcp-gen --proto ./protos/user_service.proto --output ./mcp-server-users/

# From source code (auto-detect framework)
code-agents mcp-gen --source ./src/routes/ --output ./mcp-server-myapp/

# Read-only, only user endpoints
code-agents mcp-gen --spec api.yaml --read-only --include "/users/*" --output ./mcp-server-users/

# Generate TypeScript MCP server with SSE transport
code-agents mcp-gen --spec api.yaml --language typescript --transport sse --output ./mcp-server-ts/
```

## Validation Checklist
After generation, verify:
- [ ] Every API endpoint has a corresponding MCP tool
- [ ] All required parameters are marked required in inputSchema
- [ ] Auth is configured and working
- [ ] Error responses are handled gracefully
- [ ] Pagination works for list endpoints
- [ ] Generated tests pass
- [ ] MCP config snippet is valid
- [ ] Server starts and lists tools correctly via `mcp list-tools`
