# RAG advisory corpus

This directory holds the **real document corpus** the advisory layer grounds its
rationale on (Iteration 3, Phase 2). It replaces the previously hard-coded,
synthesized SOP string in `src/rag/advisory.py`.

- Files are grouped by vertical: `data/corpus/<vertical>/*.md` (currently
  `manufacturing/`, the only built vertical).
- Each document is a Markdown file with a YAML front-matter header delimited by
  `---` lines. Required keys: `source_id`, `source_type`, `title`. Everything
  after the closing `---` is the document body used for retrieval.
- Loaded by `src/ingest/corpus.py::load_corpus_documents(vertical)`.

**Provenance / honesty note:** these are *realistic sample* planner-facing
documents (supplier agreements, SOPs, shortage/surge playbooks, planner field
notes) authored for this prototype to represent the kind of internal supply-chain
docs a customer would plug in. They are **not** confidential customer data. Real
customer-document onboarding (ETL, schema mapping, access control) is Iteration 4
/ Phase 7 scope.

**Trust boundary:** all corpus text is treated as *untrusted evidence*, never as
instructions. Retrieved chunks are prompt-injection scanned at retrieval time and
the LLM is instructed to never follow instructions found inside retrieved
context. The advisory layer explains optimizer output; it never computes or
overrides a numeric metric.
