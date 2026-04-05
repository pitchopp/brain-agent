"""Brain validators ported from the Python scripts in CLAUDE.md.

Three pure functions, no side effects. Each returns a list of errors;
an empty list means the brain is valid on that axis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Allowed values from TAXONOMIE.md.
ALLOWED_TYPES = {
    "concept",
    "principe",
    "area",
    "projet",
    "reflexion",
    "template",
    "meta",
}
ALLOWED_STATUS = {"seed", "evergreen", "archived"}

# Directories and files that legitimately contain placeholder examples
# and should therefore be skipped by the link/tag validators.
EXCLUDED_FILES = {"README.md", "TAXONOMIE.md"}
EXCLUDED_PREFIXES = ("templates/", ".git/")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_TAG_LINE_RE = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)
_ID_LINE_RE = re.compile(r"^id:\s*(.+)$", re.MULTILINE)
_TYPE_LINE_RE = re.compile(r"^type:\s*([a-z]+)", re.MULTILINE)
_STATUS_LINE_RE = re.compile(r"^status:\s*([a-z]+)", re.MULTILINE)
_DATE_LINE_RE = re.compile(r"^(created|updated):\s*([0-9-]+)", re.MULTILINE)
_DATE_VALUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_CANONICAL_TAG_RE = re.compile(r"^-\s+`([a-z0-9-]+)`", re.MULTILINE)


@dataclass(frozen=True)
class ValidationError:
    file: str
    kind: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.kind}] {self.file}: {self.detail}"


def _iter_markdown_files(brain_path: Path) -> list[Path]:
    files = []
    for p in sorted(brain_path.rglob("*.md")):
        rel = p.relative_to(brain_path).as_posix()
        if any(rel.startswith(pref) for pref in EXCLUDED_PREFIXES):
            continue
        files.append(p)
    return files


def _extract_frontmatter(content: str) -> str | None:
    m = _FRONTMATTER_RE.match(content)
    return m.group(1) if m else None


def validate_wiki_links(brain_path: Path) -> list[ValidationError]:
    """Detect [[...]] references pointing at non-existent notes.

    Port of the first Python script in CLAUDE.md.
    """
    brain_path = Path(brain_path)
    ids: set[str] = set()
    for p in brain_path.rglob("*.md"):
        rel = p.relative_to(brain_path).as_posix()
        if rel.startswith(".git/"):
            continue
        ids.add(p.stem)

    errors: list[ValidationError] = []
    for path in _iter_markdown_files(brain_path):
        rel = path.relative_to(brain_path).as_posix()
        if rel in EXCLUDED_FILES:
            continue
        content = path.read_text(encoding="utf-8")
        for m in _WIKILINK_RE.finditer(content):
            target = m.group(1).split("|")[0].strip()
            if target.startswith("..."):
                continue
            if target not in ids:
                errors.append(
                    ValidationError(file=rel, kind="broken-wikilink", detail=target)
                )
    return errors


def _load_canonical_tags(brain_path: Path) -> set[str]:
    tax = brain_path / "TAXONOMIE.md"
    if not tax.exists():
        return set()
    return set(_CANONICAL_TAG_RE.findall(tax.read_text(encoding="utf-8")))


def validate_tags(brain_path: Path) -> list[ValidationError]:
    """Detect tags that are not declared in TAXONOMIE.md.

    Port of the second Python script in CLAUDE.md.
    """
    brain_path = Path(brain_path)
    canonical = _load_canonical_tags(brain_path)
    errors: list[ValidationError] = []
    for path in _iter_markdown_files(brain_path):
        rel = path.relative_to(brain_path).as_posix()
        content = path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(content)
        if fm is None:
            continue
        tag_match = _TAG_LINE_RE.search(fm)
        if not tag_match:
            continue
        for raw in tag_match.group(1).split(","):
            tag = raw.strip()
            if not tag:
                continue
            if tag not in canonical:
                errors.append(
                    ValidationError(file=rel, kind="unknown-tag", detail=tag)
                )
    return errors


def validate_frontmatter(brain_path: Path) -> list[ValidationError]:
    """Verify that every note has a well-formed frontmatter block.

    Checks:
    - frontmatter block exists
    - id, type, tags, status, created, updated all present
    - id equals filename stem
    - type in ALLOWED_TYPES
    - status in ALLOWED_STATUS
    - created/updated match YYYY-MM-DD
    """
    brain_path = Path(brain_path)
    errors: list[ValidationError] = []
    for path in _iter_markdown_files(brain_path):
        rel = path.relative_to(brain_path).as_posix()
        # Top-level index files (MAP, TAXONOMIE, README, CLAUDE) also carry
        # frontmatter per the brain contract, so we validate them too — except
        # README (prose) and CLAUDE (agent guide), which may not follow the
        # note frontmatter schema.
        if rel in {"README.md", "CLAUDE.md"}:
            continue
        content = path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(content)
        if fm is None:
            errors.append(
                ValidationError(file=rel, kind="missing-frontmatter", detail="no --- block")
            )
            continue

        id_m = _ID_LINE_RE.search(fm)
        type_m = _TYPE_LINE_RE.search(fm)
        status_m = _STATUS_LINE_RE.search(fm)
        tags_m = _TAG_LINE_RE.search(fm)
        dates = dict(_DATE_LINE_RE.findall(fm))

        if not id_m:
            errors.append(ValidationError(rel, "frontmatter", "missing id"))
        else:
            expected_id = path.stem
            actual_id = id_m.group(1).strip()
            if actual_id != expected_id:
                errors.append(
                    ValidationError(
                        rel,
                        "frontmatter",
                        f"id '{actual_id}' != filename '{expected_id}'",
                    )
                )
        if not type_m:
            errors.append(ValidationError(rel, "frontmatter", "missing type"))
        elif type_m.group(1) not in ALLOWED_TYPES:
            errors.append(
                ValidationError(rel, "frontmatter", f"invalid type '{type_m.group(1)}'")
            )
        if not status_m:
            errors.append(ValidationError(rel, "frontmatter", "missing status"))
        elif status_m.group(1) not in ALLOWED_STATUS:
            errors.append(
                ValidationError(
                    rel, "frontmatter", f"invalid status '{status_m.group(1)}'"
                )
            )
        if not tags_m:
            errors.append(ValidationError(rel, "frontmatter", "missing tags"))
        if "created" not in dates:
            errors.append(ValidationError(rel, "frontmatter", "missing created"))
        elif not _DATE_VALUE_RE.match(dates["created"]):
            errors.append(
                ValidationError(
                    rel, "frontmatter", f"invalid created '{dates['created']}'"
                )
            )
        if "updated" not in dates:
            errors.append(ValidationError(rel, "frontmatter", "missing updated"))
        elif not _DATE_VALUE_RE.match(dates["updated"]):
            errors.append(
                ValidationError(
                    rel, "frontmatter", f"invalid updated '{dates['updated']}'"
                )
            )

    return errors


def validate_all(brain_path: Path) -> list[ValidationError]:
    """Run all validators and return the concatenated error list."""
    return (
        validate_wiki_links(brain_path)
        + validate_tags(brain_path)
        + validate_frontmatter(brain_path)
    )
