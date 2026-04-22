# Code Agents — setup guide

This document complements the [README](README.md) with **local LLM** setup, environment variables, and switching between backends.

## Quick path: `install.sh`

From the repo (or after cloning to `~/.code-agents`):

```bash
bash ~/.code-agents/install.sh
```

The installer:

- Installs Python dependencies (Poetry) and optional **cursor-agent-sdk** (Cursor CLI backend).
- Optionally installs **Ollama** and pulls a default coder model (`qwen2.5-coder:7b`, overridable with `CODE_AGENTS_DEFAULT_OLLAMA_MODEL`).
- Appends a **local LLM** template to `~/.code-agents/config.env` if `CODE_AGENTS_LOCAL_LLM_URL` is not already set.

Set **`SKIP_OLLAMA=1`** to skip Ollama download/install (defaults are still appended when the file is new).

Then in your project:

```bash
cd /path/to/your-project
code-agents init
code-agents start
code-agents chat
```

## Default backend: `local`

The product default is **`CODE_AGENTS_BACKEND=local`**: all traffic goes to an **OpenAI-compatible** HTTP API (`POST {base}/v1/chat/completions`). Typical URL for Ollama:

```text
CODE_AGENTS_LOCAL_LLM_URL=http://127.0.0.1:11434/v1
```

Other runtimes (LM Studio, llama.cpp server, vLLM) work if they expose the same API shape.

| Variable | Purpose |
|----------|---------|
| `CODE_AGENTS_BACKEND` | `local` (default), `cursor`, `claude`, `claude-cli`, or `cursor_http` |
| `CODE_AGENTS_LOCAL_LLM_URL` | Base URL including `/v1` |
| `CODE_AGENTS_LOCAL_LLM_API_KEY` | Bearer token (many local servers ignore this; use `local` if unsure) |
| `CODE_AGENTS_MODEL` | Model id as understood by the server (e.g. `qwen2.5-coder:7b`) |

If `CODE_AGENTS_LOCAL_LLM_URL` is unset, **`CURSOR_API_URL`** is used as a migration fallback (same path as older docs).

## `code-agents init`

The init wizard offers **Local LLM** first. It writes the variables above into `~/.code-agents/config.env` (and optionally repo-specific files — same merge order as runtime).

## Health check

```bash
code-agents doctor
```

You should see **Effective backend: local** and a reachable **CODE_AGENTS_LOCAL_LLM_URL** (or fix the URL / start Ollama).

## Switching to Cursor or Claude

- **Cursor (CLI or cloud HTTP):** set `CODE_AGENTS_BACKEND=cursor`, provide **`CURSOR_API_KEY`**, and optionally `CURSOR_API_URL` for HTTP-only mode.
- **Claude API:** `CODE_AGENTS_BACKEND=claude` and **`ANTHROPIC_API_KEY`**.
- **Claude CLI:** `CODE_AGENTS_BACKEND=claude-cli` (subscription; run `claude` once to log in).

In chat you can also use **`/backend`** and pick `local`, `cursor`, `claude`, or `claude-cli`.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `Cannot connect to local LLM` | Ollama running? `ollama serve` / app running; URL matches port **11434** by default. |
| `404` on `/v1/models` | Ollama version may differ; ensure OpenAI compatibility; try upgrading Ollama. |
| Wrong answers / slow | Model size vs GPU/RAM; try a smaller quant or a different `CODE_AGENTS_MODEL`. |
| Still expecting Cursor only | Set `CODE_AGENTS_BACKEND=cursor` explicitly; default is now `local`. |

For a full variable list see [`.env.example`](.env.example).
