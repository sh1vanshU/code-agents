#!/usr/bin/env python3
"""
Demo: prompt_toolkit fixed input at bottom — test before integrating.

Run: poetry run python demo_tui.py
"""
import time
import threading
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.patch_stdout import patch_stdout


def main():
    print("\n  ╔═ DEMO — prompt_toolkit Fixed Input ═══════════════╗")
    print("  ║  Output scrolls above. Input stays at bottom.      ║")
    print("  ║  Type anything. Spinner won't clobber your input.  ║")
    print("  ║  Type 'run' to simulate a long command.            ║")
    print("  ║  Type 'quit' to exit.                              ║")
    print("  ╚════════════════════════════════════════════════════╝\n")

    # Slash commands for autocomplete
    commands = ["/help", "/quit", "/agents", "/model", "/bash", "/superpower",
                "/plan", "/stats", "/export", "/endpoints", "/voice"]

    style = Style.from_dict({
        "separator": "#666666",
        "user": "#00ff00 bold",
        "agent": "#00bcd4",
        "prompt": "#ffffff bold",
    })

    history_file = str(Path.home() / ".code-agents" / "demo_history")
    session = PromptSession(
        history=FileHistory(history_file),
        auto_suggest=AutoSuggestFromHistory(),
        completer=WordCompleter(commands, ignore_case=True),
        enable_history_search=True,
    )

    while True:
        try:
            # This is the key: patch_stdout() ensures print() goes above the input
            with patch_stdout():
                prompt_msg = [
                    ("class:separator", "─── "),
                    ("class:user", " shivanshu (Lead) "),
                    ("class:separator", " ─── "),
                    ("class:agent", " → auto-pilot "),
                    ("class:separator", " ──────────────────────"),
                    ("", "\n"),
                    ("class:prompt", "❯ "),
                ]
                user_input = session.prompt(prompt_msg, style=style)
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input == "quit":
            print("  Goodbye!")
            break

        if user_input == "run":
            # Simulate a long-running command with timer
            # patch_stdout ensures this output goes ABOVE the input prompt
            print("\n  ┌──────────────────────────────────┐")
            print("  │ $ mvn clean install -DskipTests   │")
            print("  ├──────────────────────────────────┤")

            done = threading.Event()
            def _timer():
                i = 0
                while not done.is_set():
                    i += 1
                    # This print goes ABOVE the input — doesn't clobber!
                    print(f"\r  ├── ⏱ Running... {i}s ──┤", end="", flush=True)
                    done.wait(1)
                print(f"\r  ├──────────────────────────────────┤")

            t = threading.Thread(target=_timer, daemon=True)
            t.start()
            time.sleep(5)  # simulate 5 second command
            done.set()
            t.join()

            print("  │ BUILD SUCCESS                     │")
            print("  │ ✓ Done (5.0s)                     │")
            print("  └──────────────────────────────────┘\n")
            continue

        # Simulate agent response
        print(f"\n  ╔═ AUTO-PILOT ═══════════════════════════════╗")
        print(f"  ║")

        # Simulate streaming with spinner that doesn't clobber input
        response = f"    Processing your request: '{user_input}'..."
        for word in response.split():
            print(word, end=" ", flush=True)
            time.sleep(0.1)

        print(f"\n  ╚══════════════════════════════════════════════╝\n")


if __name__ == "__main__":
    main()
