"""Slash command handlers for high-impact features — benchmark, workspace, pipeline, share."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_features")


def _handle_features(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle /benchmark, /workspace, /pipeline, /share slash commands."""

    if command in ("/benchmark", "/bench"):
        _do_benchmark(arg, state, url)

    elif command == "/bench-compare":
        _do_bench_compare(arg)

    elif command == "/bench-trend":
        _do_bench_trend(arg)

    elif command in ("/workspace", "/ws"):
        _do_workspace(arg, state, url)

    elif command in ("/workspace-cross-deps", "/cross-deps"):
        _do_workspace_cross_deps(arg, state)

    elif command in ("/workspace-pr", "/ws-pr"):
        _do_workspace_pr(arg, state)

    elif command in ("/pipeline", "/pipe"):
        _do_pipeline(arg, state, url)

    elif command == "/share":
        _do_share(arg, state, url)

    return None


def _do_benchmark(arg: str, state: dict, url: str) -> None:
    """Run benchmarks from chat."""
    import asyncio
    from code_agents.testing.benchmark import BenchmarkRunner

    parts = arg.strip().split() if arg.strip() else []

    if parts and parts[0] == "list":
        reports = BenchmarkRunner.list_reports()
        if not reports:
            print("  No benchmark reports saved.")
            return
        print("\n  Saved Benchmarks:")
        for r in reports[:5]:
            s = r["summary"]
            print(f"    {r['run_id']}  quality={s.get('avg_quality', '?')}/5  latency={s.get('avg_latency_ms', '?')}ms")
        print()
        return

    agents = [state.get("agent_name", "code-writer")]
    runner = BenchmarkRunner(agents=agents, url=url, judge=True)

    print(f"\n  Running benchmark {runner.run_id} for {', '.join(agents)}...")

    def progress(done, total, result):
        status = "ERR" if result.error else f"{result.quality_score}/5"
        print(f"  [{done}/{total}] {result.task_name:<30} {status}  ({result.latency_ms}ms)")

    report = asyncio.run(runner.run(progress_callback=progress))
    runner.save_report(report)
    print()
    BenchmarkRunner.print_report(report)


def _do_bench_compare(arg: str) -> None:
    """Compare benchmark runs for regressions."""
    from code_agents.testing.benchmark_regression import RegressionDetector, format_comparison

    parts = arg.strip().split() if arg.strip() else []
    baseline_id = parts[0] if len(parts) >= 1 else ""
    current_id = parts[1] if len(parts) >= 2 else ""

    print()
    detector = RegressionDetector()
    result = detector.compare(baseline_id, current_id)
    format_comparison(result)


def _do_bench_trend(arg: str) -> None:
    """Show benchmark quality trend."""
    from code_agents.testing.benchmark_regression import RegressionDetector, format_trend

    parts = arg.strip().split() if arg.strip() else []
    n = 10
    if parts:
        try:
            n = int(parts[0])
        except ValueError:
            pass

    detector = RegressionDetector()
    trend_data = detector.trend(n)

    if not trend_data:
        print("  No benchmark data. Run /benchmark first.")
        print()
        return

    format_trend(trend_data)


def _do_workspace(arg: str, state: dict, url: str) -> None:
    """Workspace management from chat."""
    import os
    from code_agents.knowledge.workspace import WorkspaceManager

    cwd = state.get("repo_path", os.getenv("TARGET_REPO_PATH", os.getcwd()))
    wm = WorkspaceManager(cwd)
    parts = arg.strip().split() if arg.strip() else []
    subcmd = parts[0] if parts else "list"

    if subcmd == "add" and len(parts) > 1:
        try:
            info = wm.add_repo(parts[1])
            print(f"  Added: {info.name} ({info.language}) — {info.path}")
        except ValueError as e:
            print(f"  Error: {e}")

    elif subcmd == "remove" and len(parts) > 1:
        try:
            if wm.remove_repo(parts[1]):
                print(f"  Removed: {parts[1]}")
            else:
                print(f"  Not found: {parts[1]}")
        except ValueError as e:
            print(f"  Error: {e}")

    elif subcmd == "status":
        status = wm.status()
        print(f"\n  Workspace: {status['repo_count']} repos")
        for r in status["repos"]:
            clean = "clean" if r["clean"] else "dirty"
            print(f"    {r['name']:<20} {r['branch']:<15} [{clean}]")
        print()

    else:
        repos = wm.list_repos()
        if not repos:
            print("  Empty workspace. Use /workspace add <path>")
            return
        print("\n  Workspace Repos:")
        for r in repos:
            print(f"    {r.name:<20} [{r.language}]  {r.path}")
        print()


def _do_workspace_cross_deps(arg: str, state: dict) -> None:
    """Find and display cross-repo dependencies."""
    import os
    from code_agents.knowledge.workspace import WorkspaceManager

    cwd = state.get("repo_path", os.getenv("TARGET_REPO_PATH", os.getcwd()))
    wm = WorkspaceManager(cwd)
    repos = wm.list_repos()

    if len(repos) < 2:
        print("  Need at least 2 repos in workspace. Use /workspace add <path>")
        return

    from code_agents.knowledge.workspace_graph import WorkspaceGraph

    repo_paths = [r.path for r in repos]
    wg = WorkspaceGraph(repo_paths)
    print("  Building cross-repo knowledge graphs...")
    wg.build_all()
    deps = wg.find_cross_repo_deps()

    if not deps:
        print("  No cross-repo dependencies found.")
        return

    print(f"\n  Cross-Repo Dependencies ({len(deps)}):")
    for d in deps:
        src_name = os.path.basename(d.source_repo)
        tgt_name = os.path.basename(d.target_repo)
        print(f"    {src_name}/{d.source_file} -> {tgt_name} (import: {d.import_path})")
    print()


