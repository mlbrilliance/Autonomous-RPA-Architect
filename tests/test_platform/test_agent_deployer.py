"""Tests for agent deployment (mocked subprocess + packager)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from rpa_architect.assembler.packager import PackageResult, PublishResult
from rpa_architect.platform.agent_deployer import deploy_as_agent


class TestDeployAsAgent:
    @pytest.mark.asyncio
    async def test_deploy_success(self, tmp_path: Path):
        nupkg = tmp_path / "output" / "MyProject.1.0.0.nupkg"
        nupkg.parent.mkdir(parents=True)
        nupkg.touch()

        mock_pack = AsyncMock(return_value=PackageResult(
            success=True, nupkg_path=nupkg,
        ))
        mock_pub = AsyncMock(return_value=PublishResult(
            success=True, feed_url="default",
        ))

        with patch("rpa_architect.platform.agent_deployer.package_project", mock_pack), \
             patch("rpa_architect.platform.agent_deployer.publish_project", mock_pub):
            result = await deploy_as_agent(tmp_path)

        assert result.success is True
        assert result.package_id == "MyProject.1.0.0"
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_deploy_pack_failure(self, tmp_path: Path):
        mock_pack = AsyncMock(return_value=PackageResult(
            success=False, errors=["CLI not found"],
        ))

        with patch("rpa_architect.platform.agent_deployer.package_project", mock_pack):
            result = await deploy_as_agent(tmp_path)

        assert result.success is False
        assert "CLI not found" in result.errors

    @pytest.mark.asyncio
    async def test_deploy_publish_failure(self, tmp_path: Path):
        nupkg = tmp_path / "out" / "Proj.nupkg"
        nupkg.parent.mkdir()
        nupkg.touch()

        mock_pack = AsyncMock(return_value=PackageResult(
            success=True, nupkg_path=nupkg,
        ))
        mock_pub = AsyncMock(return_value=PublishResult(
            success=False, errors=["Auth failed"],
        ))

        with patch("rpa_architect.platform.agent_deployer.package_project", mock_pack), \
             patch("rpa_architect.platform.agent_deployer.publish_project", mock_pub):
            result = await deploy_as_agent(tmp_path)

        assert result.success is False
        assert "Auth failed" in result.errors
