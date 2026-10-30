from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

import research.assistant_llm as assistant_llm

APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
TIMEOUT_SECONDS = 180


class AssistantPanelUiTests(unittest.TestCase):
    """Drive the assistant the way a user does, on the same screen."""

    def setUp(self) -> None:
        # UI tests stay fully local: never read a developer's Groq key or make
        # a network call. The general-knowledge path itself is covered with
        # stub providers in tests/test_assistant_llm.py.
        provider_patch = mock.patch.object(
            assistant_llm, "get_configured_provider", return_value=None
        )
        provider_patch.start()
        self.addCleanup(provider_patch.stop)
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
        self.assertEqual(len(nav_before), 9)
        self.assertFalse(any(button.label == "Close" for button in self.at.button))
        self.assertTrue(any(button.label == "Insight Assistant" for button in self.at.button))
        self.assertNotIn("ask_open", self.at.session_state)

        self.open_panel()

        self.assertTrue(self.at.session_state["ask_open"])
        self.assertEqual(self.at.session_state.get("workspace_nav", "Overview"), "Overview")
        self.assertTrue(any(button.label == "Insight Assistant" for button in self.at.button))
        self.assertEqual(len([b for b in self.at.button if b.key == "ask_close"]), 1)
        self.assertEqual(
            [element.placeholder for element in self.at.text_input],
            ["Ask about the project — or anything else..."],
        )

        rendered = self.markdown_text()
        self.assertIn("InsightRwanda Assistant", rendered)
        self.assertIn("Ask about Rwanda's financial inclusion and poverty insights", rendered)
        self.assertIn("answers stay local", rendered)
        self.assertIn("Ask anything", rendered)
        self.assertIn("Any other question is answered from general knowledge", rendered)
        self.assertEqual(
            [button.key for button in self.at.button if button.key.startswith("ask_example_")],
            [],
        )
        self.assertEqual(self.at.button(key="ask_clear").label, "New conversation")

        examples = [button.label for button in self.at.button if button.key.startswith("ask_example_")]
        self.assertEqual(tuple(examples), ())

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
        self.assertIn("InsightRwanda Assistant", self.markdown_text())

        self.at.button(key="ask_clear").click()
        self.at.run()
        self.assert_no_exception()
        self.assertEqual(self.at.session_state["ask_messages"], [])
        self.assertTrue(self.at.session_state["ask_open"])
        self.assertIn("Ask anything", self.markdown_text())

    def test_configuration_and_privacy_notes_are_visible(self) -> None:
        self.open_panel()
        rendered = self.markdown_text() + " " + self.caption_text()
        # End-user language only: no developer setup words in the visible panel.
        self.assertIn("General AI answers are not enabled for this panel", rendered)
        self.assertIn("Do not enter personal or household-level details", rendered)
        self.assertNotIn("not an official NISR conclusion", rendered)
        for developer_word in ("API key", "administrator", "secrets or the environment"):
            self.assertNotIn(developer_word, rendered)

    def test_typed_question_and_unavailable_evidence(self) -> None:
        self.open_panel()
        self.send("Explain the available financial inclusion indicators.")
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

    def test_chart_request_returns_a_verified_chart_and_numbers(self) -> None:
        self.open_panel()
        self.send("Show FI-04 by province as a bar chart")

        messages = self.at.session_state["ask_messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        last = messages[-1]
        chart = last.get("chart")
        self.assertIsNotNone(chart)
        self.assertEqual(chart.indicator_id, "FI-04")
        self.assertEqual(chart.group_label, "province")
        self.assertTrue(chart.rows)
        self.assertEqual(len(chart.rows), len(chart.counts))
        # The bubble (chart figure, numbers table, captions) renders cleanly.
        self.assert_no_exception()

    def test_fallback_questions_stay_entirely_local(self) -> None:
        self.open_panel()
        self.send("What will inflation be next year?")

        messages = self.at.session_state["ask_messages"]
        self.assertEqual([message["role"] for message in messages][-1:], ["assistant"])
        last = messages[-1]
        self.assertNotIn("general", last)
        self.assertNotIn("general_attempt", last)
        self.assertNotIn("ai_status", last)

if __name__ == "__main__":
    unittest.main()