def _do_workspace_pr(arg: str, state: dict) -> None:
    """Create coordinated PRs across workspace repos."""
    import os
    from code_agents.knowledge.workspace import WorkspaceManager

    cwd = state.get("repo_path", os.getenv("TARGET_REPO_PATH", os.getcwd()))
    wm = WorkspaceManager(cwd)
    repos = wm.list_repos()

    if len(repos) < 2:
        print("  Need at least 2 repos in workspace. Use /workspace add <path>")
        return

    parts = arg.strip().split() if arg.strip() else []
    if not parts:
        print("  Usage: /workspace-pr <branch-name> [title]")
        print("  Example: /workspace-pr feature/update-deps \"Update shared deps\"")
        return

    branch_name = parts[0]
    title = " ".join(parts[1:]) if len(parts) > 1 else f"Coordinated change: {branch_name}"

    from code_agents.knowledge.workspace_pr import CoordinatedPRCreator

    repo_paths = [r.path for r in repos]
    creator = CoordinatedPRCreator(repo_paths)
    print(f"  Creating linked PRs on branch '{branch_name}'...")
    results = creator.create_linked_prs(branch_name, title, f"Coordinated PR: {title}")

    if not results:
        print("  No repos had uncommitted changes.")
        return

    for r in results:
        status = "OK" if r.success else "FAIL"
        repo_name = os.path.basename(r.repo)
        if r.success and r.pr_url:
            print(f"    [{status}] {repo_name}: {r.pr_url}")
        elif r.success:
            print(f"    [{status}] {repo_name}: prepared on branch {r.branch}")
        else:
            print(f"    [{status}] {repo_name}: {r.error}")
    print()


def _do_pipeline(arg: str, state: dict, url: str) -> None:
    """Pipeline management from chat."""
    import asyncio
    import os
    from code_agents.devops.pipeline import PipelineLoader, PipelineExecutor, BUILTIN_PIPELINES

    cwd = state.get("repo_path", os.getenv("TARGET_REPO_PATH", os.getcwd()))
    loader = PipelineLoader(cwd)
    parts = arg.strip().split() if arg.strip() else []
    subcmd = parts[0] if parts else "list"

    if subcmd == "list":
        pipelines = loader.list_pipelines()
        if not pipelines:
            print("  No pipelines. Templates: " + ", ".join(t["name"] for t in BUILTIN_PIPELINES))
            print("  Create: /pipeline create --template <name>")
            return
        print("\n  Pipelines:")
        for p in pipelines:
            steps = " -> ".join(s.agent for s in p.steps)
            print(f"    {p.name:<25} {steps}")
        print()

    elif subcmd == "run" and len(parts) > 1:
        name = parts[1]
        pipeline = loader.get_pipeline(name)
        if not pipeline:
            print(f"  Pipeline not found: {name}")
            return

        executor = PipelineExecutor(url)
        print(f"\n  Running pipeline: {pipeline.name} ({len(pipeline.steps)} steps)\n")

        def progress(step_num, total, result):
            print(f"  [{step_num}/{total}] {result.step_name:<20} {result.agent:<15} {result.status}  ({result.latency_ms}ms)")

        run = asyncio.run(executor.run(pipeline, progress_callback=progress))
        print()
        PipelineExecutor.print_run(run)

    elif subcmd == "templates":
        print("\n  Built-in Templates:")
        for t in BUILTIN_PIPELINES:
            print(f"    {t['name']:<25} {t['description']}")
        print("  Install: /pipeline create --template <name>")
        print()

    else:
        print("  Usage: /pipeline [list|run <name>|templates|create]")


def _do_share(arg: str, state: dict, url: str) -> None:
    """Sharing from chat."""
    import os

    parts = arg.strip().split() if arg.strip() else []
    subcmd = parts[0] if parts else "start"

    if subcmd == "stop":
        code = state.get("collab_code")
        if code:
            from code_agents.domain.collaboration import CollabStore
            CollabStore.end_session(code)
            state.pop("collab_code", None)
            print("  Collaboration session ended.")
        else:
            print("  No active collaboration session.")
        return

    if subcmd == "status":
        code = state.get("collab_code")
        if code:
            from code_agents.domain.collaboration import CollabStore
            session = CollabStore.get_session(code)
            if session:
                print(f"  Active session: {code}")
                print(f"  Participants: {len(session.participants)}")
                for p in session.participants:
                    print(f"    {p.name} ({p.role})")
            else:
                print(f"  Session {code} no longer active.")
                state.pop("collab_code", None)
        else:
            print("  No active collaboration session.")
        return

    # Start sharing
    try:
        import httpx
        name = os.getenv("CODE_AGENTS_NICKNAME", os.getenv("USER", "Host"))
        resp = httpx.post(f"{url}/api/collab/create", json={
            "name": name,
            "session_id": state.get("session_id", ""),
            "agent": state.get("agent_name", ""),
            "repo_path": state.get("repo_path", ""),
        }, timeout=10).json()

        code = resp.get("join_code")
        if code:
            state["collab_code"] = code
            print(f"\n  Session shared! Join code: {code}")
            print(f"  Others: code-agents join {code}")
            print(f"  Stop:   /share stop\n")
        else:
            print("  Failed to create shared session.")
    except Exception as e:
        print(f"  Error: {e}")
