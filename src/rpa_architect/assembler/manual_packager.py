"""Manual NuGet/.nupkg construction without UiPath.CLI.

The Linux build of UiPath.CLI 25.10 (``uipath.cli.linux``) refuses to
pack projects with ``targetFramework: "Windows"`` even though the
resulting ``.nupkg`` is platform-neutral and would run fine on a
Windows Unattended robot. To unblock CI/Linux build environments, this
module assembles the .nupkg directly using Python's :mod:`zipfile`,
producing a NuGet 2.x compatible OPC package.

Structure of a UiPath process .nupkg (REQUIRED for Orchestrator to
recognise the workflow content)::

    PackageId.{version}.nupkg (ZIP)
    ├── [Content_Types].xml
    ├── _rels/.rels
    ├── PackageId.nuspec
    ├── package/services/metadata/core-properties/{guid}.psmdcp
    └── content/                       <-- ALL project files MUST be here
        ├── Main.xaml
        ├── project.json
        ├── Framework/*.xaml
        ├── Data/Config.xlsx
        ├── DocumentProcessing/taxonomy.json
        ├── CodedWorkflows/*.cs
        ├── Agents/{agent_name}/*
        ├── .objects/*
        └── ...

If files are placed at the .nupkg root instead of under ``content/``,
Orchestrator's package metadata reader will accept the upload and show
the version, but the workflow loader won't find Main.xaml and the
package's Requirements panel will display *"This package version
contains no requirements"*. Discovered the hard way during live
deployment to UiPath Community Cloud (April 2026).
"""

from __future__ import annotations

import json
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OPC / NuGet boilerplate
# ---------------------------------------------------------------------------


_CONTENT_TYPES_XML = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
  <Default Extension="psmdcp" ContentType="application/vnd.openxmlformats-package.core-properties+xml" />
  <Default Extension="nuspec" ContentType="application/octet" />
  <Default Extension="xaml" ContentType="application/octet" />
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="xlsx" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
  <Default Extension="cs" ContentType="text/x-csharp" />
  <Default Extension="py" ContentType="text/x-python" />
  <Default Extension="bpmn" ContentType="application/octet" />
  <Default Extension="dmn" ContentType="application/octet" />
  <Default Extension="toml" ContentType="application/octet" />
  <Default Extension="md" ContentType="text/markdown" />
  <Default Extension="txt" ContentType="text/plain" />
</Types>
"""


def _build_rels(nuspec_filename: str, psmdcp_filename: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        f'  <Relationship Type="http://schemas.microsoft.com/packaging/2010/07/manifest"'
        f' Target="/{nuspec_filename}" Id="R1" />\n'
        f'  <Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"'
        f' Target="/package/services/metadata/core-properties/{psmdcp_filename}" Id="R2" />\n'
        "</Relationships>\n"
    )


def _build_nuspec(
    package_id: str,
    version: str,
    description: str,
    authors: str,
    dependencies: dict[str, str],
) -> str:
    """Build a NuGet 2.x compatible .nuspec XML manifest."""
    deps_xml = ""
    if dependencies:
        deps_lines = ["    <dependencies>"]
        for pkg_id, version_range in dependencies.items():
            deps_lines.append(
                f'      <dependency id="{_xml_escape(pkg_id)}"'
                f' version="{_xml_escape(version_range)}" />'
            )
        deps_lines.append("    </dependencies>")
        deps_xml = "\n".join(deps_lines) + "\n"

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">\n'
        "  <metadata>\n"
        f"    <id>{_xml_escape(package_id)}</id>\n"
        f"    <version>{_xml_escape(version)}</version>\n"
        f"    <title>{_xml_escape(package_id)}</title>\n"
        f"    <authors>{_xml_escape(authors)}</authors>\n"
        f"    <owners>{_xml_escape(authors)}</owners>\n"
        "    <requireLicenseAcceptance>false</requireLicenseAcceptance>\n"
        f"    <description>{_xml_escape(description or package_id)}</description>\n"
        "    <tags>UiPath Workflow REFramework</tags>\n"
        f"{deps_xml}"
        "  </metadata>\n"
        "</package>\n"
    )


def _build_psmdcp(package_id: str, version: str, authors: str, description: str) -> str:
    """Build the OPC core-properties (.psmdcp) XML."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<coreProperties xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:dcterms="http://purl.org/dc/terms/"'
        ' xmlns="http://schemas.openxmlformats.org/package/2006/metadata/core-properties">\n'
        f"  <dc:creator>{_xml_escape(authors)}</dc:creator>\n"
        f"  <dc:description>{_xml_escape(description or package_id)}</dc:description>\n"
        f"  <dc:identifier>{_xml_escape(package_id)}</dc:identifier>\n"
        f"  <version>{_xml_escape(version)}</version>\n"
        f"  <keywords>UiPath</keywords>\n"
        f"  <dc:title>{_xml_escape(package_id)}</dc:title>\n"
        f"  <dcterms:created xsi:type=\"dcterms:W3CDTF\">{now}</dcterms:created>\n"
        f"  <dcterms:modified xsi:type=\"dcterms:W3CDTF\">{now}</dcterms:modified>\n"
        "</coreProperties>\n"
    )


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Project content discovery
# ---------------------------------------------------------------------------


