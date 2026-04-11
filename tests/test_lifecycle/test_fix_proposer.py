"""Tests for fix proposal generation and application."""

import pytest
from pathlib import Path

from rpa_architect.lifecycle.state import DiagnosisResult, ProposedChange, FixProposal
from rpa_architect.lifecycle.fix_proposer import generate_fix_proposal, apply_fix


@pytest.fixture
def project_dir(tmp_path):
    # Create minimal project structure
    (tmp_path / ".objects").mkdir()
    (tmp_path / ".objects" / "app.json").write_text('{"selector": "<html>"}')
    (tmp_path / "Data").mkdir()
    (tmp_path / "Data" / "Config.xlsx").write_bytes(b"fake excel")
    (tmp_path / "Process.xaml").write_text("<Activity>original</Activity>")
    return tmp_path


def _make_diagnosis(category: str, action: str = "fix_code") -> DiagnosisResult:
    return DiagnosisResult(
        root_cause=f"Test {category}",
        category=category,
        confidence=0.8,
        recommended_action=action,
        affected_files=["Process.xaml"],
    )


class TestGenerateFixProposal:
    @pytest.mark.asyncio
    async def test_selector_drift_proposal(self, project_dir):
        diag = _make_diagnosis("selector_drift", "update_selectors")
        proposal = await generate_fix_proposal(diag, str(project_dir), {})
        assert proposal.risk_level == "medium"
        assert proposal.requires_redeployment is True
        assert "selector" in proposal.description.lower()

    @pytest.mark.asyncio
    async def test_code_bug_proposal(self, project_dir):
        diag = _make_diagnosis("code_bug", "fix_code")
        proposal = await generate_fix_proposal(diag, str(project_dir), {})
        assert proposal.risk_level == "medium"
        assert len(proposal.changes) >= 1

    @pytest.mark.asyncio
    async def test_config_update_proposal(self, project_dir):
        diag = _make_diagnosis("data_schema_change", "update_config")
        proposal = await generate_fix_proposal(diag, str(project_dir), {})
        assert proposal.risk_level == "low"

    @pytest.mark.asyncio
    async def test_escalation_proposal(self, project_dir):
        diag = _make_diagnosis("infrastructure", "escalate_to_human")
        proposal = await generate_fix_proposal(diag, str(project_dir), {})
        assert proposal.risk_level == "high"
        assert proposal.requires_redeployment is False
        assert len(proposal.changes) == 0


class TestApplyFix:
    @pytest.mark.asyncio
    async def test_modify_file(self, project_dir):
        proposal = FixProposal(
            description="Fix selector",
            risk_level="low",
            changes=[
                ProposedChange(
                    file_path="Process.xaml",
                    change_type="modify",
                    description="Update element",
                    before="original",
                    after="fixed",
                ),
            ],
        )
        await apply_fix(proposal, str(project_dir))
        content = (project_dir / "Process.xaml").read_text()
        assert "fixed" in content
        assert "original" not in content

    @pytest.mark.asyncio
    async def test_add_file(self, project_dir):
        proposal = FixProposal(
            description="Add helper",
            risk_level="low",
            changes=[
                ProposedChange(
                    file_path="Helper.xaml",
                    change_type="add",
                    description="New helper workflow",
                    after="<Activity>helper</Activity>",
                ),
            ],
        )
        await apply_fix(proposal, str(project_dir))
        assert (project_dir / "Helper.xaml").exists()
        assert "helper" in (project_dir / "Helper.xaml").read_text()

    @pytest.mark.asyncio
    async def test_delete_file(self, project_dir):
        (project_dir / "temp.txt").write_text("delete me")
        proposal = FixProposal(
            description="Remove temp",
            risk_level="low",
            changes=[
                ProposedChange(
                    file_path="temp.txt",
                    change_type="delete",
                    description="Remove temporary file",
                ),
            ],
        )
        await apply_fix(proposal, str(project_dir))
        assert not (project_dir / "temp.txt").exists()
