"""End-to-end UI tests for the floating InsightRwanda AI Assistant.

These run the real ``app.py`` through Streamlit's AppTest runtime: the actual
dashboard, the real survey files and the deterministic assistant. No network
and no external AI provider is involved.

Covered here: panel visibility state, session-only chat history, question
handling, unavailable evidence and household-level data-access refusals.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

import streamlit
from streamlit.testing.v1 import AppTest

APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
TIMEOUT_SECONDS = 180


class _FakeUiProvider:
    """Configuration-shaped stub: never looks up a key, never touches the network."""

    model = "openai/gpt-oss-120b"


class _ProviderStub:
    """Configuration-shaped stub: never reads a key, never touches the network."""

    model = "openai/gpt-oss-120b"


class AssistantPanelUiTests(unittest.TestCase):
    """Drive the assistant the way a user does, on the same screen."""

    def setUp(self) -> None:
        # Hermeticity: a developer machine may hold a real GROQ_API_KEY in
        # .streamlit/secrets.toml or the environment, which AppTest would
        # otherwise use for live network calls. Neutralize both sources for
        # every test; the dedicated configuration test re-adds a fake key via
        # the environment. (AppTest re-executes app.py each run, so patching
        # the research.assistant_llm module — which the script imports fresh
        # every run — is what per-test provider stubs must target.)
        self._secrets_off = mock.patch.object(streamlit, "secrets", {})
        self._secrets_off.start()
        self.addCleanup(self._secrets_off.stop)
        self._env_off = mock.patch.dict(os.environ, {"GROQ_API_KEY": ""})
        self._env_off.start()
        self.addCleanup(self._env_off.stop)
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
        self.assertIn("answers stay local", rendered)
        self.assertIn("Ask about verified insights", rendered)
        self.assertIn("is labelled as such", rendered)
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
        # End-user language only: no developer setup words in the visible panel.
        self.assertIn("AI-polished wording is not enabled", rendered)
        self.assertIn("Do not enter personal or household-level details", rendered)
        self.assertNotIn("not an official NISR conclusion", rendered)
        self.assertNotIn("replaced locally before sending", rendered)
        for developer_word in ("GROQ_API_KEY", "administrator", "secrets or the environment"):
            self.assertNotIn(developer_word, rendered)
        # Only human-readable UI text is scanned: strip the global <style>
        # block and all HTML tags/markup first, then no API-key-shaped value
        # ('sk-' plus at least 8 key characters) may appear.
        import re
        text_only = re.sub(r"<style>.*?</style>", " ", rendered, flags=re.DOTALL)
        text_only = re.sub(r"<[^>]*>", " ", text_only)
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9_\-]{8,}", text_only))

    def test_configured_groq_is_labelled_without_exposing_the_key(self) -> None:
        # A fake key exercises the configuration gate and client setup; no
        # question is sent, so this test never contacts the provider. The real
        # factory is restored for this test only (setUp keeps every other test
        # offline, regardless of a developer machine's real secrets).
        with mock.patch.dict(
            os.environ, {"GROQ_API_KEY": "gsk_FAKE-test-placeholder"}, clear=False
        ):
            at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT_SECONDS)
            at.run()
            self.assertFalse(list(at.exception))
            at.button(key="ask_launch").click()
            at.run()
            self.assertFalse(list(at.exception))
            rendered = " ".join(e.value for e in at.markdown)
            rendered += " " + " ".join(e.value for e in at.caption)
        self.assertIn("AI wording layer active", rendered)
        self.assertNotIn("gsk_FAKE-test-placeholder", rendered)
        self.assertNotIn("openai/gpt-oss-120b", rendered)
        self.assertNotIn("local tokens", rendered)
        self.assertTrue(at.session_state["ask_provider"] is not None)

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
        # Chart messages deliberately skip the AI wording layer.
        self.assertIsNone(last.get("ai_status"))
        # The bubble (chart figure, numbers table, captions) renders cleanly.
        self.assert_no_exception()

    def test_fallback_questions_without_a_provider_stay_entirely_local(self) -> None:
        self.open_panel()
        self.send("What will inflation be next year?")

        messages = self.at.session_state["ask_messages"]
        self.assertEqual([message["role"] for message in messages][-1:], ["assistant"])
        last = messages[-1]
        self.assertNotIn("general", last)
        self.assertNotIn("general_attempt", last)
        self.assertEqual(last.get("ai_status"), "disabled")
        self.assertNotIn("General AI answer", self.markdown_text())

    def test_fallback_question_is_routed_to_a_labelled_general_answer(self) -> None:
        # The deterministic core has no verified evidence for this question, so
        # with a provider it may be answered from labelled general knowledge.
        # The provider itself is stubbed: no network, no key needed.
        with mock.patch.dict(
            os.environ, {"GROQ_API_KEY": "gsk_FAKE-test-placeholder"}, clear=False
        ), \
                mock.patch(
                    "research.assistant_llm.get_configured_provider", return_value=_ProviderStub()
                ), \
                mock.patch(
                    "research.assistant_llm.answer_general_with_status",
                    return_value=("Kigali is the capital of Rwanda.", "general"),
                ):
            self.open_panel()
            self.send("What is the capital city of Rwanda?")

        messages = self.at.session_state["ask_messages"]
        last = messages[-1]
        self.assertEqual(last["role"], "assistant")
        self.assertEqual(last["content"], "Kigali is the capital of Rwanda.")
        self.assertEqual(last["references"], ())
        self.assertFalse(last["numeric"])
        self.assertTrue(last["general"])
        self.assertEqual(last["ai_status"], "general")

        rendered = self.markdown_text()
        self.assertIn("General AI answer", rendered)
        self.assertIn("not</strong> from this survey's verified data", rendered)
        self.assertNotIn("won't improvise", rendered)

    def test_general_mode_provider_failure_falls_back_to_the_offline_answer(self) -> None:
        with mock.patch.dict(
            os.environ, {"GROQ_API_KEY": "gsk_FAKE-test-placeholder"}, clear=False
        ), \
                mock.patch(
                    "research.assistant_llm.get_configured_provider", return_value=_ProviderStub()
                ), \
                mock.patch(
                    "research.assistant_llm.answer_general_with_status",
                    return_value=("", "timeout"),
                ):
            self.open_panel()
            self.send("What is the capital city of Rwanda?")

        messages = self.at.session_state["ask_messages"]
        last = messages[-1]
        self.assertIn("won't improvise", last["content"])
        self.assertFalse(last.get("general"))
        self.assertTrue(last.get("general_attempt"))
        self.assertEqual(last.get("ai_status"), "timeout")

        rendered = self.markdown_text() + " " + self.caption_text()
        self.assertIn("did not respond in time", rendered)
        self.assertIn("offline project answer is shown", rendered)
        self.assertNotIn("General AI answer", rendered)


if __name__ == "__main__":
    unittest.main()
