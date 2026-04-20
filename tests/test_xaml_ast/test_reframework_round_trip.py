"""Round-trip fidelity against the real REFramework template.

Renders templates/Main.xaml.j2 with the same Jinja variables the repo's
generators pass, then asserts the parsed → re-serialized output still parses,
still contains the original state machine structure, and that every selector
(even the zero selectors in Main.xaml) is enumerable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from rpa_architect.xaml_ast import (
    extract_selectors,
    patch_selector,
    read_xaml,
    write_xaml,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"


@pytest.fixture(scope="module")
def rendered_main() -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False)
    return env.get_template("Main.xaml.j2").render(
        project_name="RoundTripTest", max_retries=3
    )


def test_main_xaml_parses(rendered_main: str) -> None:
    doc = read_xaml(rendered_main)
    assert doc.root.activity_type == "Activity"


def test_main_xaml_preserves_state_machine_on_round_trip(rendered_main: str) -> None:
    doc = read_xaml(rendered_main)
    out = write_xaml(doc, pretty=False)
    # Key REFramework markers survive
    assert "StateMachine" in out
    assert "State_GetTransactionData" in out
    assert "State_ProcessTransaction" in out
    assert "State_EndProcess" in out


def test_main_xaml_round_trip_reparses(rendered_main: str) -> None:
    doc = read_xaml(rendered_main)
    out = write_xaml(doc, pretty=False)
    doc2 = read_xaml(out)
    assert doc2.root.activity_type == "Activity"


def test_main_xaml_has_no_selectors(rendered_main: str) -> None:
    """Main.xaml is a state machine scaffold — no Click/TypeInto with selectors."""
    doc = read_xaml(rendered_main)
    assert extract_selectors(doc) == []


def test_patch_on_synthetic_ui_target_works() -> None:
    xaml = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence>
    <ui:Click DisplayName="Login">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='old' /&gt;" />
      </ui:Click.Target>
    </ui:Click>
  </Sequence>
</Activity>
"""
    doc = read_xaml(xaml)
    selectors = extract_selectors(doc)
    assert len(selectors) == 1
    patch_selector(doc, selectors[0].activity_xpath, "<webctrl id='new' />")
    out = write_xaml(doc)
    assert "id='new'" in out
    assert "id='old'" not in out


def test_xxe_entity_reference_is_not_expanded() -> None:
    """Entities must not be expanded even if declared."""
    malicious = """<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe "PWNED">]>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities">
  <Sequence>
    <LogMessage Message="&xxe;" />
  </Sequence>
</Activity>
"""
    doc = read_xaml(malicious)
    # LogMessage.Message must NOT contain "PWNED" — entity should remain literal
    # or the parser should reject the document. Either is acceptable.
    out = write_xaml(doc, pretty=False)
    assert "PWNED" not in out
