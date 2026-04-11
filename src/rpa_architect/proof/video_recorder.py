"""Two-strategy video recorder for end-to-end demo proofs.

Strategy 1 — :func:`render_orchestrator_dashboard_frames` polls the
Orchestrator job API and renders an HTML dashboard showing the job state
over time as a sequence of PNG frames, then stitches them into an MP4 with
ffmpeg. This strategy avoids automating the SSO-protected Orchestrator
web UI (which is fragile) while still showing real cloud-side state.

Strategy 2 — :func:`record_playwright_replay` re-runs a recorded list of
UI actions against the target app in a headed Playwright browser with
``record_video_dir`` enabled, producing a webm that ffmpeg converts to
MP4.

Both strategies produce ``.mp4`` files at the requested path. The driver
script ``proof/record_odoo_demo.py`` runs them in parallel and stitches
them side-by-side via ``ffmpeg -filter_complex hstack=inputs=2``.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _ffmpeg_binary() -> str:
    """Locate ffmpeg, preferring the bundled imageio-ffmpeg binary."""
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError:
        path = shutil.which("ffmpeg")
        if path:
            return path
    raise RuntimeError(
        "ffmpeg not found. Install with `pip install imageio-ffmpeg` "
        "or your system package manager."
    )


# ---------------------------------------------------------------------------
# Strategy 1: Orchestrator dashboard renderer
# ---------------------------------------------------------------------------


@dataclass
class JobStateSnapshot:
    """One sampled snapshot of the job's state."""

    timestamp_iso: str
    state: str  # Pending, Running, Successful, Faulted, Stopped
    info: str = ""
    log_count: int = 0


