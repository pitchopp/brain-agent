from pathlib import Path

from brain_agent.agent.prompt import build_system_prompt


def _make_brain(tmp_path: Path) -> Path:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "CLAUDE.md").write_text("# CLAUDE\nContrat du brain.")
    (brain / "TAXONOMIE.md").write_text("# TAXONOMIE\n- `tech`\n- `meta`\n")
    (brain / "MAP.md").write_text("# MAP\n- [alpha](knowledge/alpha.md)\n")
    return brain


def test_prompt_contains_all_sections_capture(tmp_path: Path) -> None:
    brain = _make_brain(tmp_path)
    prompt = build_system_prompt("capture", brain)
    assert "Contrat du brain" in prompt
    assert "`tech`" in prompt
    assert "[alpha](knowledge/alpha.md)" in prompt
    assert "Mode CAPTURE" in prompt
    assert "Mode QUERY" not in prompt


def test_prompt_query_mode(tmp_path: Path) -> None:
    brain = _make_brain(tmp_path)
    prompt = build_system_prompt("query", brain)
    assert "Mode QUERY" in prompt
    assert "Mode CAPTURE" not in prompt
    # Query mode must never suggest writing.
    assert "ne modifie AUCUN fichier" in prompt.lower() or "ne modifie aucun fichier" in prompt.lower()


def test_prompt_missing_files_graceful(tmp_path: Path) -> None:
    brain = tmp_path / "empty"
    brain.mkdir()
    prompt = build_system_prompt("capture", brain)
    assert "file not found" in prompt
