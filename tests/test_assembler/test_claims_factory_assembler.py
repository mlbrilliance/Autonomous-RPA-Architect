"""Tests for the multi-process claims factory assembler — EV2-8.

Verifies that ``assemble_claims_factory`` emits three sibling project
directories (``dispatcher/``, ``performer/``, ``reporter/``), each
with a valid Portable project.json, a minimal Main.xaml, and the
correct C# source files — with byte-identical shared models across
all three.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rpa_architect.assembler.claims_factory_assembler import assemble_claims_factory


@pytest.fixture(scope="module")
def assembled_factory(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("claims_factory")
    return assemble_claims_factory(
        namespace="MedicalClaimsProcessing",
        output_dir=out,
    )


# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------


def test_assembles_three_sibling_project_dirs(
    assembled_factory: dict[str, Path],
) -> None:
    assert set(assembled_factory.keys()) == {"dispatcher", "performer", "reporter"}
    for name, path in assembled_factory.items():
        assert path.exists(), f"{name} dir missing: {path}"
        assert path.is_dir()


def test_each_project_has_main_xaml_and_project_json(
    assembled_factory: dict[str, Path],
) -> None:
    for name, path in assembled_factory.items():
        assert (path / "Main.xaml").exists(), f"{name} missing Main.xaml"
        assert (path / "project.json").exists(), f"{name} missing project.json"


def test_main_xaml_is_minimal_no_expressions(
    assembled_factory: dict[str, Path],
) -> None:
    """BW-6: Portable disables JIT — Main.xaml must be literal only."""
    for path in assembled_factory.values():
        main = (path / "Main.xaml").read_text(encoding="utf-8")
        assert "[" not in main or "mc:Ignorable" in main  # no [expressions]


def test_project_json_has_portable_target_framework(
    assembled_factory: dict[str, Path],
) -> None:
    for name, path in assembled_factory.items():
        pj = json.loads((path / "project.json").read_text(encoding="utf-8"))
        assert pj["targetFramework"] == "Portable", f"{name} wrong targetFramework"


def test_project_json_project_profile_is_numeric_zero(
    assembled_factory: dict[str, Path],
) -> None:
    """BW-11: projectProfile must be the numeric enum, not 'Development'."""
    for name, path in assembled_factory.items():
        pj = json.loads((path / "project.json").read_text(encoding="utf-8"))
        assert pj["designOptions"]["projectProfile"] == 0


def test_project_json_main_field_present(
    assembled_factory: dict[str, Path],
) -> None:
    """BW-12: the legacy `main` field is still required in Studio 25.10."""
    for name, path in assembled_factory.items():
        pj = json.loads((path / "project.json").read_text(encoding="utf-8"))
        assert pj["main"] == "Main.xaml"


def test_project_json_requires_user_interaction_false(
    assembled_factory: dict[str, Path],
) -> None:
    """BW-10: Community Cloud Linux robot has no interactive user."""
    for name, path in assembled_factory.items():
        pj = json.loads((path / "project.json").read_text(encoding="utf-8"))
        assert pj["runtimeOptions"]["requiresUserInteraction"] is False


# ---------------------------------------------------------------------------
# Shared C# files — byte-identical across all three projects
# ---------------------------------------------------------------------------


SHARED_FILES = [
    "Case.cs",
    "Policy.cs",
    "Provider.cs",
    "ClaimVerdict.cs",
    "ClaimMetrics.cs",
    "ClaimsProcessContext.cs",
    "SuiteCrmClient.cs",
    "ClaimsRules.cs",
    "IState.cs",
    "ClaimsExceptions.cs",
    "EndState.cs",
    "AssetClient.cs",
]


def test_shared_models_identical_byte_for_byte_across_projects(
    assembled_factory: dict[str, Path],
) -> None:
    """Every shared file must be content-identical across the three dirs."""
    for shared_file in SHARED_FILES:
        hashes: dict[str, str] = {}
        for name, path in assembled_factory.items():
            full = path / shared_file
            assert full.exists(), f"{name} missing {shared_file}"
            hashes[name] = hashlib.sha256(full.read_bytes()).hexdigest()
        assert len(set(hashes.values())) == 1, (
            f"{shared_file} differs across projects: {hashes}"
        )


# ---------------------------------------------------------------------------
# Process-specific files
# ---------------------------------------------------------------------------


def test_dispatcher_has_dispatcher_specific_files(
    assembled_factory: dict[str, Path],
) -> None:
    dispatcher = assembled_factory["dispatcher"]
    for name in (
        "DispatcherInitState.cs",
        "DispatcherGetTransactionDataState.cs",
        "DispatcherProcessState.cs",
        "DispatcherSetTransactionStatusState.cs",
        "DispatcherMain.cs",
        "UiPathQueueClient.cs",
    ):
        assert (dispatcher / name).exists(), f"missing {name}"


def test_performer_has_performer_specific_files(
    assembled_factory: dict[str, Path],
) -> None:
    performer = assembled_factory["performer"]
    for name in (
        "PerformerInitState.cs",
        "PerformerGetTransactionDataState.cs",
        "PerformerProcessState.cs",
        "PerformerSetTransactionStatusState.cs",
        "PerformerMain.cs",
        "PerformerQueueClient.cs",
    ):
        assert (performer / name).exists(), f"missing {name}"


def test_reporter_has_reporter_specific_files(
    assembled_factory: dict[str, Path],
) -> None:
    reporter = assembled_factory["reporter"]
    for name in (
        "ReporterInitState.cs",
        "ReporterProcessState.cs",
        "ReporterSetStatusState.cs",
        "ReporterMain.cs",
        "ReporterQueueReader.cs",
    ):
        assert (reporter / name).exists(), f"missing {name}"


def test_dispatcher_does_not_have_performer_files(
    assembled_factory: dict[str, Path],
) -> None:
    dispatcher = assembled_factory["dispatcher"]
    assert not (dispatcher / "PerformerMain.cs").exists()
    assert not (dispatcher / "ReporterMain.cs").exists()


def test_performer_does_not_have_dispatcher_files(
    assembled_factory: dict[str, Path],
) -> None:
    performer = assembled_factory["performer"]
    assert not (performer / "DispatcherMain.cs").exists()
    assert not (performer / "ReporterMain.cs").exists()


# ---------------------------------------------------------------------------
# Namespace propagation
# ---------------------------------------------------------------------------


def test_custom_namespace_propagates_to_all_files(tmp_path: Path) -> None:
    projects = assemble_claims_factory(
        namespace="Acme.Claims.V1",
        output_dir=tmp_path,
    )
    for path in projects.values():
        case_cs = (path / "Case.cs").read_text(encoding="utf-8")
        assert "namespace Acme.Claims.V1" in case_cs
