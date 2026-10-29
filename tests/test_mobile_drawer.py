"""End-to-end UI tests for the phone navigation drawer (Menu pill).

These run the real ``app.py`` through Streamlit's AppTest runtime: opening the
Menu pill, injecting the phones-only drawer CSS, closing the drawer from the
rail's own toggle and from a page pick, and keeping the desktop collapse state
untouched. CSS itself is browser work — covered by
``scripts/browser_render_check.py``-style manual checks; this suite verifies the
state machine that drives it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
TIMEOUT_SECONDS = 180
DRAWER_MARK = "z-index:1001"
PILL_KEY = "mobile_menu_open"


class MobileDrawerUiTests(unittest.TestCase):
    """Drive the phone drawer the way a user does, from the Menu pill."""

    def setUp(self) -> None:
        self.at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT_SECONDS)
        self.at.run()
        errors = list(self.at.exception)
        self.assertFalse(errors, f"app raised: {errors}")

    def markdown_text(self) -> str:
        return " ".join(element.value for element in self.at.markdown)

    def open_drawer(self) -> None:
        self.at.button(key=PILL_KEY).click()
        self.at.run()
        errors = list(self.at.exception)
        self.assertFalse(errors, f"app raised: {errors}")

    def drawer_css_injected(self) -> bool:
        return DRAWER_MARK in self.markdown_text()

    def test_pill_exists_next_to_the_header_but_drawer_stays_closed(self) -> None:
        self.assertIn("Menu", [button.label for button in self.at.button])
        self.assertFalse(self.drawer_css_injected())

    def test_pill_opens_the_drawer(self) -> None:
        self.open_drawer()
        self.assertTrue(self.drawer_css_injected())

    def test_rail_toggle_closes_the_drawer_without_collapsing_the_desktop_rail(self) -> None:
        self.open_drawer()
        self.at.button(key="sidebar_collapse").click()  # the rail's own toggle
        self.at.run()
        self.assertFalse(self.drawer_css_injected())
        self.assertFalse(bool(self.at.session_state.get("sidebar_collapsed")),
                         "closing the phone drawer must not collapse the desktop rail")

    def test_picking_a_page_closes_the_drawer(self) -> None:
        self.open_drawer()
        self.at.button(key="nav_03").click()
        self.at.run()
        self.assertFalse(self.drawer_css_injected())
        self.assertEqual(self.at.session_state["workspace_nav"], "Poverty insights")

    def test_clicked_page_is_highlighted_after_one_click(self) -> None:
        self.at.button(key="nav_02").click()
        self.at.run()
        self.assertEqual(self.at.session_state["workspace_nav"], "Financial inclusion")
        self.assertEqual(self.at.button(key="nav_02").proto.type, "primary")
        self.assertEqual(self.at.button(key="nav_01").proto.type, "secondary")

    def test_desktop_collapse_toggle_still_collapses_the_rail(self) -> None:
        self.at.button(key="sidebar_collapse").click()
        self.at.run()
        self.assertTrue(self.at.session_state["sidebar_collapsed"])


if __name__ == "__main__":
    unittest.main()
