"""Tests for the proof video recorder pipeline (offline portions only).

The actual Playwright + Orchestrator polling lives in proof/record_odoo_demo.py
and runs only against a live job. Here we cover:

  * ffmpeg binary discovery via imageio-ffmpeg
  * HTML frame template rendering for the orchestrator dashboard
  * frame-list → MP4 encoding (with synthetic PNG frames)
  * stitch_side_by_side composition
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.proof.video_recorder import (
    JobStateSnapshot,
    _ffmpeg_binary,
    _render_html_frame,
    frames_to_mp4,
    stitch_side_by_side,
)


def _make_red_pngs(directory: Path, count: int) -> list[Path]:
    """Generate ``count`` 320×180 red PNGs via the bundled ffmpeg.

    libx264 requires even pixel dimensions and a minimum size, so the
    earlier 2×2 byte-literal trick fails. Using ffmpeg's lavfi color
    source guarantees a valid frame.
    """
    import subprocess

    import imageio_ffmpeg

    directory.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    paths: list[Path] = []
    for i in range(count):
        p = directory / f"frame_{i:04d}.png"
        # Slightly different colour per frame so the encoder doesn't elide them.
        colour = f"#{(i * 40) % 256:02x}3344"
        subprocess.run(
            [
                ffmpeg, "-y", "-f", "lavfi",
                "-i", f"color={colour}:s=320x180:d=1",
                "-frames:v", "1", str(p),
            ],
            capture_output=True,
            check=True,
        )
        paths.append(p)
    return paths


def test_ffmpeg_binary_resolvable() -> None:
    binary = _ffmpeg_binary()
    assert Path(binary).exists()


def test_render_html_frame_includes_state_class() -> None:
    snaps = [
        JobStateSnapshot(timestamp_iso="2026-04-11T13:00:00Z", state="Pending"),
        JobStateSnapshot(timestamp_iso="2026-04-11T13:00:05Z", state="Running"),
        JobStateSnapshot(timestamp_iso="2026-04-11T13:00:30Z", state="Successful", info="done"),
    ]
    html = _render_html_frame(snaps, job_id="job-xyz", current_index=2)
    assert "Successful" in html
    assert "job-xyz" in html
    assert "done" in html
    # Earlier states must appear in the timeline.
    assert "Pending" in html
    assert "Running" in html


def test_render_html_frame_truncates_future_snapshots() -> None:
    snaps = [
        JobStateSnapshot(timestamp_iso="t1", state="Pending"),
        JobStateSnapshot(timestamp_iso="t2", state="Running"),
    ]
    html = _render_html_frame(snaps, job_id="j", current_index=0)
    # The 't2/Running' future snapshot must NOT appear in the timeline section.
    timeline_html = html.split('class="timeline"')[1] if 'class="timeline"' in html else ""
    assert "t1" in timeline_html
    assert "t2" not in timeline_html


def test_frames_to_mp4_produces_valid_file(tmp_path: Path) -> None:
    frames = _make_red_pngs(tmp_path / "frames", count=4)
    out = tmp_path / "out.mp4"
    result = frames_to_mp4(frames, out, fps=2)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0
    # MP4 magic: bytes 4..8 are "ftyp"
    head = out.read_bytes()[:12]
    assert b"ftyp" in head


def test_frames_to_mp4_raises_on_empty_list(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        frames_to_mp4([], tmp_path / "out.mp4")


def test_stitch_side_by_side_produces_mp4(tmp_path: Path) -> None:
    left_frames = _make_red_pngs(tmp_path / "L", count=3)
    right_frames = _make_red_pngs(tmp_path / "R", count=3)
    left_mp4 = frames_to_mp4(left_frames, tmp_path / "left.mp4", fps=2)
    right_mp4 = frames_to_mp4(right_frames, tmp_path / "right.mp4", fps=2)
    stitched = stitch_side_by_side(left_mp4, right_mp4, tmp_path / "stitched.mp4")
    assert stitched.exists()
    assert stitched.stat().st_size > 0
    head = stitched.read_bytes()[:12]
    assert b"ftyp" in head
