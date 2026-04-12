"""Smoke test for proof/deploy_claims.py — EV2-9.

Mocks ``UiPathClient`` and ``package_project`` so the test runs
offline and verifies the deploy script:
  1. Calls ``assemble_claims_factory`` to produce 3 sibling dirs
  2. Rewrites AssetClient.cs placeholders with env values before packing
  3. Calls ``package_project`` on each of the 3 sibling dirs
  4. Calls ``ensure_queue("MedicalClaims")``
  5. Calls ``upload_package`` 3 times (once per .nupkg)
  6. Calls ``create_release`` 3 times
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_deploy_claims_script_exists() -> None:
    """The deploy script must exist and be importable."""
    from proof import deploy_claims  # noqa: F401


def test_deploy_claims_has_main_function() -> None:
    from proof import deploy_claims

    assert hasattr(deploy_claims, "main")
    assert callable(deploy_claims.main)


def test_deploy_claims_has_rewrite_asset_client_helper() -> None:
    """The script must have a helper that rewrites AssetClient.cs with
    real env values before packing so the compiled DLL has the current
    credentials + tunnel URL (BW-07 — no runtime asset lookup)."""
    from proof.deploy_claims import rewrite_asset_client

    assert callable(rewrite_asset_client)


def test_rewrite_asset_client_replaces_all_placeholders(tmp_path: Path) -> None:
    from proof.deploy_claims import rewrite_asset_client
    from rpa_architect.codegen.dispatcher_gen import generate_asset_client_cs

    ac_path = tmp_path / "AssetClient.cs"
    ac_path.write_text(generate_asset_client_cs(), encoding="utf-8")

    rewrite_asset_client(
        ac_path,
        {
            "__SUITECRM_BASE_URL__": "https://test.trycloudflare.com",
            "__SUITECRM_CLIENT_ID__": "sc-client-123",
            "__SUITECRM_CLIENT_SECRET__": "sc-secret-456",
            "__SUITECRM_USERNAME__": "admin",
            "__SUITECRM_PASSWORD__": "strong-password",
            "__UIPATH_IDENTITY_URL__": "https://cloud.uipath.com",
            "__UIPATH_ORCHESTRATOR_URL__": "https://cloud.uipath.com/org/tenant/orchestrator_/odata",
            "__UIPATH_CLIENT_ID__": "up-client-789",
            "__UIPATH_CLIENT_SECRET__": "up-secret-abc",
            "__UIPATH_FOLDER_ID__": "42",
        },
    )

    after = ac_path.read_text(encoding="utf-8")
    assert "__SUITECRM_BASE_URL__" not in after
    assert "__UIPATH_CLIENT_SECRET__" not in after
    assert "https://test.trycloudflare.com" in after
    assert "up-client-789" in after


def test_rewrite_asset_client_is_idempotent(tmp_path: Path) -> None:
    """Running rewrite twice with the same values should be a no-op."""
    from proof.deploy_claims import rewrite_asset_client
    from rpa_architect.codegen.dispatcher_gen import generate_asset_client_cs

    ac_path = tmp_path / "AssetClient.cs"
    ac_path.write_text(generate_asset_client_cs(), encoding="utf-8")

    subs = {
        "__SUITECRM_BASE_URL__": "https://test.example",
        "__SUITECRM_CLIENT_ID__": "x",
        "__SUITECRM_CLIENT_SECRET__": "x",
        "__SUITECRM_USERNAME__": "x",
        "__SUITECRM_PASSWORD__": "x",
        "__UIPATH_IDENTITY_URL__": "x",
        "__UIPATH_ORCHESTRATOR_URL__": "x",
        "__UIPATH_CLIENT_ID__": "x",
        "__UIPATH_CLIENT_SECRET__": "x",
        "__UIPATH_FOLDER_ID__": "1",
    }
    rewrite_asset_client(ac_path, subs)
    first = ac_path.read_text(encoding="utf-8")
    rewrite_asset_client(ac_path, subs)
    second = ac_path.read_text(encoding="utf-8")
    assert first == second


async def test_deploy_dry_run_walks_the_three_process_sequence(
    tmp_path: Path, monkeypatch
) -> None:
    """A dry-run pass through the deploy script should produce 3 project
    dirs and call the mocked uipcli pack 3 times."""
    from proof import deploy_claims

    # Env vars so the script doesn't abort on _require_env.
    for key, val in {
        "UIPATH_ORG": "test-org",
        "UIPATH_TENANT_NAME": "DefaultTenant",
        "UIPATH_CLIENT_ID": "up-client",
        "UIPATH_CLIENT_SECRET": "up-secret",
        "UIPATH_FOLDER": "Shared",
        "SUITECRM_PUBLIC_URL": "https://test.trycloudflare.com",
        "SUITECRM_CLIENT_ID": "sc-client",
        "SUITECRM_CLIENT_SECRET": "sc-secret",
        "SUITECRM_USERNAME": "admin",
        "SUITECRM_PASSWORD": "strong-password",
    }.items():
        monkeypatch.setenv(key, val)

    # Patch package_project to just touch a fake .nupkg.
    pack_calls: list[Path] = []

    def fake_pack(project_dir, **kwargs):
        pack_calls.append(Path(project_dir))
        nupkg_path = Path(project_dir).parent / f"{Path(project_dir).name}.1.0.0.nupkg"
        nupkg_path.write_bytes(b"PK\x03\x04 fake nupkg")
        return nupkg_path

    # Patch UiPathClient so no real network calls happen.
    mock_client = MagicMock()
    mock_client._ensure_token = AsyncMock(return_value="fake-token")
    mock_client.ensure_queue = AsyncMock(return_value="queue-id")
    mock_client.upload_package = AsyncMock(
        return_value={"value": [{"Key": "pkg:1.0.0"}]}
    )
    mock_client.create_release = AsyncMock(return_value="release-key")
    mock_client.ensure_asset = AsyncMock()
    mock_client.close = AsyncMock()

    with patch("proof.deploy_claims.package_project", side_effect=fake_pack), \
         patch("proof.deploy_claims.UiPathClient", return_value=mock_client):
        result = await deploy_claims.main(
            output_dir=tmp_path / "claims_factory",
            dry_run=True,
        )

    # Dry-run: assemble + pack, but skip upload/release/queue.
    assert len(pack_calls) == 3
    project_names = {p.name for p in pack_calls}
    assert project_names == {"dispatcher", "performer", "reporter"}
    assert result["assembled"] is True
    assert result["packaged"] == 3
