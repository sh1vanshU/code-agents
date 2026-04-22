"""Step-by-step questionnaire widget for the upfront Q&A flow.

Presents questions one at a time with selectable option buttons.
Posts a Completed message with all answers once finished.
"""

import logging

from textual.widgets import Static, Button
from textual.containers import Vertical
from textual.message import Message
from textual import on

logger = logging.getLogger("code_agents.chat.tui.widgets.questionnaire")


class QuestionnaireWidget(Vertical):
    """Multi-step questionnaire shown inline in the chat output area."""

    DEFAULT_CSS = """
    QuestionnaireWidget {
        height: auto;
        margin: 1 0;
        padding: 0 1;
    }

    QuestionnaireWidget .qw-header {
        margin-bottom: 1;
    }

    QuestionnaireWidget .qw-question {
        margin-bottom: 1;
    }

    QuestionnaireWidget .qw-options {
        height: auto;
        padding: 0 1;
    }

    QuestionnaireWidget .qw-options Button {
        margin-bottom: 0;
        width: 100%;
    }
    """

    class Completed(Message):
        """Posted when all questions have been answered."""

        def __init__(self, answers: list[dict]) -> None:
            super().__init__()
            self.answers = answers

    class Cancelled(Message):
        """Posted when the user cancels the questionnaire."""

    def __init__(self, questions: list[dict], **kwargs) -> None:
        """Create a questionnaire.

        Args:
            questions: List of dicts, each with "question" (str) and
                       "options" (list[str]).
        """
        super().__init__(**kwargs)
        self.questions = questions
        self._current_step = 0
        self._answers: list[dict] = []

    def compose(self):
        q = self.questions[0]
        total = len(self.questions)
        yield Static(
            f"[bold]Step 1/{total}[/bold]",
            id="qw-header",
            classes="qw-header",
        )
        yield Static(
            f"[yellow]{q['question']}[/yellow]",
            id="qw-question",
            classes="qw-question",
        )
        with Vertical(id="qw-options", classes="qw-options"):
            for idx, opt in enumerate(q.get("options", [])):
                yield Button(opt, id=f"qopt-{idx}")

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Record the answer and advance to the next step."""
        button_id = event.button.id or ""
        if not button_id.startswith("qopt-"):
            return
        opt_idx = int(button_id.split("-", 1)[1])
        q = self.questions[self._current_step]
        options = q.get("options", [])
        self._answers.append(
            {
                "question": q["question"],
                "answer": options[opt_idx] if opt_idx < len(options) else "",
                "option_idx": opt_idx,
            }
        )
        self._current_step += 1

        if self._current_step >= len(self.questions):
            self.post_message(self.Completed(answers=list(self._answers)))
            self.remove()
        else:
            self._show_step(self._current_step)

    def _show_step(self, idx: int) -> None:
        """Update the widget to display the question at *idx*."""
        q = self.questions[idx]
        total = len(self.questions)

        header = self.query_one("#qw-header", Static)
        header.update(f"[bold]Step {idx + 1}/{total}[/bold]")

        question = self.query_one("#qw-question", Static)
        question.update(f"[yellow]{q['question']}[/yellow]")

        options_container = self.query_one("#qw-options", Vertical)
        options_container.remove_children()
        for opt_idx, opt in enumerate(q.get("options", [])):
            options_container.mount(Button(opt, id=f"qopt-{opt_idx}"))

    def key_escape(self) -> None:
        """Cancel the questionnaire on Escape."""
        self.post_message(self.Cancelled())
        self.remove()
