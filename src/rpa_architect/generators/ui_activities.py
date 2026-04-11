"""UI automation activity generators for UiPath XAML.

Generates structurally correct XAML for NClick, NTypeInto, NGetText, and other
Modern Design Experience (``ui:`` namespace) UI activities.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target_anchor(selector: str) -> str:
    """Build a ``<ui:Target>`` block wrapping a selector string."""
    ref = unique_id()
    return (
        f'<ui:Target WaitForReady="INTERACTIVE"'
        f' Timeout="3000"'
        f' Selector="{quote_attr(selector)}"'
        f' sap2010:WorkflowViewState.IdRef="Target_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_click(
    selector: str,
    click_type: str = "CLICK_SINGLE",
    mouse_button: str = "BTN_LEFT",
    display_name: str = "Click",
    timeout_ms: int = 30000,
) -> str:
    """Generate ``ui:NClick`` activity XAML."""
    ref = unique_id()
    target = _target_anchor(selector)
    return (
        f'<ui:NClick ClickType="{quote_attr(click_type)}"'
        f' MouseButton="{quote_attr(mouse_button)}"'
        f' DelayAfter="300"'
        f' DelayBefore="200"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' TimeoutMS="{timeout_ms}"'
        f' sap2010:WorkflowViewState.IdRef="NClick_{ref}">\n'
        f'  <ui:NClick.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NClick.Target>\n'
        f'</ui:NClick>'
    )


def gen_type_into(
    selector: str,
    text: str,
    empty_field: bool = True,
    display_name: str = "Type Into",
    click_before: bool = True,
) -> str:
    """Generate ``ui:NTypeInto`` activity XAML."""
    ref = unique_id()
    target = _target_anchor(selector)
    empty_str = "SingleSpace" if empty_field else "None"
    click_str = "True" if click_before else "False"
    return (
        f'<ui:NTypeInto ClickBeforeTyping="{click_str}"'
        f' EmptyField="{empty_str}"'
        f' Text="{quote_attr(text)}"'
        f' DelayAfter="200"'
        f' DelayBefore="200"'
        f' DelayBetweenKeys="10"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="NTypeInto_{ref}">\n'
        f'  <ui:NTypeInto.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NTypeInto.Target>\n'
        f'</ui:NTypeInto>'
    )


def gen_get_text(
    selector: str,
    output_variable: str,
    display_name: str = "Get Text",
) -> str:
    """Generate ``ui:NGetText`` activity XAML."""
    ref = unique_id()
    target = _target_anchor(selector)
    return (
        f'<ui:NGetText DisplayName="{quote_attr(display_name)}"'
        f' Value="[{quote_attr(output_variable)}]"'
        f' sap2010:WorkflowViewState.IdRef="NGetText_{ref}">\n'
        f'  <ui:NGetText.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NGetText.Target>\n'
        f'</ui:NGetText>'
    )


def gen_select_item(
    selector: str,
    item: str,
    display_name: str = "Select Item",
) -> str:
    """Generate ``ui:NSelectItem`` activity XAML."""
    ref = unique_id()
    target = _target_anchor(selector)
    return (
        f'<ui:NSelectItem Item="{quote_attr(item)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="NSelectItem_{ref}">\n'
        f'  <ui:NSelectItem.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NSelectItem.Target>\n'
        f'</ui:NSelectItem>'
    )


def gen_check(
    selector: str,
    action: str = "Check",
    display_name: str = "Check",
) -> str:
    """Generate ``ui:NCheck`` activity XAML."""
    ref = unique_id()
    target = _target_anchor(selector)
    return (
        f'<ui:NCheck Action="{quote_attr(action)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="NCheck_{ref}">\n'
        f'  <ui:NCheck.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NCheck.Target>\n'
        f'</ui:NCheck>'
    )


def gen_hover(
    selector: str,
    display_name: str = "Hover",
) -> str:
    """Generate ``ui:NHover`` activity XAML."""
    ref = unique_id()
    target = _target_anchor(selector)
    return (
        f'<ui:NHover DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="NHover_{ref}">\n'
        f'  <ui:NHover.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NHover.Target>\n'
        f'</ui:NHover>'
    )


def gen_double_click(
    selector: str,
    display_name: str = "Double Click",
) -> str:
    """Generate ``ui:NClick`` with ``CLICK_DOUBLE`` type XAML."""
    return gen_click(
        selector=selector,
        click_type="CLICK_DOUBLE",
        mouse_button="BTN_LEFT",
        display_name=display_name,
    )


def gen_right_click(
    selector: str,
    display_name: str = "Right Click",
) -> str:
    """Generate ``ui:NClick`` with ``BTN_RIGHT`` button XAML."""
    return gen_click(
        selector=selector,
        click_type="CLICK_SINGLE",
        mouse_button="BTN_RIGHT",
        display_name=display_name,
    )


def gen_keyboard_shortcuts(
    key: str,
    modifiers: str = "None",
    display_name: str = "Keyboard Shortcuts",
) -> str:
    """Generate ``ui:NKeyboardShortcuts`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:NKeyboardShortcuts DisplayName="{quote_attr(display_name)}"'
        f' Key="{quote_attr(key)}"'
        f' Modifiers="{quote_attr(modifiers)}"'
        f' sap2010:WorkflowViewState.IdRef="NKeyboardShortcuts_{ref}" />'
    )


def gen_mouse_scroll(
    selector: str,
    direction: str = "Down",
    clicks: int = 3,
    display_name: str = "Mouse Scroll",
) -> str:
    """Generate ``ui:NMouseScroll`` activity XAML."""
    ref = unique_id()
    target = _target_anchor(selector)
    return (
        f'<ui:NMouseScroll Direction="{quote_attr(direction)}"'
        f' ScrollClicks="{clicks}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="NMouseScroll_{ref}">\n'
        f'  <ui:NMouseScroll.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NMouseScroll.Target>\n'
        f'</ui:NMouseScroll>'
    )


def gen_check_state(
    selector: str,
    output_variable: str,
    display_name: str = "Check State",
) -> str:
    """Generate ``ui:NCheckState`` activity XAML (gets checkbox/toggle state)."""
    ref = unique_id()
    target = _target_anchor(selector)
    return (
        f'<ui:NCheckState DisplayName="{quote_attr(display_name)}"'
        f' Value="[{quote_attr(output_variable)}]"'
        f' sap2010:WorkflowViewState.IdRef="NCheckState_{ref}">\n'
        f'  <ui:NCheckState.Target>\n'
        f'{indent(target, 2)}\n'
        f'  </ui:NCheckState.Target>\n'
        f'</ui:NCheckState>'
    )


def gen_wait_screen_ready(
    display_name: str = "Wait Screen Ready",
    timeout_ms: int = 30000,
) -> str:
    """Generate ``ui:WaitScreenReady`` activity XAML (new in UIAutomation 25.10)."""
    ref = unique_id()
    return (
        f'<ui:WaitScreenReady DisplayName="{quote_attr(display_name)}"'
        f' TimeoutMS="{timeout_ms}"'
        f' sap2010:WorkflowViewState.IdRef="WaitScreenReady_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("click", gen_click, "Click", "UI Automation",
                   "Single, double, or custom click on a UI element")
register_generator("type_into", gen_type_into, "Type Into", "UI Automation",
                   "Type text into a UI element")
register_generator("get_text", gen_get_text, "Get Text", "UI Automation",
                   "Extract text from a UI element")
register_generator("select_item", gen_select_item, "Select Item", "UI Automation",
                   "Select an item from a dropdown or list")
register_generator("check", gen_check, "Check", "UI Automation",
                   "Check or uncheck a checkbox/toggle")
register_generator("hover", gen_hover, "Hover", "UI Automation",
                   "Hover over a UI element")
register_generator("double_click", gen_double_click, "Double Click", "UI Automation",
                   "Double-click on a UI element")
register_generator("right_click", gen_right_click, "Right Click", "UI Automation",
                   "Right-click on a UI element")
register_generator("keyboard_shortcuts", gen_keyboard_shortcuts, "Keyboard Shortcuts",
                   "UI Automation", "Send keyboard shortcuts")
register_generator("mouse_scroll", gen_mouse_scroll, "Mouse Scroll", "UI Automation",
                   "Scroll the mouse wheel on a UI element")
register_generator("check_state", gen_check_state, "Check State", "UI Automation",
                   "Get the checked/unchecked state of a UI element")
register_generator("wait_screen_ready", gen_wait_screen_ready, "Wait Screen Ready",
                   "UI Automation", "Wait until the screen keyboard is available (new in 25.10)")
