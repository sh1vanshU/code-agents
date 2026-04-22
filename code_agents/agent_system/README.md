# Agent System

Agent orchestration, skills, memory, and planning internals.

## Modules

| Module | Description |
|--------|-------------|
| `agent_memory.py` | Persistent agent learnings at ~/.code-agents/memory/<agent>.md |
| `agent_corrections.py` | Agent self-correction and learning from mistakes |
| `agent_replay.py` | Replay and debug agent sessions |
| `skill_loader.py` | On-demand [SKILL:name] loading from agents/<name>/skills/*.md |
| `skill_marketplace.py` | Skill discovery, sharing, and marketplace |
| `smart_orchestrator.py` | SmartOrchestrator for multi-agent coordination |
| `subagent_dispatcher.py` | [DELEGATE:agent-name] tag for auto-delegation |
| `session_scratchpad.py` | Session state persistence via [REMEMBER:key=value] tags |
| `plan_manager.py` | Plan lifecycle management (/plan command) |
| `requirement_confirm.py` | Spec-before-execution gate for ambiguous tasks |
| `rules_loader.py` | Global + project rules auto-refresh every message |
| `question_parser.py` | Parse [QUESTION:key] tags from agent responses |
| `questionnaire.py` | Tabbed wizard UI for upfront agent questions |
| `bash_tool.py` | Safe bash command execution for agents |
