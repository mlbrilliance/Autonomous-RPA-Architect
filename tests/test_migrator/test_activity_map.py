"""activity_map: UIAction → Playwright Python call."""

from __future__ import annotations

import pytest

from rpa_architect.ir.schema import UIAction
from rpa_architect.migrator.activity_map import UnsupportedActionError, emit_call


class TestEmitCall:
    def test_click(self) -> None:
        action = UIAction(action="click", target="Submit", selector_hint="<webctrl id='submit'/>")
        code = emit_call(action)
        assert code == "await page.locator('#submit').click()"

    def test_type_into(self) -> None:
        action = UIAction(
            action="type_into",
            target="Username",
            value="{{user}}",
            selector_hint="<webctrl name='username'/>",
        )
        code = emit_call(action)
        assert "fill(" in code
        assert "{{user}}" in code

    def test_get_text_assigns_variable(self) -> None:
        action = UIAction(
            action="get_text",
            target="Confirmation Message",
            selector_hint="<webctrl id='confirm'/>",
        )
        code = emit_call(action)
        assert "text_content()" in code
        # generated snippet should be a Python statement assigning to confirmation_message
        assert "confirmation_message" in code

    def test_select_item(self) -> None:
        action = UIAction(
            action="select_item",
            target="Country",
            value="US",
            selector_hint="<webctrl id='country'/>",
        )
        code = emit_call(action)
        assert "select_option" in code

    def test_check(self) -> None:
        action = UIAction(action="check", target="Terms", selector_hint="<webctrl id='terms'/>")
        code = emit_call(action)
        assert "check()" in code

    def test_wait_element(self) -> None:
        action = UIAction(
            action="wait_element", target="Spinner gone", selector_hint="<webctrl id='spinner'/>"
        )
        code = emit_call(action)
        assert "wait_for" in code

    def test_hover(self) -> None:
        action = UIAction(
            action="hover", target="Menu", selector_hint="<webctrl id='menu'/>"
        )
        code = emit_call(action)
        assert "hover()" in code

    def test_unsupported_action_raises(self) -> None:
        action = UIAction(
            action="scroll",  # valid in IR but not in migrator
            target="x",
            selector_hint="<webctrl id='x'/>",
        )
        with pytest.raises(UnsupportedActionError):
            emit_call(action)
