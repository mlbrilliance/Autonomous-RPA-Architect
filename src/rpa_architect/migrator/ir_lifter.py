"""Lift a REFramework XAML bundle into a :class:`ProcessIR`.

Deliberately narrow. The migrator only claims to handle the REFramework
dispatcher shape: a ``Main.xaml`` with a ``StateMachine`` containing the
four canonical states (``Init``, ``GetTransactionData``, ``ProcessTransaction``,
``EndProcess``) that invokes a ``Process.xaml`` holding the real UI actions.
Any deviation raises :class:`UnsupportedPatternError` rather than emitting
partial code — silent partial migrations have killed more of these tools
than anything else.

Process.xaml's top-level ``Sequence`` becomes a single :class:`Step`; each
recognized UI activity becomes one :class:`UIAction`.
"""

from __future__ import annotations

from rpa_architect.ir.schema import (
    ProcessIR,
    Step,
    Transaction,
    UIAction,
)
from rpa_architect.xaml_ast import (
    XamlActivity,
    XamlDocument,
    XamlSelector,
    read_xaml,
)


class UnsupportedPatternError(ValueError):
    """Raised when an input XAML bundle doesn't fit the REFramework shape."""


def lift_xaml_bundle(xaml_files: dict[str, str]) -> ProcessIR:
    """Build a :class:`ProcessIR` from an REFramework XAML bundle.

    ``xaml_files`` maps relative path → XAML content, mirroring the shape
    produced by :func:`lifecycle.swarm.failure_bundle.build_package_bytes`.
    """
    if not xaml_files:
        raise UnsupportedPatternError("xaml_files is empty; cannot migrate nothing")

    main = _find(xaml_files, "Main.xaml")
    if main is None:
        raise UnsupportedPatternError(
            "no Main.xaml in bundle; migrator only supports REFramework dispatchers"
        )
    main_doc = read_xaml(main)

    if not _is_reframework(main_doc):
        raise UnsupportedPatternError(
            "Main.xaml is not a REFramework StateMachine (missing one of "
            "Init / GetTransactionData / ProcessTransaction / EndProcess states)"
        )

    process_xaml = _find(xaml_files, "Process.xaml")
    if process_xaml is None:
        raise UnsupportedPatternError(
            "Process.xaml not present in bundle — REFramework dispatcher requires "
            "Process.xaml holding the transaction's UI flow"
        )

    process_doc = read_xaml(process_xaml)
    process_name = _extract_process_name(main_doc)
    actions = list(_walk_ui_actions(process_doc.root))

    transaction = Transaction(
        name=f"Process{process_name}",
        steps=[
            Step(
                id="S001",
                type="ui_flow",
                description=f"Migrated from Process.xaml of {process_name}",
                actions=actions,
            )
        ],
    )
    return ProcessIR(
        process_name=process_name,
        transactions=[transaction],
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_REFRAMEWORK_STATE_NAMES = {
    "State_Init",
    "State_GetTransactionData",
    "State_ProcessTransaction",
    "State_EndProcess",
}


def _find(files: dict[str, str], target: str) -> str | None:
    for path, content in files.items():
        if path == target or path.endswith("/" + target):
            return content
    return None


def _is_reframework(doc: XamlDocument) -> bool:
    """Return True iff the document contains the four REFramework states."""
    found: set[str] = set()
    for node in _walk(doc.root):
        if isinstance(node, XamlActivity) and node.activity_type == "State":
            name = node.properties.get("Name", "")
            if name in _REFRAMEWORK_STATE_NAMES:
                found.add(name)
    return found == _REFRAMEWORK_STATE_NAMES


def _extract_process_name(doc: XamlDocument) -> str:
    """Pull the project display name from the StateMachine DisplayName attribute."""
    for node in _walk(doc.root):
        if isinstance(node, XamlActivity) and node.activity_type == "StateMachine":
            disp = node.properties.get("DisplayName", "")
            # "InvoiceProcessing Main" → "InvoiceProcessing"
            if disp.endswith(" Main"):
                return disp[: -len(" Main")]
            return disp or "MigratedProcess"
    return "MigratedProcess"


def _walk(node):
    yield node
    for child in getattr(node, "children", []):
        yield from _walk(child)


_ACTION_MAP: dict[str, str] = {
    "Click": "click",
    "TypeInto": "type_into",
    "GetText": "get_text",
    "SelectItem": "select_item",
    "Check": "check",
    "Uncheck": "uncheck",
    "Hover": "hover",
    "ExtractData": "extract_data",
    "WaitUiElementAppear": "wait_element",
    "SendHotkey": "keyboard_shortcut",
}


def _walk_ui_actions(root: XamlActivity):
    """Yield one :class:`UIAction` per recognized UI activity in ``root``."""
    for node in _walk(root):
        if not isinstance(node, XamlActivity):
            continue
        action_kind = _ACTION_MAP.get(node.activity_type)
        if action_kind is None:
            continue
        target_display = node.properties.get("DisplayName", node.activity_type)
        value = node.properties.get("Text") or node.properties.get("Value")
        selector = _first_selector(node)
        yield UIAction(
            action=action_kind,
            target=target_display,
            value=value,
            selector_hint=selector.selector_xml if selector else None,
            confidence=0.8,
        )


def _first_selector(activity: XamlActivity) -> XamlSelector | None:
    for child in activity.children:
        if isinstance(child, XamlSelector):
            return child
    return None
