"""Loader for the real RAG advisory document corpus.

Reads Markdown documents with a YAML front-matter header from
``data/corpus/<vertical>/*.md`` and returns them as plain dicts. This grounds the
advisory layer on real (realistic sample) supplier docs / SOPs / playbooks /
planner notes instead of a hard-coded synthesized string.

Kept deliberately dependency-light (no import of the RAG advisory module) so it
can be reused by ingestion tooling without a circular import.
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "data" / "corpus"
DEFAULT_VERTICAL = "manufacturing"
REQUIRED_FRONT_MATTER = ("source_id", "source_type", "title")


def _parse_front_matter(raw: str, path: Path) -> tuple[dict, str]:
    """Split a ``---``-delimited YAML front-matter header from the body."""
    if not raw.startswith("---"):
        raise ValueError(f"Corpus document {path.name} is missing a front-matter header")
    # Strip the leading '---' line, then split off the closing '---' line.
    parts = raw.split("\n", 1)[1].split("\n---", 1)
    if len(parts) != 2:
        raise ValueError(f"Corpus document {path.name} has an unterminated front-matter header")
    header = yaml.safe_load(parts[0]) or {}
    if not isinstance(header, dict):
        raise ValueError(f"Corpus document {path.name} has a non-mapping front-matter header")
    body = parts[1].lstrip("\n")
    return header, body


def corpus_dir(vertical: str = DEFAULT_VERTICAL) -> Path:
    return CORPUS_ROOT / vertical


def load_corpus_documents(vertical: str = DEFAULT_VERTICAL) -> list[dict[str, str]]:
    """Load all corpus documents for a vertical, sorted by filename.

    Returns a list of dicts with keys ``source_id``, ``source_type``, ``title``,
    and ``text``. Raises ``FileNotFoundError`` if the vertical directory is
    absent and ``ValueError`` on a malformed/duplicate document, so a broken
    corpus fails loudly instead of silently degrading the advisory grounding.
    """
    directory = corpus_dir(vertical)
    if not directory.is_dir():
        raise FileNotFoundError(f"Corpus directory not found for vertical '{vertical}': {directory}")

    documents: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("*.md")):
        header, body = _parse_front_matter(path.read_text(encoding="utf-8"), path)
        missing = [key for key in REQUIRED_FRONT_MATTER if not str(header.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Corpus document {path.name} missing front-matter keys: {', '.join(missing)}")
        text = body.strip()
        if not text:
            raise ValueError(f"Corpus document {path.name} has an empty body")
        source_id = str(header["source_id"]).strip()
        if source_id in seen_ids:
            raise ValueError(f"Duplicate corpus source_id '{source_id}' in {path.name}")
        seen_ids.add(source_id)
        documents.append(
            {
                "source_id": source_id,
                "source_type": str(header["source_type"]).strip(),
                "title": str(header["title"]).strip(),
                "text": text,
            }
        )
    if not documents:
        raise FileNotFoundError(f"No corpus documents found in {directory}")
    return documents
