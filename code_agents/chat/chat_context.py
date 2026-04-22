"""System context building for chat agents.

Builds the system prompt context including bash tool instructions, rules,
skills, agent memory, MCP tools, user profile, and questionnaire hints.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_context")


def _suggest_skills(user_input: str, agent_name: str, agents_dir: str) -> None:
    """Show skill suggestions based on user input keywords."""
    try:
        from code_agents.agent_system.skill_loader import load_agent_skills

        _keywords = {
            "test": ["test-and-report", "test-fix-loop", "testing-strategy", "write-and-test"],
            "build": ["local-build", "build", "deploy-checklist"],
            "review": ["code-review", "design-review", "security-review"],
            "debug": ["debug"],
            "deploy": ["deploy", "deploy-checklist", "kibana-logs"],
            "jira": ["read-ticket", "create-ticket", "update-status"],
            "ticket": ["read-ticket", "create-ticket", "update-status"],
            "analyze": ["system-analysis", "impact-analysis", "architecture"],
            "analysis": ["system-analysis", "impact-analysis"],
            "incident": ["incident-response"],
            "standup": ["standup"],
            "doc": ["documentation"],
            "security": ["security-review", "negative-testing"],
            "refactor": ["tech-debt"],
            "design": ["system-design", "design-review"],
            "api": ["api-testing", "negative-testing"],
            "log": ["kibana-logs", "log-analysis", "debug"],
            "error": ["kibana-logs", "log-analysis", "debug"],
            "coverage": ["test-and-report", "testing-strategy"],
            "plan": ["full-sdlc", "system-design"],
            "performance": ["testing-strategy", "architecture"],
            "implement": ["write-and-test", "write-from-jira"],
            "fix": ["debug", "test-fix-loop"],
            "write": ["write-and-test", "write-from-jira"],
            "java": ["java-spring"],
            "spring": ["java-spring"],
        }

        # Skip if already invoking a skill
        if ":" in user_input and user_input.strip().startswith("/"):
            return

        all_skills = load_agent_skills(agents_dir)
        available = {}
        for s in all_skills.get(agent_name, []):
            available[s.name] = agent_name
        for s in all_skills.get("_shared", []):
            available[s.name] = "_shared"

        input_lower = user_input.lower()
        matched = []
        seen = set()
        for keyword, skill_names in _keywords.items():
            if keyword in input_lower:
                for sname in skill_names:
                    if sname in seen or sname not in available:
                        continue
                    owner = available[sname]
                    prefix = agent_name if owner == agent_name else owner
                    matched.append(f"/{prefix}:{sname}")
                    seen.add(sname)

        if matched:
            from .chat_ui import dim
            suggestions = ", ".join(matched[:3])
            print(f"  {dim(f'💡 Skills: {suggestions}')}")
            print()
    except Exception:
        pass


def _build_system_context(repo: str, agent_name: str, btw_messages: list = None, superpower: bool = False) -> str:
    """Build the system context message for an agent, including bash tool and rules."""
    logger.info("Building system context for agent=%s, repo=%s", agent_name, repo)
    from code_agents.agent_system.rules_loader import load_rules as _load_rules

    repo_name = os.path.basename(repo)
    rules_text = _load_rules(agent_name, repo)

    context = (
        f"IMPORTANT: You are working on the project at: {repo}\n"
        f"Project name: {repo_name}\n"
        f"This is the user's repository — all your analysis, code reading, "
        f"file operations, and responses must be about THIS project's files. "
        f"Do NOT describe the code-agents tool itself.\n"
        f"When reading files, searching code, or explaining architecture — "
        f"always operate within {repo}.\n"
        f"\n"
        f"--- Bash Tool ---\n"
        f"CRITICAL: You CANNOT make HTTP requests or network calls directly from your environment.\n"
        f"The ONLY way to execute commands is by outputting them in ```bash code blocks.\n"
        f"Commands run on the USER'S MACHINE (which has localhost and network access).\n"
        f"The output is automatically sent back to you so you can continue.\n"
        f"\n"
        f"HOW TO USE (follow this pattern exactly):\n"
        f"  1. Explain what you're about to do in 1 sentence\n"
        f"  2. Output exactly ONE command in a ```bash block\n"
        f"  3. STOP and wait — the command will run and output comes back to you\n"
        f"  4. Analyze the result, then propose the next command if needed\n"
        f"\n"
        f"RULES:\n"
        f"  - Output EXACTLY ONE ```bash block per response — never 2, 3, or more\n"
        f"  - After the ```bash block, STOP IMMEDIATELY — do not write more text or commands\n"
        f"  - The user's terminal will run it and send the output back to you\n"
        f"  - Then you can analyze and output the NEXT single command\n"
        f"\n"
        f"FORBIDDEN (never do these):\n"
        f"  - NEVER output multiple ```bash blocks in one response\n"
        f"  - NEVER say 'I cannot reach the server' or 'request was rejected'\n"
        f"  - NEVER write step-by-step instructions for the user to run manually\n"
        f"  - NEVER say 'paste the output here' or 'run this on your machine'\n"
        f"  - NEVER list Step 1, Step 2, Step 3 with separate bash blocks\n"
        f"  - If you need multiple commands, output ONE, wait for result, then output the next\n"
        f"\n"
        f"CORRECT PATTERN:\n"
        f"  You: 'Let me check the build job parameters.'\n"
        f"  ```bash\n"
        f"  curl -s http://127.0.0.1:8000/jenkins/jobs/path/parameters\n"
        f"  ```\n"
        f"  [STOP HERE — wait for output — then respond with analysis + next command]\n"
        f"--- End Bash Tool ---"
    )
    # Inject lean project summary (language, structure, key files)
    try:
        from code_agents.domain.project_context import build_project_summary
        project_summary = build_project_summary(repo)
        if project_summary:
            context += f"\n\n--- Project ---\n{project_summary}\n--- End Project ---"
    except Exception:
        pass

    # Inject per-agent context (agents.md) if available
    try:
        from code_agents.core.config import settings as _ctx_settings
        _agents_md_path = os.path.join(
            str(_ctx_settings.agents_dir),
            agent_name.replace("-", "_"),
            "agents.md",
        )
        if os.path.exists(_agents_md_path):
            with open(_agents_md_path, "r", encoding="utf-8") as _amd:
                _agent_ctx = _amd.read().strip()
            if _agent_ctx:
                # Limit to ~2000 tokens (~8000 chars)
                if len(_agent_ctx) > 8000:
                    _agent_ctx = _agent_ctx[:8000] + "\n... (truncated)"
                context += f"\n\n--- Agent Context ---\n{_agent_ctx}\n--- End Agent Context ---"
    except Exception:
        pass

    # Inject knowledge graph context (if built)
    try:
        from code_agents.knowledge.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(repo)
        if kg.is_stale():
            import threading
            threading.Thread(target=kg.update, daemon=True).start()
        if kg.is_ready:
            kg_summary = kg.get_context_for_prompt("", max_tokens=800)
            if kg_summary:
                context += f"\n\n{kg_summary}"
    except Exception:
        pass

    if rules_text:
        context += f"\n\n--- Rules ---\n{rules_text}\n--- End Rules ---"

    # Inject lean skill index (names + descriptions only — full body loaded on demand)
    try:
        from code_agents.agent_system.skill_loader import load_agent_skills
        from code_agents.core.config import settings
        all_skills = load_agent_skills(settings.agents_dir)
        agent_skills = all_skills.get(agent_name, [])
        shared_skills = all_skills.get("_shared", [])
        if agent_skills or shared_skills:
            lines = [
                "--- Skills (on-demand) ---",
                "IMPORTANT: These are code-agents skills (located in agents/<agent>/skills/*.md),",
                "NOT Claude Code CLI skills (.claude/skills/), NOT Cursor agent skills/tools.",
                "Do NOT look for skill files yourself, do NOT use your own native tool/skill system,",
                "and do NOT say skills are missing. To load a skill, output [SKILL:name] on its own",
                "line. The code-agents harness will resolve and inject the full workflow automatically.",
                "",
            ]
            if agent_skills:
                lines.append("Agent skills:")
                for s in agent_skills:
                    desc = f" — {s.description}" if s.description else ""
                    lines.append(f"  - {s.name}{desc}")
            if shared_skills:
                lines.append("")
                lines.append(f"Engineering skills: {len(shared_skills)} shared workflows also available (architecture, code-review, debug, deploy-checklist, etc). Use [SKILL:name] to load any.")
            lines.append("--- End Skills ---")
            context += "\n\n" + "\n".join(lines)

        # Auto-pilot always gets full agent catalog (it's the primary orchestrator)
        # In superpower mode, any agent gets the catalog too
        if agent_name == "auto-pilot" or superpower:
            from code_agents.agent_system.skill_loader import get_all_agents_with_skills
            catalog = get_all_agents_with_skills(settings.agents_dir)
            if catalog:
                label = "SUPERPOWER: " if superpower and agent_name != "auto-pilot" else ""
                context += f"\n\n--- {label}Sub-Agent Catalog (auto-discovered) ---\n"
                context += catalog
                context += "\n--- End Catalog ---"
    except Exception:
        pass

    # Inject agent memory (persistent learnings)
    try:
        from code_agents.agent_system.agent_memory import load_memory
        memory = load_memory(agent_name)
        if memory:
            context += f"\n\n--- Agent Memory ---\n{memory}\n--- End Memory ---"
    except Exception:
        pass

    # Inject past corrections (learn from user edits)
    try:
        from code_agents.agent_system.agent_corrections import inject_corrections
        # Use the first user message from btw_messages or a generic query
        _corrections_query = ""
        if btw_messages:
            _corrections_query = " ".join(btw_messages[-3:])
        corrections_block = inject_corrections(agent_name, _corrections_query, project_path=repo)
        if corrections_block:
            context += f"\n\n{corrections_block}"
    except Exception:
        pass

    # Inject RAG context (vector-based code search)
    try:
        from code_agents.knowledge.rag_context import RAGContextInjector
        _rag = RAGContextInjector(repo)
        if _rag.store.is_ready():
            _rag_query = ""
            if btw_messages:
                _rag_query = " ".join(btw_messages[-3:])
            rag_block = _rag.get_context(_rag_query)
            if rag_block:
                context += f"\n\n{rag_block}"
    except Exception:
        pass

    # Inject MCP tools (external services) — smart per-agent context
    try:
        from code_agents.integrations.mcp_client import get_servers_for_agent, get_smart_mcp_context
        mcp_servers = get_servers_for_agent(agent_name, repo)
        mcp_text = get_smart_mcp_context(agent_name, mcp_servers)
        if mcp_text:
            context += "\n" + mcp_text
    except Exception:
        pass

    # Inject user profile with role-specific guidance
    user_role = os.getenv("CODE_AGENTS_USER_ROLE", "")
    if user_role:
        role_guidance = {
            "Junior Engineer": "Explain your reasoning step by step. Include context and rationale. Show examples. Ask before making assumptions.",
            "Senior Engineer": "Be concise. Trust their technical judgment. Focus on what's different or non-obvious.",
            "Lead Engineer": "Focus on architecture, trade-offs, and risk. Highlight cross-team impacts. Include 'why' not just 'what'.",
            "Principal Engineer / Architect": "Strategic-level communication. System-wide implications. Long-term maintainability. Design patterns.",
            "Engineering Manager": "Status summaries. Timeline impacts. Team dependency analysis. Risk assessment with business context.",
        }
        guidance = role_guidance.get(user_role, f"The user is a {user_role}.")
        context += f"\n\nUser role: {user_role}. {guidance}"

    # Build location — tell agent where to build/test
    _build_loc = os.getenv("CODE_AGENTS_BUILD_LOCATION", "ask").strip().lower()
    _jenkins_url = os.getenv("JENKINS_URL", "").strip()
    if _jenkins_url:
        if _build_loc == "jenkins":
            context += (
                "\n\n--- Build/Test Location ---\n"
                "ALWAYS use Jenkins for builds and tests. Never run build/test commands locally.\n"
                f"Jenkins is available at {_jenkins_url}. Use the /testing/run API or delegate to jenkins-cicd agent.\n"
                "--- End Build Location ---"
            )
        elif _build_loc == "local":
            context += (
                "\n\n--- Build/Test Location ---\n"
                "Run builds and tests LOCALLY using bash commands.\n"
                "--- End Build Location ---"
            )
        else:
            # ask (default) — tell agent to ask user
            context += (
                "\n\n--- Build/Test Location ---\n"
                f"Jenkins is available at {_jenkins_url}. Before running any build or test command, "
                "ASK the user: \"Where should I build/test? (1) Local  (2) Jenkins\"\n"
                "Use [QUESTION:build_location] to ask. If the user says Jenkins, delegate to jenkins-cicd agent "
                "or use the /testing/run API. If local, run commands via bash.\n"
                "--- End Build Location ---"
            )

    # Questionnaire hint — agents can ask structured questions
    context += (
        "\n\nWhen you need clarification from the user, you can output [QUESTION:key] tags.\n"
        "Built-in keys: environment, database, deploy_strategy, branch, test_scope, review_depth, jira_type, build_location.\n"
        "Or use a free-form question: [QUESTION:Should we include integration tests?]\n"
        "The user will answer interactively and the result will be injected into the next message."
    )

    logger.debug("System context built for agent=%s: ~%d chars", agent_name, len(context))

    # Agent chaining hint for auto-pilot
    if agent_name == "auto-pilot":
        context += (
            "\n\nYou can invoke specialist agents as tools by outputting: [DELEGATE:agent-name] your prompt here\n"
            "The delegate executes and its result returns to you. You synthesize the findings and respond to the user."
        )

    # Requirement-first workflow: agent restates requirements before executing
    from .chat_input import get_current_mode
    _mode = get_current_mode()

    if superpower:
        context += (
            "\n\n--- SUPERPOWER MODE ACTIVE ---\n"
            "You are in SUPERPOWER mode. Execute commands immediately without asking for approval.\n"
            "Do NOT ask 'Proceed?', 'Should I continue?', or wait for confirmation.\n"
            "Do NOT ask for permission to run curl commands — they auto-execute.\n"
            "Show a brief plan summary, then execute immediately.\n"
            "--- End Superpower ---"
        )
    context += (
        "\n\n--- Requirement Protocol ---\n"
        "IMPORTANT: Before starting any work, FIRST restate the user's requirement in your own words "
        "as a short numbered list of what you will do. "
        'Start with "**Understood. Here\'s what I\'ll do:**" then list the steps.\n'
    )
    if superpower:
        context += "Then proceed directly with execution — do NOT wait for confirmation.\n"
    else:
        context += (
            "If the task is large (multiple files, refactoring, migration, rewrite, 5+ steps), "
            "tell the user: \"This is a large task. I recommend switching to Plan mode for a structured approach. "
            'Type /plan or press shift+tab to switch." Then WAIT for user confirmation before proceeding.\n'
        )
    context += (
        "For simple tasks (single file fix, quick question, small change), proceed directly after restating.\n"
        "--- End Requirement Protocol ---"
    )

    # Plan mode context injection
    try:
        from code_agents.agent_system.plan_manager import get_plan_manager
        pm = get_plan_manager()
        if pm.is_plan_mode or _mode == "plan":
            context += (
                "\n\n--- Plan Mode ---\n"
                "You are in PLAN MODE. Do NOT execute commands or write code yet. "
                "Instead, analyze the request and produce a STRUCTURED PLAN:\n"
                "1. Restate the requirement\n"
                "2. List each step with: description, files to modify, and what changes to make\n"
                "3. Note any risks or dependencies between steps\n"
                "4. Estimate scope (small/medium/large)\n\n"
                "After presenting the plan, you MUST end your response with exactly this question block:\n\n"
                "**How would you like to proceed?**\n"
                "1. Accepted — execute this plan as-is\n"
                "2. Edit — modify the plan with changes\n"
                "3. Rejected — discard this plan entirely\n\n"
                "Wait for the user's choice before doing anything.\n"
                "--- End Plan Mode ---"
            )
            # Show existing plan if one is active
            plan_display = pm.format_plan()
            if plan_display and plan_display != "  No active plan.":
                context += f"\n\n--- Current Plan ---\n{plan_display}\n--- End Current Plan ---"
    except Exception:
        pass

    # Inject /btw side messages (user corrections/requirements during session)
    if btw_messages:
        context += "\n\n[USER UPDATES — apply to current task]:\n"
        for msg in btw_messages:
            context += f"- {msg}\n"

    return context
