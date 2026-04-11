"""Tests for the v0.5.0 enterprise MCP tools.

Covers:
- ``generate_enterprise_reframework`` — writes 16 C# files
- ``verify_package_contents`` — structural assertions on a fake .nupkg
- ``get_community_cloud_gotchas`` — returns 12 gotchas + capability matrix
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from rpa_architect.mcp_server.tools import (
    generate_enterprise_reframework,
    get_community_cloud_gotchas,
    verify_package_contents,
)


# ---------------------------------------------------------------------------
# generate_enterprise_reframework
# ---------------------------------------------------------------------------


async def test_generate_enterprise_reframework_writes_all_16_files(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "enterprise"
    result = await generate_enterprise_reframework(
        namespace="TestFactory",
        output_dir=str(out_dir),
        odoo_base_url="https://example.test",
    )
    assert result["success"], result.get("errors")
    expected = {
        "IState.cs",
        "ProcessExceptions.cs",
        "InitState.cs",
        "GetTransactionDataState.cs",
        "ProcessState.cs",
        "SetTransactionStatusState.cs",
        "EndState.cs",
        "ProcessInvoiceMain.cs",
        "BusinessRuleEngine.cs",
        "OdooClient.cs",
        "DocumentUnderstandingClient.cs",
        "LocalInvoiceExtractor.cs",
        "ProcessConfig.cs",
        "BatchMetrics.cs",
        "ProcessContext.cs",
        "EmbeddedInvoices.cs",
    }
    assert set(result["files"]) == expected
    for name in expected:
        assert (out_dir / name).exists(), f"missing {name}"


async def test_generate_enterprise_reframework_uses_namespace(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "custom_ns"
    await generate_enterprise_reframework(
        namespace="MyCustomFactory", output_dir=str(out_dir)
    )
    istate = (out_dir / "IState.cs").read_text(encoding="utf-8")
    assert "namespace MyCustomFactory" in istate


async def test_generate_enterprise_reframework_bakes_odoo_url(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "url_bake"
    await generate_enterprise_reframework(
        namespace="UrlBakeTest",
        output_dir=str(out_dir),
        odoo_base_url="https://my-tunnel.trycloudflare.com",
    )
    main_cs = (out_dir / "ProcessInvoiceMain.cs").read_text(encoding="utf-8")
    assert "https://my-tunnel.trycloudflare.com" in main_cs


# ---------------------------------------------------------------------------
# verify_package_contents
# ---------------------------------------------------------------------------


def _build_fake_nupkg(
    path: Path,
    *,
    project_json: dict | None = None,
    include_dll: bool = True,
    main_xaml: str = '<Activity xmlns:x="foo"/>',
) -> Path:
    """Build a minimal but realistic .nupkg for assertion tests."""
    pj = project_json or {
        "name": "Test",
        "main": "Main.xaml",
        "targetFramework": "Portable",
        "projectProfile": 0,
        "requiresUserInteraction": False,
    }
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("_rels/.rels", "<Relationships/>")
        z.writestr("content/project.json", json.dumps(pj))
        z.writestr("content/Main.xaml", main_xaml)
        if include_dll:
            z.writestr("lib/net8.0/Test.dll", b"MZ\x90\x00" + b"\x00" * 64)
    return path


async def test_verify_package_happy_path(tmp_path: Path) -> None:
    nupkg = _build_fake_nupkg(tmp_path / "ok.nupkg")
    result = await verify_package_contents(str(nupkg))
    assert result["success"] is True
    assert result["failed"] == 0
    names = {a["name"] for a in result["assertions"]}
    assert "target_framework_portable" in names
    assert "project_profile_numeric_zero" in names
    assert "main_field_present" in names
    assert "has_net8_dll" in names


async def test_verify_package_rejects_non_portable_framework(tmp_path: Path) -> None:
    nupkg = _build_fake_nupkg(
        tmp_path / "wrong_tfm.nupkg",
        project_json={
            "name": "X",
            "main": "Main.xaml",
            "targetFramework": "Windows",
            "projectProfile": 0,
            "requiresUserInteraction": False,
        },
    )
    result = await verify_package_contents(str(nupkg))
    failing = [a for a in result["assertions"] if not a["passed"]]
    assert any(a["name"] == "target_framework_portable" for a in failing)
    assert result["success"] is False


async def test_verify_package_rejects_string_project_profile(tmp_path: Path) -> None:
    nupkg = _build_fake_nupkg(
        tmp_path / "string_profile.nupkg",
        project_json={
            "name": "X",
            "main": "Main.xaml",
            "targetFramework": "Portable",
            "projectProfile": "Development",  # String instead of numeric — the trap
            "requiresUserInteraction": False,
        },
    )
    result = await verify_package_contents(str(nupkg))
    failing = [a for a in result["assertions"] if not a["passed"]]
    assert any(a["name"] == "project_profile_numeric_zero" for a in failing)


async def test_verify_package_rejects_missing_main_field(tmp_path: Path) -> None:
    nupkg = _build_fake_nupkg(
        tmp_path / "no_main.nupkg",
        project_json={
            "name": "X",
            "targetFramework": "Portable",
            "projectProfile": 0,
            "requiresUserInteraction": False,
        },
    )
    result = await verify_package_contents(str(nupkg))
    failing = [a for a in result["assertions"] if not a["passed"]]
    assert any(a["name"] == "main_field_present" for a in failing)


async def test_verify_package_rejects_missing_dll(tmp_path: Path) -> None:
    nupkg = _build_fake_nupkg(tmp_path / "no_dll.nupkg", include_dll=False)
    result = await verify_package_contents(str(nupkg))
    failing = [a for a in result["assertions"] if not a["passed"]]
    assert any(a["name"] == "has_net8_dll" for a in failing)


async def test_verify_package_reports_missing_file() -> None:
    result = await verify_package_contents("/nonexistent/path.nupkg")
    assert result["success"] is False
    assert any("not found" in e.lower() for e in result["errors"])


async def test_verify_package_rejects_non_zip(tmp_path: Path) -> None:
    bad = tmp_path / "notazip.nupkg"
    bad.write_bytes(b"this is not a zip file")
    result = await verify_package_contents(str(bad))
    assert result["success"] is False


# ---------------------------------------------------------------------------
# get_community_cloud_gotchas
# ---------------------------------------------------------------------------


async def test_get_gotchas_returns_twelve_items() -> None:
    result = await get_community_cloud_gotchas()
    assert "gotchas" in result
    assert "capability_matrix" in result
    assert len(result["gotchas"]) == 12


async def test_each_gotcha_has_required_fields() -> None:
    result = await get_community_cloud_gotchas()
    for g in result["gotchas"]:
        assert "id" in g
        assert "title" in g
        assert "symptom" in g
        assert "workaround" in g
        assert "status" in g


async def test_gotcha_ids_are_unique_and_sequential() -> None:
    result = await get_community_cloud_gotchas()
    ids = [g["id"] for g in result["gotchas"]]
    assert ids == list(range(1, 13))


async def test_capability_matrix_covers_key_features() -> None:
    result = await get_community_cloud_gotchas()
    matrix = result["capability_matrix"]
    assert matrix["ui_click_type"] == "unavailable_linux_serverless"
    assert matrix["maestro_deploy_api"] == "unavailable"
    assert matrix["action_center"] == "enterprise_only"
    assert matrix["csharp_coded_workflow_httpclient"] == "available"
