"""Tests for brain validators."""

from __future__ import annotations

from pathlib import Path

from brain_agent.brain.validation import (
    validate_frontmatter,
    validate_tags,
    validate_wiki_links,
)

TAXONOMIE = """# TAXONOMIE

## Tags
- `tech` — description
- `meta` — description
- `immobilier` — description
"""

NOTE_OK = """---
id: note-alpha
type: concept
tags: [tech, meta]
status: evergreen
created: 2026-04-04
updated: 2026-04-04
---

# Note Alpha

Référence à [[note-beta]].
"""

NOTE_BETA = """---
id: note-beta
type: principe
tags: [meta]
status: seed
created: 2026-04-04
updated: 2026-04-04
---

# Note Beta
"""


def _make_brain(tmp_path: Path, notes: dict[str, str]) -> Path:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "TAXONOMIE.md").write_text(TAXONOMIE)
    (brain / "knowledge").mkdir()
    for name, content in notes.items():
        (brain / "knowledge" / name).write_text(content)
    return brain


def test_wiki_links_ok(tmp_path: Path) -> None:
    brain = _make_brain(
        tmp_path, {"note-alpha.md": NOTE_OK, "note-beta.md": NOTE_BETA}
    )
    assert validate_wiki_links(brain) == []


def test_wiki_links_broken(tmp_path: Path) -> None:
    brain = _make_brain(tmp_path, {"note-alpha.md": NOTE_OK})  # note-beta manquante
    errors = validate_wiki_links(brain)
    assert len(errors) == 1
    assert errors[0].kind == "broken-wikilink"
    assert errors[0].detail == "note-beta"


def test_tags_ok(tmp_path: Path) -> None:
    brain = _make_brain(
        tmp_path, {"note-alpha.md": NOTE_OK, "note-beta.md": NOTE_BETA}
    )
    assert validate_tags(brain) == []


def test_tags_unknown(tmp_path: Path) -> None:
    bad = NOTE_OK.replace("tags: [tech, meta]", "tags: [tech, notatag]")
    brain = _make_brain(
        tmp_path, {"note-alpha.md": bad, "note-beta.md": NOTE_BETA}
    )
    errors = validate_tags(brain)
    assert len(errors) == 1
    assert errors[0].kind == "unknown-tag"
    assert errors[0].detail == "notatag"


def test_frontmatter_ok(tmp_path: Path) -> None:
    brain = _make_brain(
        tmp_path, {"note-alpha.md": NOTE_OK, "note-beta.md": NOTE_BETA}
    )
    # TAXONOMIE.md has no note frontmatter schema — should be flagged.
    errors = validate_frontmatter(brain)
    # We expect errors from TAXONOMIE.md only (no id field etc.)
    rels = {e.file for e in errors}
    assert "knowledge/note-alpha.md" not in rels
    assert "knowledge/note-beta.md" not in rels


def test_frontmatter_missing(tmp_path: Path) -> None:
    brain = _make_brain(tmp_path, {"note-alpha.md": "no frontmatter here"})
    errors = validate_frontmatter(brain)
    kinds = {e.kind for e in errors}
    assert "missing-frontmatter" in kinds


def test_frontmatter_id_mismatch(tmp_path: Path) -> None:
    bad = NOTE_OK.replace("id: note-alpha", "id: wrong-id")
    brain = _make_brain(tmp_path, {"note-alpha.md": bad, "note-beta.md": NOTE_BETA})
    errors = validate_frontmatter(brain)
    assert any("wrong-id" in e.detail for e in errors)


def test_frontmatter_invalid_type(tmp_path: Path) -> None:
    bad = NOTE_OK.replace("type: concept", "type: bogus")
    brain = _make_brain(tmp_path, {"note-alpha.md": bad, "note-beta.md": NOTE_BETA})
    errors = validate_frontmatter(brain)
    assert any("invalid type" in e.detail for e in errors)
