"""Tests for the manual Python-based UiPath .nupkg packager."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from rpa_architect.assembler.manual_packager import pack_project_manually


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    """Build a minimal UiPath project layout on disk."""
    proj = tmp_path / "MyTestProject"
    proj.mkdir()
    (proj / "project.json").write_text(
        json.dumps(
            {
                "name": "MyTestProject",
                "projectVersion": "1.2.3",
                "description": "A minimal test project.",
                "dependencies": {
                    "UiPath.System.Activities": "[25.10.0]",
                    "UiPath.UIAutomation.Activities": "[25.10.16]",
                },
            }
        )
    )
    (proj / "Main.xaml").write_text("<Activity />")
    (proj / "Framework").mkdir()
    (proj / "Framework" / "Process.xaml").write_text("<Activity />")
    (proj / "Data").mkdir()
    (proj / "Data" / "Config.xlsx").write_bytes(b"PK\x03\x04fake xlsx bytes")
    (proj / "DocumentProcessing").mkdir()
    (proj / "DocumentProcessing" / "taxonomy.json").write_text('{"DocumentTypes": []}')
    return proj


def test_pack_returns_path_to_nupkg(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    assert nupkg.exists()
    assert nupkg.suffix == ".nupkg"


def test_pack_uses_project_name_and_version_in_filename(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    assert nupkg.name == "MyTestProject.1.2.3.nupkg"


def test_pack_writes_to_custom_output_dir(minimal_project: Path, tmp_path: Path) -> None:
    out = tmp_path / "custom-out"
    nupkg = pack_project_manually(minimal_project, output_dir=out)
    assert nupkg.parent == out


def test_pack_raises_when_project_json_missing(tmp_path: Path) -> None:
    empty = tmp_path / "Empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        pack_project_manually(empty)


def test_pack_raises_when_project_json_invalid(tmp_path: Path) -> None:
    proj = tmp_path / "Bad"
    proj.mkdir()
    (proj / "project.json").write_text("not json {")
    with pytest.raises(ValueError):
        pack_project_manually(proj)


def test_nupkg_is_a_valid_zip(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    assert zipfile.is_zipfile(nupkg)


def test_nupkg_contains_opc_scaffolding(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    with zipfile.ZipFile(nupkg) as zf:
        names = set(zf.namelist())
    assert "[Content_Types].xml" in names
    assert "_rels/.rels" in names
    assert "MyTestProject.nuspec" in names
    psmdcp = [n for n in names if n.startswith("package/services/metadata/core-properties/") and n.endswith(".psmdcp")]
    assert len(psmdcp) == 1


def test_nupkg_contains_main_xaml_under_content(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    with zipfile.ZipFile(nupkg) as zf:
        assert "content/Main.xaml" in zf.namelist()


def test_nupkg_contains_framework_subdir_under_content(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    with zipfile.ZipFile(nupkg) as zf:
        assert "content/Framework/Process.xaml" in zf.namelist()


def test_nupkg_contains_du_taxonomy_under_content(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    with zipfile.ZipFile(nupkg) as zf:
        assert "content/DocumentProcessing/taxonomy.json" in zf.namelist()


def test_nupkg_contains_config_xlsx_under_content(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    with zipfile.ZipFile(nupkg) as zf:
        assert "content/Data/Config.xlsx" in zf.namelist()


def test_nupkg_contains_project_json_under_content(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    with zipfile.ZipFile(nupkg) as zf:
        assert "content/project.json" in zf.namelist()


def test_nuspec_declares_dependencies(minimal_project: Path) -> None:
    nupkg = pack_project_manually(minimal_project)
    with zipfile.ZipFile(nupkg) as zf:
        nuspec = zf.read("MyTestProject.nuspec").decode("utf-8")
    assert "UiPath.System.Activities" in nuspec
    assert "UiPath.UIAutomation.Activities" in nuspec
    assert "<id>MyTestProject</id>" in nuspec
    assert "<version>1.2.3</version>" in nuspec


def test_excluded_dirs_not_in_nupkg(minimal_project: Path) -> None:
    """The .local/, output/, .git/, __pycache__/ dirs must NOT be packed."""
    (minimal_project / ".local").mkdir()
    (minimal_project / ".local" / "secret.json").write_text("{}")
    (minimal_project / "output").mkdir()
    (minimal_project / "output" / "old.nupkg").write_bytes(b"old")
    (minimal_project / "__pycache__").mkdir()
    (minimal_project / "__pycache__" / "junk.pyc").write_bytes(b"junk")

    nupkg = pack_project_manually(minimal_project, output_dir=minimal_project.parent / "out")
    with zipfile.ZipFile(nupkg) as zf:
        names = zf.namelist()
    assert not any(n.startswith("content/.local/") for n in names)
    assert not any(n.startswith("content/output/") for n in names)
    assert not any("__pycache__" in n for n in names)


def test_pack_real_odoo_project_smoketest(tmp_path: Path) -> None:
    """End-to-end: parse the Odoo PDD, assemble, then pack via manual_packager."""
    import asyncio

    from rpa_architect.assembler.project_assembler import assemble_project
    from rpa_architect.parser.pdd_parser import parse_pdd

    pdd_path = (
        Path(__file__).parent.parent / "fixtures" / "pdds" / "odoo_invoice_processing.md"
    )
    project_dir = tmp_path / "OdooSmoke"
    asyncio.run(assemble_project(parse_pdd(pdd_path), {}, project_dir))

    nupkg = pack_project_manually(project_dir, output_dir=tmp_path / "pack")
    assert nupkg.exists()

    with zipfile.ZipFile(nupkg) as zf:
        names = set(zf.namelist())
    # Critical artifacts must be inside the .nupkg, under content/.
    assert "content/Main.xaml" in names
    assert "content/project.json" in names
    # ProcessInvoiceMain.cs is at the root of content/ — it's the
    # actual entry point for the Cross-Platform / Portable runtime.
    assert "content/ProcessInvoiceMain.cs" in names
    # Post-pivot: no Framework/ stubs, no DocumentUnderstandingFlow,
    # no Maestro/, no Agents/ inside the nupkg. All of those are
    # either design-time siblings or removed as fakery.
    assert not any("Framework/" in n for n in names)
    assert not any("Maestro/" in n for n in names)
    assert not any("Agents/" in n for n in names)
    assert not any("DocumentProcessing/" in n for n in names)
