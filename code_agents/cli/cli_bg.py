"""CLI background agent command — list, stop, view background tasks."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_bg")


def cmd_bg():
    """Manage background agent tasks.

    Usage:
      code-agents bg                # list all background tasks
      code-agents bg list           # list all background tasks
      code-agents bg stop <id>      # stop a specific task
      code-agents bg stop-all       # stop all running tasks
      code-agents bg view <id>      # view task result
      code-agents bg clean          # remove completed tasks
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    sub = args[0] if args else "list"

    from code_agents.devops.background_agent import BackgroundAgentManager, render_tasks_panel

    mgr = BackgroundAgentManager.get_instance()

    if sub in ("list", "ls"):
        panel = render_tasks_panel(mgr)
        print(panel)

    elif sub == "stop":
        if len(args) < 2:
            print(yellow("  Usage: code-agents bg stop <task-id>"))
            return
        task_id = args[1]
        ok = mgr.stop_task(task_id)
        if ok:
            print(green(f"  Stopped task {task_id}"))
        else:
            print(yellow(f"  Task {task_id} not found or not running."))

    elif sub == "stop-all":
        count = mgr.stop_all()
        if count:
            print(green(f"  Stopped {count} task(s)."))
        else:
            print(dim("  No running tasks to stop."))

    elif sub == "view":
        if len(args) < 2:
            print(yellow("  Usage: code-agents bg view <task-id>"))
            return
        task_id = args[1]
        task = mgr.get_task(task_id)
        if not task:
            print(yellow(f"  Task {task_id} not found."))
            return
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
            if len(task.result.splitlines()) > 20:
                print(dim(f"    ... ({len(task.result.splitlines()) - 20} more lines)"))
        if task.error:
            print()
            print(red(f"  Error: {task.error}"))
        print()

    elif sub == "clean":
        count = mgr.remove_completed()
        if count:
            print(green(f"  Removed {count} completed task(s)."))
        else:
            print(dim("  No completed tasks to remove."))

    elif sub in ("--help", "-h"):
        print(cmd_bg.__doc__)

    else:
        print(yellow(f"  Unknown subcommand: {sub}"))
        print(dim("  Usage: code-agents bg [list|stop|stop-all|view|clean]"))
