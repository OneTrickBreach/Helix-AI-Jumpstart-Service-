"""Iteration 3 Phase 2 tests: the real on-disk RAG advisory corpus + loader.

These are pure filesystem/parsing tests (no Qdrant/LLM), so they run in the
normal suite. On-device grounding, retrieval-time injection scanning, and
stale-point cleanup are verified with real `make rag` runs (see journal).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingest import corpus
from src.ingest.corpus import (
    DEFAULT_VERTICAL,
    load_corpus_documents,
)
from src.rag import advisory


def test_default_vertical_corpus_loads_with_required_fields():
    docs = load_corpus_documents(DEFAULT_VERTICAL)
    assert docs, "expected at least one manufacturing corpus document"
    for doc in docs:
        assert doc["source_id"], "every document needs a source_id"
        assert doc["source_type"], "every document needs a source_type"
        assert doc["title"], "every document needs a title"
        assert doc["text"].strip(), "every document needs a non-empty body"
    # front-matter header markers must not leak into the retrieval body
    assert all(not doc["text"].lstrip().startswith("---") for doc in docs)


def test_corpus_source_ids_are_unique():
    docs = load_corpus_documents(DEFAULT_VERTICAL)
    ids = [doc["source_id"] for doc in docs]
    assert len(ids) == len(set(ids)), f"duplicate source_id in corpus: {ids}"


def test_missing_vertical_raises_not_found():
    with pytest.raises(FileNotFoundError):
        load_corpus_documents("no-such-vertical")


def test_missing_front_matter_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vertical = tmp_path / "corpus" / "broken"
    vertical.mkdir(parents=True)
    (vertical / "bad.md").write_text("no front matter here\n", encoding="utf-8")
    monkeypatch.setattr(corpus, "CORPUS_ROOT", tmp_path / "corpus")
    with pytest.raises(ValueError):
        load_corpus_documents("broken")


def test_missing_required_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vertical = tmp_path / "corpus" / "partial"
    vertical.mkdir(parents=True)
    (vertical / "bad.md").write_text(
        "---\nsource_id: x\ntitle: X\n---\nbody\n", encoding="utf-8"
    )  # missing source_type
    monkeypatch.setattr(corpus, "CORPUS_ROOT", tmp_path / "corpus")
    with pytest.raises(ValueError):
        load_corpus_documents("partial")


def test_duplicate_source_id_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vertical = tmp_path / "corpus" / "dupes"
    vertical.mkdir(parents=True)
    fm = "---\nsource_id: dup\nsource_type: sop\ntitle: T\n---\nbody\n"
    (vertical / "a.md").write_text(fm, encoding="utf-8")
    (vertical / "b.md").write_text(fm, encoding="utf-8")
    monkeypatch.setattr(corpus, "CORPUS_ROOT", tmp_path / "corpus")
    with pytest.raises(ValueError):
        load_corpus_documents("dupes")


def test_static_corpus_documents_feed_build_corpus():
    """The real on-disk corpus must actually reach the advisory corpus builder."""
    static_docs = advisory._static_corpus_documents()
    assert static_docs, "static corpus documents should be loaded from disk"
    disk_ids = {doc["source_id"] for doc in load_corpus_documents(DEFAULT_VERTICAL)}
    static_ids = {doc.source_id for doc in static_docs}
    assert static_ids == disk_ids
    # the retired hard-coded SOP id must be gone
    assert "manufacturing-sop" not in static_ids
