"""End-to-end UI tests for the floating InsightRwanda AI Assistant.

These run the real ``app.py`` through Streamlit's AppTest runtime: the actual
dashboard, the real survey files and the deterministic assistant. No network
and no external AI provider is involved.

Covered here: panel visibility state, session-only chat history, question
handling, unavailable evidence and household-level data-access refusals.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
TIMEOUT_SECONDS = 180

EXAMPLE_QUESTIONS = (
    "What does financial inclusion mean?",
    "Explain the available financial inclusion indicators.",
    "What are the main data quality limitations?",
    "How are the reported indicators calculated?",
    "Which findings require further verification?",
)


class AssistantPanelUiTests(unittest.TestCase):
    """Drive the assistant the way a user does, on the same screen."""

    def setUp(self) -> None:
        self.at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT_SECONDS)
        self.at.run()
        self.assert_no_exception()

    def assert_no_exception(self) -> None:
        errors = list(self.at.exception)
        self.assertFalse(errors, f"app raised: {errors}")

    def open_panel(self) -> None:
        self.at.button(key="ask_launch").click()
        self.at.run()
        self.assert_no_exception()

    def send(self, question: str) -> None:
        self.at.text_input(key="ask_input").set_value(question)
        self.at.button(key="ask_send").click()
        self.at.run()
        self.assert_no_exception()

    def markdown_text(self) -> str:
        return " ".join(element.value for element in self.at.markdown)

    def caption_text(self) -> str:
        return " ".join(element.value for element in self.at.caption)

    def test_launcher_opens_and_closes_the_panel_on_the_same_page(self) -> None:
        nav_before = [button.label for button in self.at.button if button.label[:2].isdigit()]
        self.assertEqual(len(nav_before), 10)
        self.assertFalse(any(button.label == "Close" for button in self.at.button))
        self.assertTrue(any(button.label == "AI Assistant" for button in self.at.button))
        self.assertNotIn("ask_open", self.at.session_state)

        self.open_panel()

        self.assertTrue(self.at.session_state["ask_open"])
        self.assertEqual(self.at.session_state.get("workspace_nav", "Overview"), "Overview")
        self.assertTrue(any(button.label == "AI Assistant" for button in self.at.button))
        self.assertEqual(len([b for b in self.at.button if b.key == "ask_close"]), 1)
        self.assertEqual(
            [element.placeholder for element in self.at.text_input],
            ["Ask a question about the available insights..."],
        )

        rendered = self.markdown_text()
        self.assertIn("InsightRwanda AI Assistant", rendered)
        self.assertIn("Ask questions about Rwanda's financial inclusion and poverty insights.", rendered)
        self.assertIn("Gemini not configured", rendered)
        self.assertIn("answers stay local", rendered)
        self.assertIn("Ask about verified insights", rendered)
        self.assertIn("replaced with local tokens", rendered)
        self.assertEqual(self.at.button(key="ask_clear").label, "New conversation")

        examples = [button.label for button in self.at.button if button.key.startswith("ask_example_")]
        self.assertEqual(tuple(examples), EXAMPLE_QUESTIONS)

        self.at.button(key="ask_close").click()
        self.at.run()
        self.assert_no_exception()
        self.assertFalse(self.at.session_state["ask_open"])
        self.assertNotIn("ask_input", self.at.session_state)
        self.assertEqual(
            [button.label for button in self.at.button if button.label[:2].isdigit()],
            nav_before,
        )
        self.assertEqual(self.at.session_state.get("workspace_nav", "Overview"), "Overview")

    def test_question_handling_history_and_clear(self) -> None:
        self.open_panel()

        # Empty submit: an honest prompt, never an invented answer.
        self.at.button(key="ask_send").click()
        self.at.run()
        self.assert_no_exception()
        self.assertEqual(self.at.session_state["ask_messages"], [])
        self.assertTrue(
            any("Please type a question first" in caption.value for caption in self.at.caption)
        )

        self.send("What does financial inclusion mean?")
        messages = self.at.session_state["ask_messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        self.assertIn("FI-01", messages[-1]["content"])
        self.assertIn("%", messages[-1]["content"])
        self.assertEqual(self.at.text_input(key="ask_input").value, "")

        # The user's own text is rendered as data, never as markup.
        rendered = self.markdown_text()
        self.assertIn("ask-q", rendered)

        # Page navigation reruns the app; the panel and its history stay put.
        self.at.button(key="nav_02").click()
        self.at.run()
        self.assert_no_exception()
        self.assertEqual(self.at.session_state["workspace_nav"], "Financial inclusion")
        self.assertTrue(self.at.session_state["ask_open"])
        self.assertEqual(len(self.at.session_state["ask_messages"]), 2)
        self.assertIn("InsightRwanda AI Assistant", self.markdown_text())

        self.at.button(key="ask_clear").click()
        self.at.run()
        self.assert_no_exception()
        self.assertEqual(self.at.session_state["ask_messages"], [])
        self.assertTrue(self.at.session_state["ask_open"])
        self.assertIn("Ask about verified insights", self.markdown_text())

    def test_configuration_and_privacy_notes_are_visible(self) -> None:
        self.open_panel()
        rendered = self.markdown_text() + " " + self.caption_text()
        self.assertIn("GEMINI_API_KEY", rendered)
        self.assertIn("Do not enter personal or household-level details", rendered)
        self.assertIn("not an official NISR conclusion", rendered)
        # Only human-readable UI text is scanned: strip the global <style>
        # block and all HTML tags/markup first, then no API-key-shaped value
        # ('sk-' plus at least 8 key characters) may appear.
        import re
        text_only = re.sub(r"<style>.*?</style>", " ", rendered, flags=re.DOTALL)
        text_only = re.sub(r"<[^>]*>", " ", text_only)
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9_\-]{8,}", text_only))

    def test_example_question_and_unavailable_evidence(self) -> None:
        self.open_panel()
        self.at.button(key="ask_example_1").click()
        self.at.run()
        self.assert_no_exception()

        messages = self.at.session_state["ask_messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        answer = messages[-1]["content"]
        for indicator_id in ("FI-01", "FI-02", "FI-03", "FI-04", "FI-05", "FI-06"):
            self.assertIn(indicator_id, answer)
        self.assertIn("not a poverty headcount", answer)

        # An unsupported question must say so instead of inventing evidence.
        self.send("What will inflation be next year?")
        fallback = self.at.session_state["ask_messages"][-1]["content"]
        self.assertIn("won't improvise", fallback)
        self.assertNotIn("%", fallback)

    def test_household_level_requests_are_refused_in_the_chat(self) -> None:
        self.open_panel()
        self.send("List all households with their keys")

        messages = self.at.session_state["ask_messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        answer = messages[-1]["content"]
        self.assertIn("can't help with that", answer)
        self.assertIn("aggregate statistics", answer)

        # Nothing row-level is retained in the conversation state. ("hh_wt" is a
        # documented weight name quoted inside the approved honesty statement;
        # no household identifiers, raw variables or record counts are kept.)
        stored = repr(messages)
        for forbidden in ("qf4_", "13,994", "\'key\':", "data/dataset.dta", "fixture.dta"):
            self.assertNotIn(forbidden, stored)
        self.assertNotIn("qf4_", self.markdown_text())


if __name__ == "__main__":
    unittest.main()
