"""Browser QA-loop demo — mirrors the YouTube Playwright-CLI workflow.

End-to-end:

1. Spin up a tiny Flask form on ``localhost:5555``. The form's submit button
   is intentionally slow — JS injects it 5 seconds after page load, so a
   short Playwright wait will time out.
2. Lift a small XAML bundle through the real ``emit_project`` migrator.
3. Patch the emitted ``processes/*.py`` to (a) navigate to the form and
   (b) wait with a deliberately tight ``timeout=1500`` on the slow button.
4. Run :class:`MigratorQALoop` — iteration 1 should time out; the
   :class:`MigratorQAFixer` bumps the timeout; iteration 2 should pass.
5. Print a report and exit non-zero on failure.

This is the executable analog of the video's "build → headed test → find
bugs → fix → retest" loop, applied to this repo's actual subject (UiPath
migration), not a generic form demo. Run::

    python proof/demo_qa_loop.py            # headed (default)
    python proof/demo_qa_loop.py --headless # CI-style
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

from rpa_architect.lifecycle.fault_fixer import FixerRegistry
from rpa_architect.lifecycle.migrator_qa_fixer import MigratorQAFixer
from rpa_architect.lifecycle.migrator_qa_orchestrator import MigratorQALoop
from rpa_architect.lifecycle.qa_loop import QALoopRunner
from rpa_architect.migrator.emitter import _module_name, emit_project
from rpa_architect.migrator.ir_lifter import lift_xaml_bundle

PORT = 5555
URL = f"http://127.0.0.1:{PORT}/"
SLOW_BUTTON_DELAY_S = 4  # JS injects #submit after this many seconds

SAMPLE_MAIN = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <StateMachine DisplayName="QALoopDemo Main">
    <State x:Name="State_Init" DisplayName="Init"/>
    <State x:Name="State_GetTransactionData" DisplayName="Get Transaction Data"/>
    <State x:Name="State_ProcessTransaction" DisplayName="Process Transaction">
      <State.Entry>
        <Sequence>
          <ui:InvokeWorkflowFile FilePath="Process.xaml"/>
        </Sequence>
      </State.Entry>
    </State>
    <State x:Name="State_EndProcess" DisplayName="End Process" IsFinal="True"/>
  </StateMachine>
</Activity>
"""

SAMPLE_PROCESS = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Submit Form">
    <ui:WaitUiElementAppear DisplayName="Wait Submit">
      <ui:WaitUiElementAppear.Target>
        <ui:Target Selector="&lt;webctrl id='submit' /&gt;"/>
      </ui:WaitUiElementAppear.Target>
    </ui:WaitUiElementAppear>
    <ui:Click DisplayName="Click Submit">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='submit' /&gt;"/>
      </ui:Click.Target>
    </ui:Click>
  </Sequence>
</Activity>
"""


def _slow_form_html(delay_s: int) -> str:
    return f"""<!doctype html>
<html><head><title>QA-loop demo</title></head>
<body>
  <h1>Demo form</h1>
  <p>The submit button shows up after {delay_s}s.</p>
  <div id="container"></div>
  <script>
    setTimeout(() => {{
      const b = document.createElement('button');
      b.id = 'submit';
      b.textContent = 'Submit';
      b.onclick = () => document.body.innerHTML = '<h1 id=done>thanks</h1>';
      document.getElementById('container').appendChild(b);
    }}, {delay_s * 1000});
  </script>
</body></html>
"""


def _start_demo_server(delay_s: int) -> threading.Thread:
    """Tiny stdlib HTTP server — no Flask dep, returns the slow-form HTML."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    html = _slow_form_html(delay_s).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — stdlib name
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *_args: object) -> None:
            return  # silence access logs

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect(("127.0.0.1", PORT))
                return thread
            except OSError:
                time.sleep(0.05)
    raise RuntimeError(f"Demo HTTP server never came up on :{PORT}")


def _patch_process_with_navigation_and_short_timeout(
    project_dir: Path, tx_module: str
) -> None:
    """Inject ``page.goto(URL)`` and a tight ``timeout=`` on the wait_for call.

    This is the kind of post-emit edit a developer would normally make: the
    migrator emits behavior-equivalent code, but doesn't know the URL or the
    target's timing characteristics. The QA-loop's job is to spot when a
    too-tight timeout flakes the bot, and bump it.
    """
    py = project_dir / "processes" / f"{tx_module}.py"
    text = py.read_text()
    # Add navigation as the first step inside the function body.
    text = text.replace(
        '    outputs: dict[str, Any] = {}',
        f'    outputs: dict[str, Any] = {{}}\n    await page.goto({URL!r})',
    )
    # Tighten the wait_for timeout so iteration 1 is guaranteed to fail.
    text = text.replace(".wait_for()", ".wait_for(timeout=1500)")
    py.write_text(text)


def banner(msg: str) -> None:
    print(f"\n{'═' * len(msg)}\n{msg}\n{'═' * len(msg)}")


async def main_async(args: argparse.Namespace) -> int:
    banner("DEMO — Browser QA-Loop (build → test → fix → retest)")
    print(f"▸ Starting demo HTTP server on {URL} (submit button delay {SLOW_BUTTON_DELAY_S}s) …")
    _start_demo_server(SLOW_BUTTON_DELAY_S)

    print("▸ Lifting XAML bundle into ProcessIR …")
    ir = lift_xaml_bundle({"Main.xaml": SAMPLE_MAIN, "Process.xaml": SAMPLE_PROCESS})
    tx_module = _module_name(ir.transactions[0].name)
    print(f"  process_name : {ir.process_name}")
    print(f"  tx module    : {tx_module}")

    project_dir = Path(tempfile.mkdtemp(prefix="qa-loop-demo-"))
    print(f"▸ Emitting Python+Playwright project to {project_dir} …")
    emit_project(ir, project_dir)
    _patch_process_with_navigation_and_short_timeout(project_dir, tx_module)
    print("  injected page.goto + tight timeout=1500 on wait_for")

    headless = args.headless
    env = {"RPA_HEADLESS": "1" if headless else "0"}
    runner = QALoopRunner(timeout_seconds=60, env=env)
    registry = FixerRegistry([MigratorQAFixer()])
    loop = MigratorQALoop(runner=runner, registry=registry, max_iterations=3)

    banner(f"RUNNING QA LOOP (max 3 iters, headless={headless})")
    report = await loop.run(project_dir)

    print()
    for i, outcome in enumerate(report.fix_outcomes, start=1):
        bumps = outcome.evidence.get("bumps", [])
        print(f"  iter {i} fix: {outcome.fixer} → bumps={bumps} success={outcome.success}")
    print(f"\n{report.summary()}")

    if not report.passed:
        banner("FAILED — see stderr below")
        print(report.last_run.stderr[-1500:])
    else:
        banner("PASSED — QA loop closed itself without human intervention")

    if not args.keep:
        shutil.rmtree(project_dir, ignore_errors=True)
    else:
        print(f"\n(kept project at {project_dir})")

    return 0 if report.passed else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--headless", action="store_true", help="Run Playwright headless (CI-style).")
    p.add_argument("--keep", action="store_true", help="Keep generated project dir for inspection.")
    args = p.parse_args()
    # Ensure the migrated project's subprocess sees the same PYTHONPATH so
    # rpa_architect imports keep working — the project itself does NOT depend
    # on rpa_architect, but keeping PYTHONPATH stable avoids subprocess surprises.
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