_EXCLUDED_DIRS = {".local", "output", ".git", "__pycache__", "Exceptions_Screenshots"}
_EXCLUDED_NAMES = {".DS_Store"}


def _iter_project_files(project_dir: Path) -> list[tuple[Path, str]]:
    """Walk a project directory and return (absolute_path, archive_name) pairs."""
    entries: list[tuple[Path, str]] = []
    for path in project_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(project_dir)
        # Skip excluded directories anywhere in the path.
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.name in _EXCLUDED_NAMES:
            continue
        # NuGet/UiPath archive paths use forward slashes.
        archive_name = rel.as_posix()
        entries.append((path, archive_name))
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pack_project_manually(
    project_dir: Path,
    output_dir: Path | None = None,
    *,
    version: str | None = None,
    authors: str = "Autonomous RPA Architect",
) -> Path:
    """Build a valid UiPath .nupkg from ``project_dir`` without UiPath.CLI.

    Reads ``project.json`` for the package id (``name``), version, and
    dependency list. Writes ``{name}.{version}.nupkg`` to ``output_dir``
    (which defaults to ``project_dir/output``) and returns its path.

    Raises ``FileNotFoundError`` if project.json is missing.
    Raises ``ValueError`` if project.json is malformed.
    """
    project_dir = Path(project_dir)
    project_json_path = project_dir / "project.json"
    if not project_json_path.exists():
        raise FileNotFoundError(f"project.json not found in {project_dir}")

    try:
        project_data = json.loads(project_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid project.json: {exc}") from exc

    package_id = str(project_data.get("name") or project_dir.name)
    pkg_version = version or str(project_data.get("projectVersion") or "1.0.0")
    description = str(project_data.get("description") or package_id)
    dependencies_raw = project_data.get("dependencies") or {}
    if not isinstance(dependencies_raw, dict):
        dependencies_raw = {}
    dependencies = {str(k): str(v) for k, v in dependencies_raw.items()}

    if output_dir is None:
        output_dir = project_dir / "output"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    nupkg_path = output_dir / f"{package_id}.{pkg_version}.nupkg"
    nuspec_filename = f"{package_id}.nuspec"
    psmdcp_guid = uuid.uuid4().hex
    psmdcp_filename = f"{psmdcp_guid}.psmdcp"
    psmdcp_archive_path = (
        f"package/services/metadata/core-properties/{psmdcp_filename}"
    )

    files = _iter_project_files(project_dir)
    if not any(name == "project.json" for _, name in files):
        raise ValueError("project.json was excluded from the package contents")

    nuspec_xml = _build_nuspec(
        package_id=package_id,
        version=pkg_version,
        description=description,
        authors=authors,
        dependencies=dependencies,
    )
    psmdcp_xml = _build_psmdcp(
        package_id=package_id,
        version=pkg_version,
        authors=authors,
        description=description,
    )
    rels_xml = _build_rels(nuspec_filename, psmdcp_filename)

    with zipfile.ZipFile(nupkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # OPC scaffolding (must come first for NuGet readers).
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr(nuspec_filename, nuspec_xml)
        zf.writestr(psmdcp_archive_path, psmdcp_xml)

        # Project content files — UiPath's workflow loader requires
        # everything under ``content/``. Without this prefix, the
        # Orchestrator UI shows the package metadata but the workflow
        # itself is treated as empty.
        for src, archive_name in files:
            zf.write(src, arcname=f"content/{archive_name}")

    logger.info(
        "manual_packager: wrote %s (%d project files + 4 OPC entries)",
        nupkg_path,
        len(files),
    )
    return nupkg_path
