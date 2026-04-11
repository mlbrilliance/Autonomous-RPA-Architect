"""Tests for UiPath project packager (mocked subprocess)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from rpa_architect.assembler.packager import package_project, publish_project


class TestPackageProject:
    @pytest.mark.asyncio
    async def test_success(self, tmp_path: Path):
        # Create project.json
        (tmp_path / "project.json").write_text("{}")
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        nupkg = out_dir / "TestProject.1.0.0.nupkg"
        nupkg.touch()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        with patch("rpa_architect.assembler.packager.asyncio.create_subprocess_exec",
                    return_value=mock_proc) as mock_exec, \
             patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value="/usr/bin/uipath"):
            result = await package_project(tmp_path, output_dir=out_dir)

        assert result.success
        assert result.nupkg_path == nupkg
        # Verify correct CLI sub-command
        cmd_args = mock_exec.call_args[0]
        assert "package" in cmd_args
        assert "pack" in cmd_args

    @pytest.mark.asyncio
    async def test_cli_not_found_explicit_no_fallback(self, tmp_path: Path):
        """Without manual fallback, CLI absence is a hard failure."""
        (tmp_path / "project.json").write_text("{}")

        with patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value=None):
            result = await package_project(tmp_path, use_manual_fallback=False)

        assert not result.success
        assert any("not found" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_cli_not_found_falls_back_to_manual_packager(self, tmp_path: Path):
        """When CLI is missing, the manual Python packager handles the build."""
        # Need a real (minimal) project.json so manual_packager can read it.
        (tmp_path / "project.json").write_text(
            '{"name": "TestPkg", "projectVersion": "1.0.0", "dependencies": {}}'
        )
        (tmp_path / "Main.xaml").write_text("<Activity />")

        with patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value=None):
            result = await package_project(tmp_path)

        assert result.success
        assert result.nupkg_path is not None
        assert result.nupkg_path.exists()
        assert result.nupkg_path.suffix == ".nupkg"

    @pytest.mark.asyncio
    async def test_no_project_json(self, tmp_path: Path):
        with patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value="/usr/bin/uipath"):
            result = await package_project(tmp_path)

        assert not result.success
        assert any("project.json" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_pack_failure_explicit_no_fallback(self, tmp_path: Path):
        """Without manual fallback, CLI failure surfaces as a hard error."""
        (tmp_path / "project.json").write_text("{}")

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = (b"", b"Build error")

        with patch("rpa_architect.assembler.packager.asyncio.create_subprocess_exec",
                    return_value=mock_proc), \
             patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value="/usr/bin/uipath"):
            result = await package_project(tmp_path, use_manual_fallback=False)

        assert not result.success
        assert any("failed" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_pack_failure_falls_back_to_manual_packager(self, tmp_path: Path):
        """CLI failure triggers the manual packager fallback by default."""
        (tmp_path / "project.json").write_text(
            '{"name": "FallbackPkg", "projectVersion": "0.1.0", "dependencies": {}}'
        )
        (tmp_path / "Main.xaml").write_text("<Activity />")

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = (b"", b"Linux pack rejected")

        with patch("rpa_architect.assembler.packager.asyncio.create_subprocess_exec",
                    return_value=mock_proc), \
             patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value="/usr/bin/uipath"):
            result = await package_project(tmp_path)

        assert result.success
        assert result.nupkg_path is not None
        assert result.nupkg_path.exists()


class TestPublishProject:
    @pytest.mark.asyncio
    async def test_success(self, tmp_path: Path):
        nupkg = tmp_path / "Test.nupkg"
        nupkg.touch()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        with patch("rpa_architect.assembler.packager.asyncio.create_subprocess_exec",
                    return_value=mock_proc) as mock_exec, \
             patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value="/usr/bin/uipath"):
            result = await publish_project(nupkg, feed="https://feed.example.com")

        assert result.success
        assert result.feed_url == "https://feed.example.com"
        # Verify correct CLI sub-command
        cmd_args = mock_exec.call_args[0]
        assert "package" in cmd_args
        assert "deploy" in cmd_args

    @pytest.mark.asyncio
    async def test_nupkg_not_found(self, tmp_path: Path):
        missing = tmp_path / "missing.nupkg"

        with patch("rpa_architect.assembler.packager._find_uipath_cli",
                    return_value="/usr/bin/uipath"):
            result = await publish_project(missing, feed="f")

        assert not result.success