_HTML_FRAME_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, sans-serif; background: #0b1220; color: #e5e7eb; margin: 0; padding: 32px; }}
.title {{ font-size: 28px; font-weight: 600; margin-bottom: 8px; }}
.subtitle {{ color: #94a3b8; margin-bottom: 24px; font-size: 14px; }}
.state {{ font-size: 64px; font-weight: 700; margin: 16px 0; }}
.state.Successful {{ color: #22c55e; }}
.state.Running, .state.Pending {{ color: #38bdf8; }}
.state.Faulted, .state.Stopped {{ color: #ef4444; }}
.timeline {{ margin-top: 32px; border-top: 1px solid #1e293b; padding-top: 16px; }}
.row {{ font-family: monospace; font-size: 13px; margin: 4px 0; color: #cbd5e1; }}
.row.now {{ color: #facc15; font-weight: 600; }}
.label {{ color: #64748b; }}
</style></head>
<body>
  <div class="title">UiPath Orchestrator Job</div>
  <div class="subtitle">{job_id}</div>
  <div class="state {state}">{state}</div>
  <div class="row"><span class="label">info:</span> {info}</div>
  <div class="row"><span class="label">logs collected:</span> {log_count}</div>
  <div class="timeline">{timeline_rows}</div>
</body></html>
"""


def _render_html_frame(
    snapshots: list[JobStateSnapshot],
    job_id: str,
    current_index: int,
) -> str:
    timeline_rows = []
    for i, snap in enumerate(snapshots[: current_index + 1]):
        cls = "row now" if i == current_index else "row"
        timeline_rows.append(
            f'<div class="{cls}">[{snap.timestamp_iso}] {snap.state} {snap.info[:60]}</div>'
        )
    current = snapshots[current_index]
    return _HTML_FRAME_TEMPLATE.format(
        job_id=job_id,
        state=current.state,
        info=current.info[:120] or "&nbsp;",
        log_count=current.log_count,
        timeline_rows="\n  ".join(timeline_rows),
    )


async def render_orchestrator_dashboard_frames(
    snapshots: list[JobStateSnapshot],
    job_id: str,
    output_dir: Path,
) -> list[Path]:
    """Render one PNG frame per snapshot using a headless Playwright browser.

    Returns the list of frame paths in chronological order. Each frame
    shows the job state and a growing timeline.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is required: pip install playwright && playwright install chromium"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        for i, _ in enumerate(snapshots):
            html = _render_html_frame(snapshots, job_id, i)
            await page.set_content(html, wait_until="domcontentloaded")
            out = output_dir / f"frame_{i:04d}.png"
            await page.screenshot(path=str(out), full_page=False)
            frame_paths.append(out)

        await browser.close()

    logger.info("rendered %d dashboard frames in %s", len(frame_paths), output_dir)
    return frame_paths


def frames_to_mp4(frame_paths: list[Path], output_path: Path, fps: int = 2) -> Path:
    """Stitch a sequence of PNG frames into an MP4 via ffmpeg."""
    if not frame_paths:
        raise ValueError("no frames to encode")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_binary()

    # frame paths must share a common parent and a numeric pattern
    parent = frame_paths[0].parent
    pattern = str(parent / "frame_%04d.png")

    cmd = [
        ffmpeg,
        "-y",
        "-framerate", str(fps),
        "-i", pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {proc.returncode}): {proc.stderr[:500]}"
        )
    logger.info("encoded %s (%d bytes)", output_path, output_path.stat().st_size)
    return output_path


async def record_orchestrator_run(
    snapshots: list[JobStateSnapshot],
    job_id: str,
    output_path: Path,
    fps: int = 2,
) -> Path:
    """End-to-end strategy 1: render frames + encode MP4 in one call."""
    frames_dir = output_path.parent / "frames_orchestrator"
    frames = await render_orchestrator_dashboard_frames(
        snapshots, job_id, frames_dir
    )
    return frames_to_mp4(frames, output_path, fps=fps)


# ---------------------------------------------------------------------------
# Strategy 2: Playwright replay recorder
# ---------------------------------------------------------------------------


@dataclass
class ReplayAction:
    """One step the bot performed in the target web UI."""

    kind: str  # 'navigate', 'fill', 'click', 'wait', 'screenshot'
    target: str = ""  # URL for navigate, selector for fill/click
    value: str = ""  # text for fill
    delay_ms: int = 250


@dataclass
class ReplayConfig:
    """Inputs for :func:`record_playwright_replay`."""

    base_url: str
    actions: list[ReplayAction] = field(default_factory=list)
    viewport_width: int = 1280
    viewport_height: int = 720
    headless: bool = True


async def record_playwright_replay(
    config: ReplayConfig,
    output_path: Path,
) -> Path:
    """Re-run the bot's UI actions in Playwright with video recording on.

    Produces a `.webm` then converts it to `.mp4` via ffmpeg. The webm is
    written to ``output_path.parent`` and removed after conversion.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is required") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    video_dir = output_path.parent / "playwright_video"
    video_dir.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=config.headless)
        context = await browser.new_context(
            viewport={"width": config.viewport_width, "height": config.viewport_height},
            record_video_dir=str(video_dir),
            record_video_size={"width": config.viewport_width, "height": config.viewport_height},
        )
        page = await context.new_page()

        for action in config.actions:
            try:
                if action.kind == "navigate":
                    target = action.target if action.target.startswith("http") else f"{config.base_url}{action.target}"
                    await page.goto(target, wait_until="domcontentloaded")
                elif action.kind == "fill":
                    await page.fill(action.target, action.value)
                elif action.kind == "click":
                    await page.click(action.target)
                elif action.kind == "wait":
                    await asyncio.sleep(max(action.delay_ms / 1000, 0.1))
                elif action.kind == "screenshot":
                    await page.screenshot(path=str(output_path.parent / f"shot_{action.target or 'x'}.png"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("replay step failed (%s %s): %s", action.kind, action.target, exc)
            await asyncio.sleep(action.delay_ms / 1000)

        await context.close()
        await browser.close()

    webms = sorted(video_dir.glob("*.webm"))
    if not webms:
        raise RuntimeError("playwright did not produce a video")
    webm = webms[-1]

    ffmpeg = _ffmpeg_binary()
    cmd = [
        ffmpeg,
        "-y",
        "-i", str(webm),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"webm->mp4 conversion failed: {proc.stderr[:500]}")

    webm.unlink(missing_ok=True)
    return output_path


# ---------------------------------------------------------------------------
# Side-by-side stitching
# ---------------------------------------------------------------------------


def stitch_side_by_side(
    left_mp4: Path,
    right_mp4: Path,
    output_path: Path,
) -> Path:
    """Concatenate two MP4s horizontally via ffmpeg's hstack filter."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_binary()
    cmd = [
        ffmpeg,
        "-y",
        "-i", str(left_mp4),
        "-i", str(right_mp4),
        "-filter_complex", "[0:v][1:v]hstack=inputs=2",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"hstack failed: {proc.stderr[:500]}")
    return output_path
