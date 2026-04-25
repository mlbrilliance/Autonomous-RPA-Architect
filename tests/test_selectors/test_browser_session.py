"""Tests for BrowserSession config + env-var resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.selectors.browser_session import (
    BrowserSessionConfig,
    _env_headless,
    _env_user_data_dir,
)


def test_default_is_headed() -> None:
    """Headed-by-default matches the YouTube workflow's interactive iteration."""
    cfg = BrowserSessionConfig()
    assert cfg.headless is False
    assert cfg.user_data_dir is None


def test_from_env_passes_through_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RPA_HEADLESS", raising=False)
    monkeypatch.delenv("RPA_USER_DATA_DIR", raising=False)
    cfg = BrowserSessionConfig.from_env()
    assert cfg.headless is False
    assert cfg.user_data_dir is None


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on"])
def test_env_headless_truthy(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("RPA_HEADLESS", raw)
    assert _env_headless(default=False) is True


@pytest.mark.parametrize("raw", ["0", "false", "no", ""])
def test_env_headless_non_truthy(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("RPA_HEADLESS", raw)
    # Empty string falls back to default.
    expected = False if raw else False
    assert _env_headless(default=False) is expected


def test_env_headless_unset_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RPA_HEADLESS", raising=False)
    assert _env_headless(default=True) is True
    assert _env_headless(default=False) is False


def test_env_user_data_dir_expands_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RPA_USER_DATA_DIR", "~/some/profile")
    result = _env_user_data_dir(default=None)
    assert result is not None
    assert "~" not in str(result)


def test_env_user_data_dir_unset_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RPA_USER_DATA_DIR", raising=False)
    fallback = Path("/fallback")
    assert _env_user_data_dir(default=fallback) == fallback
    assert _env_user_data_dir(default=None) is None


def test_from_env_overrides_explicit_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env wins over explicit kwargs — env is the deployment-time toggle."""
    monkeypatch.setenv("RPA_HEADLESS", "1")
    monkeypatch.setenv("RPA_USER_DATA_DIR", "/tmp/test-profile")
    cfg = BrowserSessionConfig.from_env(headless=False, user_data_dir=None)
    assert cfg.headless is True
    assert cfg.user_data_dir == Path("/tmp/test-profile")
