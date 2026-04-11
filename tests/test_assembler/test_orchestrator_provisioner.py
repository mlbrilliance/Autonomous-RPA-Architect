"""Tests for Orchestrator provisioning (mocked SDK client)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from rpa_architect.assembler.orchestrator_provisioner import provision_orchestrator
from rpa_architect.ir.schema import CredentialInfo, ProcessIR


def _make_ir(**kwargs) -> ProcessIR:
    """Create a minimal ProcessIR with overrides."""
    defaults = {
        "process_name": "TestProcess",
        "systems": [],
        "transactions": [],
        "credentials": [],
    }
    defaults.update(kwargs)
    return ProcessIR(**defaults)


class TestProvisionOrchestrator:
    @pytest.mark.asyncio
    async def test_creates_queues(self):
        ir = _make_ir(credentials=[
            CredentialInfo(name="WorkQueue", type="queue", description="Main queue"),
        ])
        mock_sdk = AsyncMock()
        mock_sdk.create_queue.return_value = None

        result = await provision_orchestrator(ir, mock_sdk)

        assert result.success
        assert "WorkQueue" in result.queues_created
        mock_sdk.create_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_verifies_assets(self):
        ir = _make_ir(credentials=[
            CredentialInfo(name="AppCred", type="credential"),
        ])
        mock_sdk = AsyncMock()
        mock_sdk.get_asset.return_value = {"Name": "AppCred"}

        result = await provision_orchestrator(ir, mock_sdk)

        assert result.success
        assert "AppCred" in result.assets_verified

    @pytest.mark.asyncio
    async def test_handles_existing_queue(self):
        ir = _make_ir(credentials=[
            CredentialInfo(name="ExistingQ", type="queue"),
        ])
        mock_sdk = AsyncMock()
        mock_sdk.create_queue.side_effect = Exception("Queue 'ExistingQ' already exists")

        result = await provision_orchestrator(ir, mock_sdk)

        assert result.success
        assert any("ExistingQ" in q for q in result.queues_created)

    @pytest.mark.asyncio
    async def test_records_errors(self):
        ir = _make_ir(credentials=[
            CredentialInfo(name="BadQueue", type="queue"),
        ])
        mock_sdk = AsyncMock()
        mock_sdk.create_queue.side_effect = Exception("Network timeout")

        result = await provision_orchestrator(ir, mock_sdk)

        assert not result.success
        assert len(result.errors) == 1
        assert "BadQueue" in result.errors[0]

    @pytest.mark.asyncio
    async def test_creates_folders_from_paths(self):
        ir = _make_ir(credentials=[
            CredentialInfo(
                name="AppCred",
                type="credential",
                orchestrator_path="Production/AppCred",
            ),
        ])
        mock_sdk = AsyncMock()
        # Folder doesn't exist
        mock_sdk.get_folder.side_effect = Exception("not found")
        mock_sdk.create_folder.return_value = None

        result = await provision_orchestrator(ir, mock_sdk)

        assert "Production" in result.folders_created
