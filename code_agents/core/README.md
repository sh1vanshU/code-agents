# Core

Core infrastructure and configuration modules that power the code-agents platform.

## Modules

| Module | Description |
|--------|-------------|
| `app.py` | FastAPI application, CORS, lifespan, middleware |
| `config.py` | AgentConfig, Settings, AgentLoader (YAML + ${VAR} expansion) |
| `backend.py` | Backend dispatcher: cursor CLI/HTTP, claude SDK, claude CLI |
| `stream.py` | SSE streaming, build_prompt() for multi-turn conversations |
| `models.py` | Pydantic request/response models |
| `env_loader.py` | Two-tier env: global (~/.code-agents/config.env) + per-repo (.env.code-agents) |
| `main.py` | Entry point for uvicorn server |
| `logging_config.py` | Structured logging setup and configuration |
| `openai_errors.py` | OpenAI-compatible error formatting |
| `message_types.py` | Message type definitions (AssistantMessage, SystemMessage, etc.) |
| `rate_limiter.py` | Per-user RPM + daily token budgets |
| `token_tracker.py` | Token usage tracking and limits |
| `context_manager.py` | Smart context trimming and conversation window management |
| `response_optimizer.py` | Response optimization and formatting |
| `response_verifier.py` | Response verification and validation |
| `confidence_scorer.py` | Confidence scoring (1-5) with auto-delegation suggestions |
| `public_urls.py` | Public URL builders for API endpoints |
