"""Browser session lifecycle — ephemeral or persistent (logged-in) profile.

Wraps Playwright launch so callers don't pick between ``launch()`` and
``launch_persistent_context()``. Provides a single async context manager that
yields a ``Page`` and a ``BrowserContext``.

Two modes:

* **Ephemeral** (``user_data_dir=None``): fresh Chromium each invocation.
  Session state is lost on close. Today's harvest behavior.
* **Persistent** (``user_data_dir=/some/path``): cookies, localStorage, and
  IndexedDB survive across runs — log in once, automate forever.

Defaults are headed (``headless=False``) to match interactive development. The
``RPA_HEADLESS`` env var (``1`` / ``true`` / ``yes``) flips to headless without
code changes; ``RPA_USER_DATA_DIR`` enables persistence the same way.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def _env_headless(default: bool) -> bool:
    raw = os.environ.get("RPA_HEADLESS")
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _env_user_data_dir(default: Path | None) -> Path | None:
    raw = os.environ.get("RPA_USER_DATA_DIR")
    if not raw:
        return default
    return Path(raw).expanduser()


@dataclass
class BrowserSessionConfig:
    """Configuration for a Playwright browser session."""

    headless: bool = False
    user_data_dir: Path | None = None
    viewport_width: int = 1920
    viewport_height: int = 1080
    timeout_ms: int = 30000
    screenshot_on_error_dir: Path | None = None

    @classmethod
    def from_env(
        cls,
        *,
        headless: bool = False,
        user_data_dir: Path | None = None,
        **kwargs: Any,
    ) -> "BrowserSessionConfig":
        return cls(
            headless=_env_headless(headless),
            user_data_dir=_env_user_data_dir(user_data_dir),
            **kwargs,
        )


@asynccontextmanager
async def browser_session(
    config: BrowserSessionConfig | None = None,
) -> AsyncIterator[tuple["BrowserContext", "Page"]]:
    """Yield ``(context, page)`` for the duration of the ``async with`` block.

    Closes the browser on exit. If ``config.screenshot_on_error_dir`` is set
    and the block raises, captures a screenshot before re-raising.
    """
    from playwright.async_api import async_playwright

    cfg = config or BrowserSessionConfig()
    viewport = {"width": cfg.viewport_width, "height": cfg.viewport_height}

    async with async_playwright() as pw:
        if cfg.user_data_dir is not None:
            cfg.user_data_dir.mkdir(parents=True, exist_ok=True)
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(cfg.user_data_dir),
                headless=cfg.headless,
                viewport=viewport,
                timeout=cfg.timeout_ms,
            )
            browser = None
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await pw.chromium.launch(
                headless=cfg.headless,
                timeout=cfg.timeout_ms,
            )
            context = await browser.new_context(viewport=viewport)
            page = await context.new_page()

        try:
            yield context, page
        except Exception:
            if cfg.screenshot_on_error_dir is not None:
                try:
                    cfg.screenshot_on_error_dir.mkdir(parents=True, exist_ok=True)
                    shot = cfg.screenshot_on_error_dir / "session_error.png"
                    await page.screenshot(path=str(shot), full_page=True)
                    logger.info("Captured failure screenshot: %s", shot)
                except Exception as exc:
                    logger.warning("Failed to capture error screenshot: %s", exc)
            raise
        finally:
            try:
                await context.close()
            finally:
                if browser is not None:
                    await browser.close()
