"""Runtime operations: /run, /exec, /bash, /btw, /repo, /endpoints, /superpower, /permissions, /layout, /voice, /plan, /mcp."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_ops")

from .chat_ui import bold, green, yellow, red, cyan, dim, magenta
from .chat_commands import _resolve_placeholders, _run_single_command


def _handle_operations(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle runtime operation slash commands."""

    if command == "/run":
        # Manual run: /run <command> — run only, no agent feedback
        if not arg:
            print(yellow("  Usage: /run <shell command>"))
            return None
        _run_single_command(arg, state.get("repo_path", "."))
        return None

    elif command in ("/execute", "/exec"):
        # Execute + feed output to agent: /execute <command>
        if not arg:
            print(yellow("  Usage: /execute <shell command>"))
            print(dim("  Runs the command and sends output to the agent for analysis."))
            return None
        resolved = _resolve_placeholders(arg)
        if not resolved:
            return None
        output = _run_single_command(resolved, state.get("repo_path", "."))
        # Return special signal for REPL to feed back to agent
        state["_exec_feedback"] = {
            "command": resolved,
            "output": output,
        }
        return "exec_feedback"

    elif command == "/bash":
        if not arg:
            print(dim("  Usage: /bash <command>"))
            print(dim("  Runs directly in terminal — no AI, no approval."))
            print()
        else:
            import subprocess as _sp
            import time as _time
            cwd = state.get("repo_path", os.getcwd())
            print(f"  {bold('$')} {cyan(arg)}")
            t0 = _time.monotonic()
            try:
                result = _sp.run(arg, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
                elapsed = _time.monotonic() - t0
                output = result.stdout or result.stderr or ""
                if output.strip():
                    for line in output.strip().splitlines()[:50]:
                        print(f"  {line}")
                if result.returncode == 0:
                    print(f"  {green('✓')} Done ({elapsed:.1f}s)")
                else:
                    print(f"  {yellow(f'✗ Exit code: {result.returncode}')} ({elapsed:.1f}s)")
            except _sp.TimeoutExpired:
                print(f"  {yellow('✗ Timed out after 120s')}")
                output = ""
                result = None
            except Exception as e:
                print(f"  {yellow(f'✗ Error: {e}')}")
                output = ""
                result = None
            print()
            # Ask if user wants agent to analyze the output
            if output and output.strip():
                try:
                    feed = input(f"  {dim('Feed output to agent? [y/N]:')} ").strip().lower()
                    if feed in ("y", "yes"):
                        rc = result.returncode if result else -1
                        return f"I ran `/bash {arg}` and got (exit={rc}):\n```\n{output[:3000]}\n```\nAnalyze this output."
                except (EOFError, KeyboardInterrupt):
                    pass
                print()

    elif command == "/btw":
        if not arg:
            # Show current btw messages
            btw_msgs = state.get("_btw_messages", [])
            if btw_msgs:
                print()
                print(bold("  Side messages (injected into agent context):"))
                for i, msg in enumerate(btw_msgs, 1):
                    print(f"    {i}. {msg}")
                print()
                print(dim("  /btw clear — remove all"))
            else:
                print(dim("  No side messages. Use: /btw <message>"))
            print()
        elif arg.lower() == "clear":
            state["_btw_messages"] = []
            print(green("  ✓ Side messages cleared."))
            print()
        else:
            btw_list = state.setdefault("_btw_messages", [])
            btw_list.append(arg)
            print(f"  {green('✓')} Noted: {dim(arg[:80])}")
            print(dim("  Agent will see this in the next response."))
            print()

    elif command == "/repo":
        from code_agents.domain.repo_manager import get_repo_manager
        rm = get_repo_manager()

        # Ensure current repo is registered
        current_path = state.get("repo_path", os.getcwd())
        if not rm.repos:
            try:
                rm.add_repo(current_path)
            except ValueError:
                pass  # not a git repo, that's ok

        if not arg:
            # /repo — list all registered repos
            repos = rm.list_repos()
            print()
            if not repos:
                print(dim("  No repos registered. Use /repo add <path> to register one."))
            else:
                print(bold("  Registered repos:"))
                for ctx in repos:
                    is_active = ctx.path == rm.active_repo
                    marker = f" {green('< active')}" if is_active else ""
                    branch_info = f" [{dim(ctx.git_branch)}]" if ctx.git_branch else ""
                    print(f"    {cyan(ctx.name):<28}{branch_info}{marker}")
                    print(f"      {dim(ctx.path)}")
                print()
                print(dim("  Switch: /repo <name>  |  Add: /repo add <path>  |  Remove: /repo remove <name>"))
            print()

        elif arg.startswith("add "):
            # /repo add <path>
            add_path = arg[4:].strip()
            if not add_path:
                print(yellow("  Usage: /repo add <path>"))
                print()
                return None
            add_path = os.path.expanduser(add_path)
            try:
                ctx = rm.add_repo(add_path)
                print()
                print(green(f"  + Registered: {bold(ctx.name)}"))
                print(f"    Path:   {dim(ctx.path)}")
                print(f"    Branch: {dim(ctx.git_branch or 'unknown')}")
                print(f"    Config: {dim(ctx.config_file)}")
                print()
            except ValueError as e:
                print(red(f"  {e}"))
                print()

        elif arg.startswith("remove "):
            # /repo remove <name>
            remove_name = arg[7:].strip()
            if not remove_name:
                print(yellow("  Usage: /repo remove <name>"))
                print()
                return None
            try:
                removed = rm.remove_repo(remove_name)
                if removed:
                    print(green(f"  - Removed: {remove_name}"))
                else:
                    print(yellow(f"  Repo '{remove_name}' not found."))
                    available = ", ".join(c.name for c in rm.list_repos())
                    if available:
                        print(dim(f"  Available: {available}"))
            except ValueError as e:
                print(red(f"  {e}"))
            print()

        else:
            # /repo <name> — switch to repo
            try:
                ctx = rm.switch_repo(arg)
                state["repo_path"] = ctx.path
                # Reload env for the new repo
                from code_agents.core.env_loader import load_all_env
                load_all_env(ctx.path)
                print()
                print(green(f"  Switched to: {bold(ctx.name)}"))
                print(f"    Path:   {dim(ctx.path)}")
                print(f"    Branch: {dim(ctx.git_branch or 'unknown')}")
                print()
            except ValueError as e:
                print(red(f"  {e}"))
                print()

    elif command == "/endpoints":
        from code_agents.cicd.endpoint_scanner import load_cache, scan_all, save_cache, generate_curls, generate_grpc_cmds, generate_kafka_cmds, run_all_endpoints, format_run_report, load_endpoint_config
        repo = state.get("repo_path") or os.getcwd()
        filter_type = (arg or "").strip().lower()

        if filter_type == "scan":
            print()
            print(dim("  Scanning endpoints..."))
            result = scan_all(repo)
            if result.total > 0:
                save_cache(repo, result)
                print(green(f"  Scan complete: {result.summary()}"))
            else:
                print(dim("  No endpoints found in this repo."))
            print()
        elif filter_type.startswith("run"):
            # /endpoints run [rest|grpc|kafka]
            run_parts = filter_type.split()
            run_type = run_parts[1] if len(run_parts) > 1 else "all"
            if run_type not in ("all", "rest", "grpc", "kafka"):
                print(dim(f"  Unknown type '{run_type}'. Use: all, rest, grpc, kafka"))
                print()
            else:
                # Load config
                ep_config = load_endpoint_config(repo)
                base_url = ep_config.get("base_url", "http://localhost:8080")
                auth_header = ep_config.get("auth_header", "")
                timeout = ep_config.get("timeout", 10)

                # Load or scan endpoints
                print()
                result = None
                cached = load_cache(repo)
                if cached:
                    from code_agents.cicd.endpoint_scanner import RestEndpoint, GrpcService, KafkaListener, ScanResult
                    result = ScanResult(
                        repo_name=cached["repo_name"],
                        rest_endpoints=[RestEndpoint(**e) for e in cached.get("rest_endpoints", [])],
                        grpc_services=[GrpcService(**s) for s in cached.get("grpc_services", [])],
                        kafka_listeners=[KafkaListener(**k) for k in cached.get("kafka_listeners", [])],
                    )
                else:
                    print(dim("  No cached endpoints. Scanning first..."))
                    result = scan_all(repo)
                    if result.total > 0:
                        save_cache(repo, result)

                if result and result.total > 0:
                    print(dim(f"  Running {run_type} endpoints against {base_url}..."))
                    print()
                    run_results = run_all_endpoints(
                        result, base_url=base_url, auth_header=auth_header,
                        timeout=timeout, endpoint_type=run_type,
                    )
                    report = format_run_report(run_results)
                    print(report)

                    # Feed report to agent as context for analysis
                    passed = sum(1 for r in run_results if r["passed"])
                    failed = len(run_results) - passed
                    if failed > 0:
                        print(dim("  Failures detected — sending report to agent for analysis..."))
                        print()
                        state["_exec_feedback"] = {
                            "command": f"/endpoints run {run_type}",
                            "output": (
                                f"Endpoint test results ({passed} passed, {failed} failed):\n\n"
                                f"{report}\n\n"
                                "Analyze the failures above. For each failure:\n"
                                "1. Classify: connection refused, auth error, bad request, server error, or timeout\n"
                                "2. Suggest a fix or next diagnostic step\n"
                                "3. If it looks like a code bug, suggest which file to check"
                            ),
                        }
                        return "exec_feedback"
                else:
                    print(dim("  No endpoints found to run."))
                    print()
        else:
            cached = load_cache(repo)
            if not cached:
                print()
                print(dim("  No cached endpoints. Running scan..."))
                result = scan_all(repo)
                if result.total > 0:
                    save_cache(repo, result)
                    cached = load_cache(repo)
                else:
                    print(dim("  No endpoints found in this repo."))
                    print(dim("  Scans Java/Spring @RestController, .proto files, @KafkaListener."))
                    print()

            if cached:
                print()
                print(bold(f"  Endpoints — {cached['repo_name']}"))
                print(f"  {dim(cached['summary'])}")
                print()

                if (not filter_type or filter_type == "rest") and cached.get("rest_endpoints"):
                    print(bold("  REST Endpoints:"))
                    for ep in cached["rest_endpoints"]:
                        method_color = green if ep["method"] == "GET" else yellow if ep["method"] == "POST" else cyan
                        m = ep["method"]
                        p = ep["path"]
                        c = ep.get("controller", "")
                        print(f"    {method_color(m):<7} {p:<40} {dim(c)}")
                    print()

                if (not filter_type or filter_type == "grpc") and cached.get("grpc_services"):
                    print(bold("  gRPC Services:"))
                    for svc in cached["grpc_services"]:
                        print(f"    {cyan(svc['service_name'])}")
                        for m in svc.get("methods", []):
                            print(f"      rpc {m['name']}({dim(m['request_type'])}) -> {dim(m['response_type'])}")
                    print()

                if (not filter_type or filter_type == "kafka") and cached.get("kafka_listeners"):
                    print(bold("  Kafka Listeners:"))
                    for kl in cached["kafka_listeners"]:
                        group_label = f" (group: {kl['group']})" if kl.get("group") else ""
                        print(f"    {magenta(kl['topic'])}{dim(group_label)}  {dim(kl.get('file', ''))}")
                    print()

                print(dim("  /endpoints scan    — rescan"))
                print(dim("  /endpoints rest    — REST only"))
                print(dim("  /endpoints grpc    — gRPC only"))
                print(dim("  /endpoints kafka   — Kafka only"))
                print(dim("  /endpoints run     — run all endpoints"))
                print(dim("  /endpoints run rest/grpc/kafka — run by type"))
                print()

    elif command == "/superpower":
        if arg.lower() == "off":
            state["superpower"] = False
            os.environ.pop("CODE_AGENTS_SUPERPOWER", None)
            print(green("  ✓ Superpower mode OFF. Commands require approval."))
        else:
            state["superpower"] = True
            os.environ["CODE_AGENTS_SUPERPOWER"] = "1"
            print()
            print(yellow("  ⚡ SUPERPOWER MODE ACTIVATED"))
            print(yellow("  All commands auto-execute (except blocklisted)."))
            print(yellow("  Agent edits auto-accepted. Type /superpower off to deactivate."))
        print()

    elif command == "/sandbox":
        from code_agents.devops.sandbox import is_sandbox_available, is_sandbox_enabled

        sub = (arg or "").strip().lower()

        if sub == "off":
            state["sandbox"] = False
            os.environ.pop("CODE_AGENTS_SANDBOX", None)
            print(green("  ✓ Sandbox mode OFF. Commands run without filesystem restrictions."))
        elif sub == "status":
            enabled = is_sandbox_enabled()
            available = is_sandbox_available()
            status_str = green("ON") if enabled else dim("OFF")
            avail_str = green("available") if available else yellow("unavailable (non-macOS)")
            print(f"  Sandbox: {status_str}  (sandbox-exec: {avail_str})")
            if enabled:
                cwd = state.get("repo_path", os.getcwd())
                print(dim(f"  Writes restricted to: {cwd}, /tmp"))
        else:
            available = is_sandbox_available()
            state["sandbox"] = True
            os.environ["CODE_AGENTS_SANDBOX"] = "1"
            print()
            if available:
                cwd = state.get("repo_path", os.getcwd())
                print(green("  🔒 SANDBOX MODE ACTIVATED"))
                print(green(f"  Filesystem writes restricted to: {cwd}, /tmp"))
                print(dim("  Type /sandbox off to deactivate, /sandbox status to check."))
            else:
                print(yellow("  ⚠ Sandbox enabled but sandbox-exec not available on this platform."))
                print(yellow("  Commands will run unsandboxed with a warning."))
        print()

    elif command == "/layout":
        from code_agents.chat.terminal_layout import supports_layout
        if arg == "on":
            if not supports_layout():
                print(yellow("  Terminal does not support fixed layout (not a TTY or TERM is dumb)."))
                print()
            else:
                state["_fixed_layout"] = True
                from code_agents.chat.terminal_layout import enter_layout, draw_input_bar
                enter_layout()
                draw_input_bar(state.get("agent", ""), os.getenv("CODE_AGENTS_NICKNAME", "you"), state.get("superpower", False))
                print(green("  ✓ Fixed layout ON (experimental). /layout off to restore."))
        elif arg == "off":
            state["_fixed_layout"] = False
            from code_agents.chat.terminal_layout import exit_layout
            exit_layout()
            print(green("  ✓ Layout restored to normal."))
        else:
            print(dim("  /layout on — fixed input at bottom (experimental)"))
            print(dim("  /layout off — normal sequential mode"))
        print()

    elif command == "/voice":
        from code_agents.ui.voice_input import is_available, listen_and_transcribe, get_install_instructions
        if not is_available():
            print()
            print(dim(get_install_instructions()))
            print()
        else:
            print(f"  {bold('🎤 Listening...')} (speak now, {arg or '10'}s timeout)")
            timeout = int(arg) if arg and arg.isdigit() else 10
            text = listen_and_transcribe(timeout=timeout)
            if text:
                print(f"  {green('🎤')} \"{text}\"")
                try:
                    confirm = input(f"  {dim('Send this? [Y/n/edit]:')} ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    confirm = "n"
                if confirm in ("", "y", "yes"):
                    return text  # use as user input
                elif confirm == "edit":
                    try:
                        import readline
                        readline.set_startup_hook(lambda: readline.insert_text(text))
                        edited = input(f"  {bold('Edit:')} ").strip()
                        readline.set_startup_hook()
                        if edited:
                            return edited
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    print(dim("  Cancelled."))
            else:
                print(dim("  No speech detected. Try again or type your message."))
            print()

    elif command == "/plan":
        from code_agents.agent_system.plan_manager import (
            load_plan, list_plans, update_step,
            get_plan_manager, PlanStatus, ApprovalMode,
        )
        pm = get_plan_manager()

        if not arg:
            # If a plan is proposed, show the questionnaire
            if pm.active_plan and pm.active_plan.status == PlanStatus.PROPOSED:
                print()
                print(pm.format_plan())
                print()
                print("  Agent has proposed a plan. How would you like to proceed?")
                print()
                from code_agents.agent_system.questionnaire import _question_selector
                _approval_options = [
                    "Yes, auto-accept edits",
                    "Yes, manually approve edits",
                    "Tell the agent what to change",
                ]
                _approval_idx = _question_selector("  Approve:", _approval_options, default=0)
                if _approval_idx == 0:
                    pm.approve(ApprovalMode.AUTO_ACCEPT)
                    # Auto-switch to edit mode if user chose "plan → auto-accept" flow
                    if state.get("_auto_edit_after_plan"):
                        from .chat_input import set_mode
                        set_mode("edit")
                        state.pop("_auto_edit_after_plan", None)
                        print(green("  \u2713 Plan approved. Switched to accept-edits mode."))
                    else:
                        print(green("  \u2713 Plan approved (auto-accept edits)."))
                elif _approval_idx == 1:
                    pm.approve(ApprovalMode.MANUAL_APPROVE)
                    print(green("  \u2713 Plan approved (manual approval per edit)."))
                elif _approval_idx == 2:
                    try:
                        feedback = input("  Feedback: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        feedback = ""
                    if feedback:
                        pm.edit_plan(feedback)
                        print(green(f"  \u2713 Feedback sent. Plan returned to draft."))
                    else:
                        print(dim("  No feedback provided."))
                print()
            elif pm.active_plan:
                # Show current plan status
                print()
                print(pm.format_plan())
                status = pm.get_status()
                print()
                print(dim(f"  Status: {status.get('status', 'unknown')}"))
                if status.get("approval_mode"):
                    print(dim(f"  Mode: {status['approval_mode']}"))
                print()
                print(dim("  /plan approve        — approve the plan"))
                print(dim("  /plan reject         — reject the plan"))
                print(dim("  /plan edit <feedback> — request changes"))
                print(dim("  /plan status         — show progress"))
                print(dim("  /plan complete       — mark plan done"))
                print()
            else:
                # No active enhanced plan — fall back to legacy file plans
                plans = list_plans()
                if plans:
                    print()
                    print(bold("  Saved plans:"))
                    for p in plans[:10]:
                        print(f"    {dim(p['id'])}  {p['title']:<40} {cyan(p['progress'])}")
                    print()
                    print(dim("  /plan <prompt> — ask agent to create a plan"))
                    print(dim("  /plan approve — approve the active plan"))
                    print(dim("  /plan status  — show current plan progress"))
                else:
                    print()
                    print(dim("  No plans yet. Ask the agent to create one:"))
                    print(dim("  Example: 'Create a plan to implement login feature'"))
                print()
        elif arg == "approve":
            if pm.active_plan and pm.active_plan.status in (PlanStatus.DRAFT, PlanStatus.PROPOSED):
                # Enhanced plan — approve with optional mode
                pm.approve(ApprovalMode.AUTO_ACCEPT)
                print(green(f"  \u2713 Plan approved: {pm.active_plan.title if pm.active_plan else 'plan'}"))
                print(dim("  Mode: auto-accept edits"))
            else:
                # Legacy file-based plan
                plan_id = state.get("_last_plan_id")
                if plan_id:
                    state["plan_active"] = plan_id
                    plan = load_plan(plan_id)
                    if plan:
                        print(green(f"  \u2713 Plan approved: {plan['title']}"))
                        print(dim(f"  Agent will follow {plan['total']} steps."))
                else:
                    print(yellow("  No plan to approve. Ask the agent to create one first."))
            print()
        elif arg.startswith("approve manual"):
            if pm.active_plan:
                pm.approve(ApprovalMode.MANUAL_APPROVE)
                print(green(f"  \u2713 Plan approved: {pm.active_plan.title if pm.active_plan else 'plan'}"))
                print(dim("  Mode: manually approve each edit"))
            else:
                print(yellow("  No plan to approve."))
            print()
        elif arg == "status":
            # Show enhanced plan status if active
            if pm.active_plan:
                print()
                print(pm.format_plan())
                status = pm.get_status()
                print()
                print(dim(f"  Completed: {status.get('completed_steps', 0)}/{status.get('steps', 0)} steps"))
                print()
            else:
                # Fall back to legacy file plan
                plan_id = state.get("plan_active")
                if plan_id:
                    plan = load_plan(plan_id)
                    if plan:
                        print()
                        print(bold(f"  {plan['title']}"))
                        for i, step in enumerate(plan["steps"]):
                            if step["done"]:
                                print(f"    {green(chr(0x2713))} {step['text']}")
                            elif i == plan["current_step"]:
                                print(f"    {yellow(chr(0x2192))} {bold(step['text'])}")
                            else:
                                print(f"    {dim(chr(0x25cb))} {dim(step['text'])}")
                        done = sum(1 for s in plan["steps"] if s["done"])
                        print(f"\n  Progress: {done}/{plan['total']}")
                        print()
                else:
                    print(dim("  No active plan. Use /plan approve to activate."))
                    print()
        elif arg.startswith("edit"):
            feedback = arg[4:].strip()
            if pm.active_plan:
                if feedback:
                    pm.edit_plan(feedback)
                    print(green(f"  \u2713 Feedback recorded. Plan returned to draft."))
                else:
                    # No feedback text — try legacy file edit
                    plan_id = state.get("plan_active") or state.get("_last_plan_id")
                    if plan_id:
                        plan = load_plan(plan_id)
                        if plan:
                            editor = os.environ.get("EDITOR", "vi")
                            import subprocess as _sp
                            _sp.run([editor, plan["path"]])
                    else:
                        print(dim("  Usage: /plan edit <feedback>"))
            else:
                plan_id = state.get("plan_active") or state.get("_last_plan_id")
                if plan_id:
                    plan = load_plan(plan_id)
                    if plan:
                        editor = os.environ.get("EDITOR", "vi")
                        import subprocess as _sp
                        _sp.run([editor, plan["path"]])
                else:
                    print(dim("  No plan to edit."))
            print()
        elif arg == "reject":
            if pm.active_plan:
                title = pm.active_plan.title
                pm.reject()
                print(green(f"  \u2713 Plan rejected: {title}"))
            else:
                state.pop("plan_active", None)
                state.pop("_last_plan_id", None)
                print(green("  \u2713 Plan rejected."))
            print()
        elif arg == "complete":
            if pm.active_plan and pm.active_plan.status in (PlanStatus.EXECUTING, PlanStatus.APPROVED):
                title = pm.active_plan.title
                pm.complete()
                print(green(f"  \u2713 Plan completed: {title}"))
            else:
                print(dim("  No executing plan to complete."))
            print()
        elif arg == "list":
            plans = list_plans()
            if plans:
                print()
                print(bold("  All plans:"))
                for p in plans:
                    print(f"    {dim(p['id'])}  {p['title']:<40} {cyan(p['progress'])}")
            else:
                print(dim("  No plans saved."))
            print()
        else:
            # /plan <prompt> — treat as a message to agent asking to create a plan
            return "plan_prompt"

    elif command == "/permissions":
        from code_agents.chat.chat_commands import (
            _load_agent_autorun_config,
            _load_global_autorun_config,
        )
        from code_agents.agent_system.rules_loader import PROJECT_RULES_DIRNAME
        from pathlib import Path

        agent_name = state.get("agent", "")
        cwd = state.get("repo_path", "") or os.getenv("TARGET_REPO_PATH", "")
        is_superpower = state.get("superpower", False)
        auto_run = os.getenv("CODE_AGENTS_AUTO_RUN", "true").lower() not in ("0", "false", "no")

        print()
        # ── Current mode ──
        print(bold("  Permissions"))
        print()
        print(f"  Auto-run:   {green('ON') if auto_run else red('OFF')}  (read-only commands auto-execute)")
        print(f"  Superpower: {yellow('ON ⚡') if is_superpower else dim('OFF')}  (all commands auto-execute)")
        print()

        # ── Agent autorun rules ──
        if agent_name:
            config = _load_agent_autorun_config(agent_name)
            global_config = _load_global_autorun_config()
            agent_allow = [p for p in config.get("allow", []) if p not in global_config.get("allow", [])]
            agent_block = [p for p in config.get("block", []) if p not in global_config.get("block", [])]

            print(bold(f"  Agent: {agent_name}"))
            if agent_allow:
                print(green(f"    Allow ({len(agent_allow)}):"), ", ".join(f'"{p}"' for p in agent_allow[:10]))
                if len(agent_allow) > 10:
                    print(dim(f"      ... and {len(agent_allow) - 10} more"))
            if agent_block:
                print(red(f"    Block ({len(agent_block)}):"), ", ".join(f'"{p}"' for p in agent_block[:10]))
                if len(agent_block) > 10:
                    print(dim(f"      ... and {len(agent_block) - 10} more"))
            if not agent_allow and not agent_block:
                print(dim("    No agent-specific rules (using global defaults)"))

            global_allow_count = len(global_config.get("allow", []))
            global_block_count = len(global_config.get("block", []))
            print(dim(f"    Global: {global_allow_count} allow, {global_block_count} block patterns"))
            print()

            # ── Trusted/saved commands ──
            if cwd:
                rules_file = Path(cwd) / PROJECT_RULES_DIRNAME / f"{agent_name}.md"
                if rules_file.is_file():
                    try:
                        content = rules_file.read_text().strip()
                        trusted_cmds = [
                            line.strip()
                            for line in content.splitlines()
                            if line.strip() and not line.startswith("#") and not line.startswith("---")
                        ]
                        if trusted_cmds:
                            print(bold(f"  Saved commands ({len(trusted_cmds)}):"))
                            for tc in trusted_cmds[:15]:
                                print(f"    {green('✓')} {tc[:100]}")
                            if len(trusted_cmds) > 15:
                                print(dim(f"      ... and {len(trusted_cmds) - 15} more"))
                            print(dim(f"    File: {rules_file}"))
                        else:
                            print(dim("  No saved/trusted commands for this agent."))
                    except OSError:
                        print(dim("  No saved/trusted commands for this agent."))
                else:
                    print(dim("  No saved/trusted commands for this agent."))
        else:
            print(dim("  No agent selected."))

        print()
        print(dim("  Toggle: /superpower [off]  ·  Set: CODE_AGENTS_AUTO_RUN=false"))
        print()

    elif command == "/confirm":
        from code_agents.agent_system.requirement_confirm import RequirementStatus, is_confirm_enabled

        sub = (arg or "").strip().lower()

        if sub == "on":
            state["_require_confirm_enabled"] = True
            print(green("  ✓ Requirement confirmation ON."))
            print(dim("  Agent will produce a spec before executing tasks."))
        elif sub == "off":
            state["_require_confirm_enabled"] = False
            print(green("  ✓ Requirement confirmation OFF."))
            print(dim("  Agent will execute tasks immediately."))
        elif sub == "show":
            confirmed = state.get("_confirmed_requirement")
            if confirmed:
                print()
                print(bold("  Confirmed Requirement:"))
                for line in confirmed.strip().splitlines():
                    print(f"    {line}")
            else:
                print(dim("  No confirmed requirement in this session."))
        else:
            # /confirm with no args — show current status
            enabled = is_confirm_enabled(state)
            req_status = state.get("_req_status", RequirementStatus.NONE)
            # Normalize to enum if stored as string
            if isinstance(req_status, str):
                try:
                    req_status = RequirementStatus(req_status)
                except ValueError:
                    req_status = RequirementStatus.NONE

            print()
            print(bold("  Requirement Confirmation"))
            print()
            print(f"  Enabled: {green('ON') if enabled else dim('OFF')}")
            print(f"  Status:  {yellow(req_status.value) if req_status != RequirementStatus.NONE else dim(req_status.value)}")

            if req_status == RequirementStatus.CONFIRMED and state.get("_confirmed_requirement"):
                preview = state["_confirmed_requirement"].strip().splitlines()[0][:80]
                print(f"  Spec:    {dim(preview)}")
            print()
            print(dim("  /confirm on   — enable (agent produces spec before executing)"))
            print(dim("  /confirm off  — disable (agent executes immediately)"))
            print(dim("  /confirm show — show confirmed requirement spec"))
        print()

    elif command == "/mcp":
        from code_agents.integrations.mcp_client import load_mcp_config, get_servers_for_agent
        servers = get_servers_for_agent(state.get("agent", ""), state.get("repo_path", ""))
        if not servers:
            print(dim("  No MCP servers configured."))
            print(dim("  Create ~/.code-agents/mcp.yaml or .code-agents/mcp.yaml"))
        else:
            print()
            print(bold("  MCP Servers:"))
            for name, srv in servers.items():
                transport = "stdio" if srv.is_stdio else "SSE"
                agents_str = ", ".join(srv.agents) if srv.agents else "all"
                print(f"    {cyan(name)} ({transport}) → agents: {agents_str}")
        print()

    elif command in ("/undo", "/rollback", "/revert"):
        from code_agents.git_ops.action_log import get_current_log, undo_action
        log = get_current_log()
        if not log:
            print(yellow("  No action log for this session."))
            print()
            return None

        if arg == "list":
            actions = log.get_undoable()
            if not actions:
                print(dim("  No undoable actions."))
            else:
                print()
                print(bold("  Undoable actions:"))
                from datetime import datetime as _dt
                for i, a in enumerate(actions, 1):
                    ts = _dt.fromtimestamp(a.timestamp).strftime("%H:%M:%S")
                    print(f"    {dim(f'{i}.')} {a.description}  {dim(ts)}")
            print()
            return None

        dry = arg == "dry-run"
        actions = log.get_undoable()
        if not actions:
            print(dim("  Nothing to undo."))
            print()
            return None

        action = actions[0]
        print(f"  Last action: {bold(action.description)}")

        if arg == "all":
            for a in actions:
                ok, msg = undo_action(a, dry_run=dry)
                icon = green("✓") if ok else red("✗")
                print(f"  {icon} {msg}")
                if ok and not dry:
                    log.pop_last()
        else:
            if not dry:
                try:
                    confirm = input(f"  Undo? {dim('[y/N]')} ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    confirm = "n"
                if confirm not in ("y", "yes"):
                    print(dim("  Cancelled."))
                    print()
                    return None
            ok, msg = undo_action(action, dry_run=dry)
            icon = green("✓") if ok else red("✗")
            prefix = dim("[dry-run] ") if dry else ""
            print(f"  {icon} {prefix}{msg}")
            if ok and not dry:
                log.pop_last()
        print()

    elif command in ("/diff-preview", "/diffmode"):
        # Toggle diff preview mode
        current = state.get("diff_preview", os.getenv("CODE_AGENTS_DIFF_PREVIEW", "false").lower() == "true")
        if arg in ("on", "true", "1"):
            state["diff_preview"] = True
            print(green("  ✓ Diff preview mode: ON"))
        elif arg in ("off", "false", "0"):
            state["diff_preview"] = False
            print(yellow("  ✗ Diff preview mode: OFF"))
        elif arg == "status":
            status = green("ON") if current else dim("OFF")
            print(f"  Diff preview mode: {status}")
        else:
            # Toggle
            state["diff_preview"] = not current
            new_status = green("ON") if state["diff_preview"] else dim("OFF")
            print(f"  Diff preview mode: {new_status}")
        print()

    elif command in ("/bg", "/tasks"):
        from code_agents.devops.background_agent import (
            BackgroundAgentManager, interactive_tasks_panel, render_tasks_panel,
        )
        mgr = BackgroundAgentManager.get_instance()

        if not arg:
            # Interactive panel
            result = interactive_tasks_panel(mgr)
            if result is None:
                pass  # Esc / no tasks
            elif result == "stop_all":
                count = mgr.stop_all()
                if count:
                    print(green(f"  Stopped {count} background task(s)."))
                else:
                    print(dim("  No running tasks to stop."))
                print()
            elif result.startswith("stop:"):
                task_id = result[5:]
                ok = mgr.stop_task(task_id)
                if ok:
                    print(green(f"  Stopped task {task_id}"))
                else:
                    print(yellow(f"  Task {task_id} not running."))
                print()
            else:
                # task_id — view result
                task = mgr.get_task(result)
                if task:
                    print()
                    print(bold(f"  Task: {task.name}"))
                    print(f"  ID:     {task.task_id}")
                    print(f"  Agent:  {task.agent}")
                    print(f"  Status: {task.status.value} {task.status_icon}")
                    print(f"  Time:   {task.elapsed_str}")
                    if task.result:
                        print()
                        print(bold("  Result:"))
                        for line in task.result.splitlines()[:20]:
                            print(f"    {line}")
                    if task.error:
                        print(red(f"  Error: {task.error}"))
                    print()
        elif arg == "list":
            panel = render_tasks_panel(mgr)
            print(panel)
        elif arg.startswith("stop "):
            task_id = arg[5:].strip()
            ok = mgr.stop_task(task_id)
            if ok:
                print(green(f"  Stopped task {task_id}"))
            else:
                print(yellow(f"  Task {task_id} not found or not running."))
            print()
        elif arg == "stop-all":
            count = mgr.stop_all()
            if count:
                print(green(f"  Stopped {count} task(s)."))
            else:
                print(dim("  No running tasks to stop."))
            print()
        elif arg == "clean":
            count = mgr.remove_completed()
            if count:
                print(green(f"  Removed {count} completed task(s)."))
            else:
                print(dim("  No completed tasks to remove."))
            print()
        else:
            print(dim("  /bg              — interactive task panel"))
            print(dim("  /bg list         — show all tasks"))
            print(dim("  /bg stop <id>    — stop a task"))
            print(dim("  /bg stop-all     — stop all running tasks"))
            print(dim("  /bg clean        — remove completed tasks"))
            print()

    elif command == "/doctor":
        from code_agents.cli.cli import cmd_doctor
        cmd_doctor()
        print()

    elif command in ("/install-hooks", "/hooks"):
        from code_agents.git_ops.git_hooks import GitHooksManager
        repo = state.get("repo_path", os.getcwd())
        mgr = GitHooksManager(repo)
        if arg == "status":
            status = mgr.status()
            for hook, installed in status.items():
                icon = green("✓") if installed else dim("✗")
                print(f"  {icon} {hook}")
        elif arg == "uninstall":
            removed = mgr.uninstall()
            print(f"  {green('✓')} Removed: {', '.join(removed)}" if removed else dim("  No hooks to remove."))
        else:
            installed = mgr.install()
            print(f"  {green('✓')} Installed: {', '.join(installed)}" if installed else dim("  Already installed."))
        print()

    elif command in ("/env-health",):
        from code_agents.reporters.env_health import check_env_health
        report = check_env_health()
        print(report)
        print()

    elif command == "/incident":
        from code_agents.reporters.incident import start_incident
        start_incident(arg or "")
        print()

    elif command in ("/ci-heal", "/self-heal", "/ci-fix"):
        import shlex
        from code_agents.devops.ci_self_heal import CISelfHealer, format_heal_result

        parts = shlex.split(arg) if arg else []
        build_id = ""
        source = "jenkins"
        max_attempts = 3
        dry_run = False
        log_file = ""
        build_url = ""
        idx = 0
        while idx < len(parts):
            p = parts[idx]
            if p in ("--build", "-b") and idx + 1 < len(parts):
                build_id = parts[idx + 1]; idx += 2
            elif p in ("--source", "-s") and idx + 1 < len(parts):
                source = parts[idx + 1]; idx += 2
            elif p in ("--max-attempts", "-m") and idx + 1 < len(parts):
                max_attempts = int(parts[idx + 1]); idx += 2
            elif p == "--dry-run":
                dry_run = True; idx += 1
            elif p in ("--log-file", "-f") and idx + 1 < len(parts):
                log_file = parts[idx + 1]; idx += 2
            elif p in ("--url", "-u") and idx + 1 < len(parts):
                build_url = parts[idx + 1]; idx += 2
            else:
                idx += 1

        cwd = state.get("repo_path", os.getcwd())
        log_text = ""
        if log_file:
            try:
                with open(log_file) as f:
                    log_text = f.read()
                source = "generic"
            except OSError as exc:
                print(red(f"  Cannot read log file: {exc}"))
                return None

        healer = CISelfHealer(cwd=cwd, max_attempts=max_attempts, dry_run=dry_run)
        result = healer.heal(build_url=build_url, build_id=build_id, source=source, log_text=log_text)
        print()
        print(format_heal_result(result))
        if result.healed:
            print(green(f"  Build healed after {result.total_attempts} attempt(s)"))
        elif result.final_status == "dry_run":
            print(yellow("  Dry run complete — no changes made"))
        else:
            print(red(f"  Could not heal build: {result.final_status}"))
        print()

    else:
        return "_not_handled"

    return None
